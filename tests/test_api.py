from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from accounts import UserStore
from api.main import SESSION_COOKIE, create_app

PASSWORD = "correct horse battery"
EMPLOYEE = {
    "email": "kertu.vaher@nordtech.test",
    "name": "Kertu Vaher",
    "role": "employee",
    "job_title": "Junior Backend Engineer",
    "department": "Engineering",
    "office": "Tallinn",
    "country": "Estonia",
    "manager_name": "Priit Kask",
    "start_date": date(2026, 10, 19),
    "pronouns": "she/her",
}
OTHER_EMPLOYEE = {
    **EMPLOYEE,
    "email": "alex.rinne@nordtech.test",
    "name": "Alex Rinne",
    "office": "Remote",
    "country": "Finland",
    "pronouns": "they/them",
}
HR = {
    **EMPLOYEE,
    "email": "marju.ilves@nordtech.test",
    "name": "Marju Ilves",
    "role": "hr",
    "job_title": "HR Business Partner",
    "department": "HR",
}
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
            yield "updates", {"generate_answer": {"answer_declined": False}}
        yield "updates", {"log_interaction": {key: value for key, value in result.items() if key not in state}}


class FakeStore:
    """Every chat and question in it belongs to `owner_id`."""

    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id
        self.choices: list[tuple[str, bool, str | None, str | None]] = []
        self.read: list[str] = []

    def _interaction(self, interaction_id: str, *, answered: bool = False):
        return SimpleNamespace(
            id=interaction_id,
            user_id=self.owner_id,
            created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
            question="Can I bring my dog?",
            answer="Not in the HR documents. Ask HR?",
            sources=[],
            confidence_score=0.0,
            confidence_label="low",
            answered=answered,
            escalation_status="requested",
            escalation_reason="answer_declined",
            hr_answer=None,
            hr_answered_by=None,
            hr_answered_at=None,
        )

    def get(self, interaction_id):
        if interaction_id == "missing":
            return None
        return self._interaction(interaction_id, answered=interaction_id == "answered")

    def session_owners(self, session_id):
        return {self.owner_id}

    def list_session(self, session_id):
        return [self._interaction("interaction-1")]

    def mark_hr_answers_read(self, session_id):
        self.read.append(session_id)

    def record_hr_choice(self, interaction_id, *, ask_hr, name=None, email=None):
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


@pytest.fixture(scope="module")
def users(tmp_path_factory) -> UserStore:
    store = UserStore(f"sqlite:///{tmp_path_factory.mktemp('accounts') / 'users.db'}")
    for account in (EMPLOYEE, OTHER_EMPLOYEE, HR):
        store.create_user(**account, password=PASSWORD)
    return store


@contextmanager
def _client(
    users: UserStore,
    graph: FakeGraph | None = None,
    store: object | None = None,
    *,
    as_user: dict[str, object] | None = EMPLOYEE,
) -> Iterator[TestClient]:
    store = store or FakeStore(owner_id=users.get_by_email(EMPLOYEE["email"]).id)
    app = create_app(graph=graph or FakeGraph(), store=store, passages=FakePassages(), users=users)
    with TestClient(app) as client:
        if as_user is not None:
            response = client.post("/auth/sign-in", json={"email": as_user["email"], "password": PASSWORD})
            assert response.status_code == 200
        yield client


def _events(response) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health_needs_no_sign_in(users) -> None:
    with _client(users, as_user=None) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_sign_in_sets_a_session_cookie_and_returns_the_profile(users) -> None:
    with _client(users, as_user=None) as client:
        response = client.post("/auth/sign-in", json={"email": " Kertu.Vaher@nordtech.test ", "password": PASSWORD})
        me = client.get("/auth/me")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert response.json()["name"] == "Kertu Vaher"
    assert "password_hash" not in response.json()
    assert me.json() == {
        "id": me.json()["id"],
        "email": "kertu.vaher@nordtech.test",
        "name": "Kertu Vaher",
        "role": "employee",
        "job_title": "Junior Backend Engineer",
        "department": "Engineering",
        "office": "Tallinn",
        "country": "Estonia",
        "manager_name": "Priit Kask",
        "start_date": "2026-10-19",
        "pronouns": "she/her",
    }


def test_sign_in_rejects_a_wrong_password_or_unknown_email_the_same_way(users) -> None:
    with _client(users, as_user=None) as client:
        wrong = client.post("/auth/sign-in", json={"email": EMPLOYEE["email"], "password": "not it"})
        unknown = client.post("/auth/sign-in", json={"email": "nobody@nordtech.test", "password": PASSWORD})
        me = client.get("/auth/me")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers
    assert me.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/auth/me"),
        ("post", "/auth/sign-out"),
        ("post", "/chat"),
        ("post", "/chat/stream"),
        ("post", "/interactions/interaction-1/hr-request"),
        ("get", "/sessions"),
        ("get", "/sessions/s-1/messages"),
        ("get", "/sources/chunk-1"),
        ("get", "/hr/overview"),
        ("get", "/hr/questions"),
        ("get", "/hr/questions/interaction-1"),
        ("post", "/hr/questions/interaction-1/answer"),
    ],
)
def test_every_route_but_health_and_sign_in_needs_a_session(users, method, path) -> None:
    with _client(users, as_user=None) as client:
        response = getattr(client, method)(path)

    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


def test_an_unknown_session_cookie_is_rejected_and_cleared(users) -> None:
    with _client(users, as_user=None) as client:
        client.cookies.set(SESSION_COOKIE, "made-up-token")
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_sign_out_revokes_the_session(users) -> None:
    with _client(users) as client:
        token = client.cookies.get(SESSION_COOKIE)
        assert client.post("/auth/sign-out").status_code == 204
        # The same cookie sent again, as a copy kept elsewhere would be, no longer works.
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/hr/overview"),
        ("get", "/hr/questions"),
        ("get", "/hr/questions/interaction-1"),
        ("post", "/hr/questions/interaction-1/answer"),
    ],
)
def test_employees_cannot_use_the_hr_routes(users, method, path) -> None:
    with _client(users) as client:
        kwargs = {"json": {"answer": "Yes", "applies_to": "everyone"}} if method == "post" else {}
        response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 403


def test_chat_takes_who_is_asking_from_the_account_not_the_request(users) -> None:
    graph = FakeGraph()
    with _client(users, graph) as client:
        response = client.post(
            "/chat",
            json={"message": "How much annual leave do I get?", "employee_context": {"employee_country": "Portugal"}},
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
    assert state["user_id"] == users.get_by_email(EMPLOYEE["email"]).id
    assert state["employee_context"]["employee_country"] == "Estonia"
    assert state["employee_context"]["office_location"] == "Tallinn"
    assert state["employee_context"]["department"] == "Engineering"
    assert state["employee_context"]["role"] == "Junior Backend Engineer"
    assert state["session_id"] == body["session_id"]
    assert state["retrieval_config"] == {"apply_reranker": False}
    assert state["history"] == []


def test_chat_passes_earlier_turns_of_the_session_as_history(users) -> None:
    graph = FakeGraph()
    with _client(users, graph) as client:
        client.post("/chat", json={"message": "and in Finland?", "session_id": "s-1"})

    assert graph.states[0]["history"] == [
        {"question": "Can I bring my dog?", "answer": "Not in the HR documents. Ask HR?"}
    ]


def test_chat_offers_hr_when_the_documents_have_no_answer(users) -> None:
    with _client(users, FakeGraph(result=NOT_FOUND)) as client:
        body = client.post("/chat", json={"message": "Can I bring my dog?", "session_id": "session-7"}).json()

    assert body["session_id"] == "session-7"
    assert body["answered"] is False
    assert body["escalation_status"] == "offered"
    assert body["escalation_reason"] == "answer_declined"


def test_chat_rejects_empty_message(users) -> None:
    with _client(users) as client:
        assert client.post("/chat", json={"message": ""}).status_code == 422


def test_chat_returns_503_when_agent_fails(users) -> None:
    with _client(users, FakeGraph(error=RuntimeError("OpenAI is down"))) as client:
        response = client.post("/chat", json={"message": "How much annual leave do I get?"})

    assert response.status_code == 503
    assert "OpenAI" not in response.text


def test_chat_stream_sends_progress_and_the_checked_answer(users) -> None:
    with _client(users) as client:
        response = client.post("/chat/stream", json={"message": "How much annual leave do I get?", "session_id": "s-1"})

    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    names = [name for name, _ in events]
    assert names[0] == "session"
    assert names[-1] == "done"
    statuses = [payload for name, payload in events if name == "status"]
    assert [status["stage"] for status in statuses] == ["searching", "reading", "writing", "verifying"]
    assert statuses[0]["label"] == "Searching HR documents for Estonia"
    assert statuses[1]["documents"] == ["leave_policy"]
    # The draft isn't streamed; the checked answer arrives whole in "done".
    assert not [name for name, _ in events if name == "token"]
    done = events[-1][1]
    assert done["answer"] == "Employees in Estonia get 28 calendar days."
    assert done["session_id"] == "s-1"
    assert done["interaction_id"] == "interaction-1"


def test_chat_stream_offers_hr_without_tokens_when_not_found(users) -> None:
    with _client(users, FakeGraph(result=NOT_FOUND)) as client:
        events = _events(client.post("/chat/stream", json={"message": "Can I bring my dog?"}))

    assert not [name for name, _ in events if name == "token"]
    assert [payload["stage"] for name, payload in events if name == "status"][-1] == "not_found"
    assert events[-1][1]["escalation_status"] == "offered"


def test_chat_stream_reports_errors_as_an_event(users) -> None:
    with _client(users, FakeGraph(error=RuntimeError("OpenAI is down"))) as client:
        events = _events(client.post("/chat/stream", json={"message": "How much annual leave do I get?"}))

    assert events[-1] == ("error", {"detail": "The assistant is temporarily unavailable."})


def test_hr_request_records_the_signed_in_employee_only_when_sent(users) -> None:
    store = FakeStore(owner_id=users.get_by_email(EMPLOYEE["email"]).id)
    with _client(users, store=store) as client:
        yes = client.post("/interactions/interaction-1/hr-request", json={"ask_hr": True})
        no = client.post("/interactions/interaction-2/hr-request", json={"ask_hr": False})

    assert yes.status_code == 200
    assert yes.json()["escalation_status"] == "requested"
    assert "kertu.vaher@nordtech.test" in yes.json()["message"]
    assert no.json()["escalation_status"] == "declined"
    # The store keeps the name and email only for questions sent to HR.
    assert store.choices == [
        ("interaction-1", True, "Kertu Vaher", "kertu.vaher@nordtech.test"),
        ("interaction-2", False, "Kertu Vaher", "kertu.vaher@nordtech.test"),
    ]


def test_hr_request_rejects_unknown_or_answered_questions(users) -> None:
    with _client(users) as client:
        assert client.post("/interactions/missing/hr-request", json={"ask_hr": True}).status_code == 404
        assert client.post("/interactions/answered/hr-request", json={"ask_hr": True}).status_code == 409


def test_session_messages_returns_history_with_hr_status(users) -> None:
    with _client(users) as client:
        messages = client.get("/sessions/session-7/messages").json()

    assert messages[0]["question"] == "Can I bring my dog?"
    assert messages[0]["answered"] is False
    assert messages[0]["escalation_status"] == "requested"
    assert messages[0]["hr_answer"] is None


def test_employees_cannot_open_or_continue_someone_elses_chat(users) -> None:
    # Every chat in this store belongs to Kertu; Alex is signed in.
    store = FakeStore(owner_id=users.get_by_email(EMPLOYEE["email"]).id)
    graph = FakeGraph()
    with _client(users, graph, store, as_user=OTHER_EMPLOYEE) as client:
        messages = client.get("/sessions/s-1/messages")
        chat = client.post("/chat", json={"message": "What did they ask?", "session_id": "s-1"})
        stream = client.post("/chat/stream", json={"message": "What did they ask?", "session_id": "s-1"})
        hr_request = client.post("/interactions/interaction-1/hr-request", json={"ask_hr": True})

    assert messages.status_code == chat.status_code == stream.status_code == hr_request.status_code == 404
    assert graph.states == []
    assert store.choices == []


def test_source_returns_the_document_with_the_chunk_highlighted(users) -> None:
    with _client(users) as client:
        response = client.get("/sources/chunk-1")

    assert response.status_code == 200
    body = response.json()
    assert body["source_doc"] == "leave_policy"
    assert body["content"][body["highlight_start"] : body["highlight_end"]] == "28 calendar days."


def test_source_returns_404_for_unknown_chunks(users) -> None:
    with _client(users) as client:
        assert client.get("/sources/unknown").status_code == 404
