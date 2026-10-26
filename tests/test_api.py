from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import create_app


class FakeGraph:
    def __init__(self, result: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.states: list[dict[str, object]] = []
        self.result = result
        self.error = error

    def invoke(self, state):
        self.states.append(state)
        if self.error is not None:
            raise self.error
        return {
            **state,
            "interaction_id": "interaction-1",
            "confidence_score": 0.7,
            "confidence_label": "medium",
            "final_response": {
                "text": "Employees in Estonia get 28 calendar days.",
                "sources": [
                    {
                        "chunk_id": "chunk-1",
                        "source_file": "leave_absence_policy.md",
                        "section_path": "Leave > Estonia",
                        "score": 0.03,
                    }
                ],
                "escalated": False,
            },
            **(self.result or {}),
        }


class FakeStore:
    def list_session(self, session_id):
        return [
            SimpleNamespace(
                id="interaction-1",
                created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
                question="How much annual leave do I get?",
                answer="28 calendar days.",
                sources=[{"chunk_id": "chunk-1", "source_file": "leave_absence_policy.md", "score": 0.03}],
                confidence_score=0.7,
                confidence_label="medium",
                escalated=False,
                escalation_reason=None,
            )
        ]


def test_health() -> None:
    with TestClient(create_app(graph=FakeGraph(), store=FakeStore())) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_chat_passes_question_and_context_and_returns_answer() -> None:
    graph = FakeGraph()
    with TestClient(create_app(graph=graph, store=FakeStore())) as client:
        response = client.post(
            "/chat",
            json={
                "message": "How much annual leave do I get?",
                "employee_context": {"employee_country": "Estonia"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Employees in Estonia get 28 calendar days."
    assert body["sources"][0]["source_file"] == "leave_absence_policy.md"
    assert body["escalated"] is False
    assert body["interaction_id"] == "interaction-1"
    assert body["session_id"]
    state = graph.states[0]
    assert state["question"] == "How much annual leave do I get?"
    assert state["employee_context"] == {"employee_country": "Estonia"}
    assert state["session_id"] == body["session_id"]
    assert state["retrieval_config"] == {"apply_reranker": False}


def test_chat_keeps_given_session_and_reports_escalation() -> None:
    graph = FakeGraph(
        result={
            "confidence_score": 0.0,
            "confidence_label": "low",
            "final_response": {"text": "Logged for HR.", "sources": [], "escalated": True},
            "escalation": {"reason": "answer_declined"},
        }
    )
    with TestClient(create_app(graph=graph, store=FakeStore())) as client:
        body = client.post("/chat", json={"message": "Can I bring my dog?", "session_id": "session-7"}).json()

    assert body["session_id"] == "session-7"
    assert body["escalated"] is True
    assert body["escalation_reason"] == "answer_declined"


def test_chat_rejects_empty_message() -> None:
    with TestClient(create_app(graph=FakeGraph(), store=FakeStore())) as client:
        assert client.post("/chat", json={"message": ""}).status_code == 422


def test_chat_returns_503_when_agent_fails() -> None:
    graph = FakeGraph(error=RuntimeError("OpenAI is down"))
    with TestClient(create_app(graph=graph, store=FakeStore())) as client:
        response = client.post("/chat", json={"message": "How much annual leave do I get?"})

    assert response.status_code == 503
    assert "OpenAI" not in response.text


def test_session_messages_returns_history() -> None:
    with TestClient(create_app(graph=FakeGraph(), store=FakeStore())) as client:
        messages = client.get("/sessions/session-7/messages").json()

    assert messages[0]["question"] == "How much annual leave do I get?"
    assert messages[0]["sources"][0]["source_file"] == "leave_absence_policy.md"
