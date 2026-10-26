from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import create_app

ANSWER_SOURCE = {
    "chunk_id": "chunk-1",
    "source_doc": "leave_policy",
    "source_file": "leave_absence_policy.md",
    "section_path": "Leave > Estonia",
    "score": 0.03,
}
NOT_FOUND = {
    "confidence_score": 0.0,
    "confidence_label": "low",
    "final_response": {"text": "Not in the HR documents. Ask HR?", "sources": [], "answered": False},
    "hr_handoff": {"reason": "answer_declined"},
}


class FakeGraph:
    def __init__(self, result: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.states: list[dict[str, object]] = []
        self.result = result
        self.error = error

    def _result(self, state):
        return {
            **state,
            "interaction_id": "interaction-1",
            "confidence_score": 0.7,
            "confidence_label": "medium",
            "final_response": {
                "text": "Employees in Estonia get 28 calendar days.",
                "sources": [ANSWER_SOURCE],
                "answered": True,
            },
            **(self.result or {}),
        }

    def invoke(self, state):
        self.states.append(state)
        if self.error is not None:
            raise self.error
        return self._result(state)

    def stream(self, state, stream_mode):
        self.states.append(state)
        if self.error is not None:
            raise self.error
        result = self._result(state)
        yield "updates", {"resolve_filters": {"resolved_filters": {"country": "Estonia"}}}
        yield "updates", {"retrieve_documents": {"retrieved_chunks": [{"metadata": {"source_doc": "leave_policy"}}]}}
        yield "updates", {"score_confidence": {"confidence_label": result["confidence_label"]}}
        if result["final_response"]["answered"]:
            for token in ("Employees in Estonia ", "get 28 calendar days."):
                yield "messages", (SimpleNamespace(content=token), {"langgraph_node": "generate_answer"})
        yield "updates", {"log_interaction": {key: value for key, value in result.items() if key not in state}}


class FakeStore:
    def __init__(self) -> None:
        self.choices: list[tuple[str, bool]] = []

    def list_session(self, session_id):
        return [
            SimpleNamespace(
                id="interaction-1",
                created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
                question="Can I bring my dog?",
                answer="Not in the HR documents. Ask HR?",
                sources=[],
                confidence_score=0.0,
                confidence_label="low",
                answered=False,
                escalation_status="requested",
                escalation_reason="answer_declined",
            )
        ]

    def record_hr_choice(self, interaction_id, *, ask_hr, name=None, email=None):
        if interaction_id == "missing":
            return None
        if interaction_id == "answered":
            raise ValueError("answered")
        self.choices.append((interaction_id, ask_hr, name, email))
        return SimpleNamespace(id=interaction_id, escalation_status="requested" if ask_hr else "declined")


class FakePassages:
    def passage(self, chunk_id):
        if chunk_id != "chunk-1":
            return None
        return SimpleNamespace(
            chunk_id="chunk-1",
            source_doc="leave_policy",
            source_file="leave_absence_policy.md",
            section_path="Leave > Estonia",
            content="# Leave\n\n## Estonia\n\n28 calendar days.",
            highlight_start=21,
            highlight_end=38,
        )


def _client(graph: FakeGraph | None = None, store: FakeStore | None = None) -> TestClient:
    return TestClient(create_app(graph=graph or FakeGraph(), store=store or FakeStore(), passages=FakePassages()))


def _events(response) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health() -> None:
    with _client() as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_chat_passes_question_and_context_and_returns_answer() -> None:
    graph = FakeGraph()
    with _client(graph) as client:
        response = client.post(
            "/chat",
            json={"message": "How much annual leave do I get?", "employee_context": {"employee_country": "Estonia"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Employees in Estonia get 28 calendar days."
    assert body["sources"][0]["source_file"] == "leave_absence_policy.md"
    assert body["answered"] is True
    assert body["escalation_status"] is None
    assert body["interaction_id"] == "interaction-1"
    state = graph.states[0]
    assert state["question"] == "How much annual leave do I get?"
    assert state["employee_context"] == {"employee_country": "Estonia"}
    assert state["session_id"] == body["session_id"]
    assert state["retrieval_config"] == {"apply_reranker": False}
    assert state["history"] == []


def test_chat_passes_earlier_turns_of_the_session_as_history() -> None:
    graph = FakeGraph()
    with _client(graph) as client:
        client.post("/chat", json={"message": "and in Finland?", "session_id": "s-1"})

    assert graph.states[0]["history"] == [
        {"question": "Can I bring my dog?", "answer": "Not in the HR documents. Ask HR?"}
    ]


def test_chat_offers_hr_when_the_documents_have_no_answer() -> None:
    with _client(FakeGraph(result=NOT_FOUND)) as client:
        body = client.post("/chat", json={"message": "Can I bring my dog?", "session_id": "session-7"}).json()

    assert body["session_id"] == "session-7"
    assert body["answered"] is False
    assert body["escalation_status"] == "offered"
    assert body["escalation_reason"] == "answer_declined"


def test_chat_rejects_empty_message() -> None:
    with _client() as client:
        assert client.post("/chat", json={"message": ""}).status_code == 422


def test_chat_returns_503_when_agent_fails() -> None:
    with _client(FakeGraph(error=RuntimeError("OpenAI is down"))) as client:
        response = client.post("/chat", json={"message": "How much annual leave do I get?"})

    assert response.status_code == 503
    assert "OpenAI" not in response.text


def test_chat_stream_sends_progress_tokens_and_final_answer() -> None:
    with _client() as client:
        response = client.post("/chat/stream", json={"message": "How much annual leave do I get?", "session_id": "s-1"})

    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    names = [name for name, _ in events]
    assert names[0] == "session"
    assert names[-1] == "done"
    statuses = [payload for name, payload in events if name == "status"]
    assert [status["stage"] for status in statuses] == ["searching", "reading", "checking"]
    assert statuses[0]["label"] == "Searching HR documents for Estonia"
    assert statuses[1]["documents"] == ["leave_policy"]
    tokens = "".join(payload["text"] for name, payload in events if name == "token")
    assert tokens == "Employees in Estonia get 28 calendar days."
    done = events[-1][1]
    assert done["answer"] == "Employees in Estonia get 28 calendar days."
    assert done["session_id"] == "s-1"
    assert done["interaction_id"] == "interaction-1"


def test_chat_stream_offers_hr_without_tokens_when_not_found() -> None:
    with _client(FakeGraph(result=NOT_FOUND)) as client:
        events = _events(client.post("/chat/stream", json={"message": "Can I bring my dog?"}))

    assert not [name for name, _ in events if name == "token"]
    assert [payload["stage"] for name, payload in events if name == "status"][-1] == "not_found"
    assert events[-1][1]["escalation_status"] == "offered"


def test_chat_stream_reports_errors_as_an_event() -> None:
    with _client(FakeGraph(error=RuntimeError("OpenAI is down"))) as client:
        events = _events(client.post("/chat/stream", json={"message": "How much annual leave do I get?"}))

    assert events[-1] == ("error", {"detail": "The assistant is temporarily unavailable."})


def test_hr_request_records_the_choice_and_who_asked_only_when_sent() -> None:
    store = FakeStore()
    with _client(store=store) as client:
        yes = client.post("/interactions/interaction-1/hr-request", json={"ask_hr": True})
        no = client.post("/interactions/interaction-2/hr-request", json={"ask_hr": False})

    assert yes.status_code == 200
    assert yes.json()["escalation_status"] == "requested"
    assert "employee@nordtech.test" in yes.json()["message"]
    assert no.json()["escalation_status"] == "declined"
    # The store keeps the name and email only for questions sent to HR.
    assert store.choices == [
        ("interaction-1", True, "Employee", "employee@nordtech.test"),
        ("interaction-2", False, "Employee", "employee@nordtech.test"),
    ]


def test_hr_request_rejects_unknown_or_answered_questions() -> None:
    with _client() as client:
        assert client.post("/interactions/missing/hr-request", json={"ask_hr": True}).status_code == 404
        assert client.post("/interactions/answered/hr-request", json={"ask_hr": True}).status_code == 409


def test_session_messages_returns_history_with_hr_status() -> None:
    with _client() as client:
        messages = client.get("/sessions/session-7/messages").json()

    assert messages[0]["question"] == "Can I bring my dog?"
    assert messages[0]["answered"] is False
    assert messages[0]["escalation_status"] == "requested"


def test_source_returns_the_document_with_the_chunk_highlighted() -> None:
    with _client() as client:
        response = client.get("/sources/chunk-1")

    assert response.status_code == 200
    body = response.json()
    assert body["source_doc"] == "leave_policy"
    assert body["content"][body["highlight_start"] : body["highlight_end"]] == "28 calendar days."


def test_source_returns_404_for_unknown_chunks() -> None:
    with _client() as client:
        assert client.get("/sources/unknown").status_code == 404
