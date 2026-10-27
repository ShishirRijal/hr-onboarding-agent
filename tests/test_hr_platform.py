from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from accounts import UserStore
from api.main import create_app
from interactions import InteractionStore

PASSWORD = "correct horse battery"
EMPLOYEE = {
    "email": "joonas.laaksonen@nordtech.test",
    "name": "Joonas Laaksonen",
    "role": "employee",
    "job_title": "Senior Account Executive",
    "department": "Sales",
    "office": "Tampere",
    "country": "Finland",
    "manager_name": "Jukka Hämäläinen",
    "start_date": date(2026, 10, 26),
}
HR = {
    **EMPLOYEE,
    "email": "marju.ilves@nordtech.test",
    "name": "Marju Ilves",
    "role": "hr",
    "job_title": "HR Business Partner",
    "department": "HR",
    "office": "Tallinn",
    "country": "Estonia",
}


class FakeKnowledge:
    def __init__(self, error: Exception | None = None) -> None:
        self.added: list[dict[str, str]] = []
        self.error = error
        self.lock = None
        self.held_lock: list[bool] = []

    def add_hr_answer(self, **answer: str) -> str:
        self.held_lock.append(self.lock.locked())
        if self.error is not None:
            raise self.error
        self.added.append(answer)
        return f"chunk-{answer['interaction_id']}"


class FakeGraph:
    def invoke(self, state):
        raise AssertionError("The graph isn't used in these tests.")


class FakePassages:
    def passage(self, chunk_id):
        return None


@pytest.fixture
def stores(tmp_path: Path) -> tuple[InteractionStore, UserStore]:
    database = f"sqlite:///{tmp_path / 'hr.db'}"
    users = UserStore(database)
    for account in (EMPLOYEE, HR):
        users.create_user(**account, password=PASSWORD)
    return InteractionStore(database), users


@contextmanager
def _client(stores, knowledge: FakeKnowledge) -> Iterator[TestClient]:
    store, users = stores
    app = create_app(graph=FakeGraph(), store=store, passages=FakePassages(), knowledge=knowledge, users=users)
    with TestClient(app) as client:
        knowledge.lock = app.state.graph_lock
        yield client


def _sign_in(client: TestClient, account: dict[str, object]) -> None:
    client.cookies.clear()
    assert client.post("/auth/sign-in", json={"email": account["email"], "password": PASSWORD}).status_code == 200


def _ask(store: InteractionStore, users: UserStore, question: str, *, session_id: str, answered: bool) -> str:
    """Logs a question as the agent would for the employee."""
    employee = users.get_by_email(EMPLOYEE["email"])
    state: dict[str, object] = {
        "session_id": session_id,
        "user_id": employee.id,
        "question": question,
        "employee_context": employee.employee_context(),
        "final_response": {
            "text": "You get 25 days." if answered else "Not in the HR documents. Ask HR?",
            "sources": [],
            "answered": answered,
        },
    }
    if not answered:
        state["hr_handoff"] = {
            "reason": "answer_declined",
            "candidate_sources": [
                {"section_path": "NordTech Solutions — Employee Handbook v2.1 > 6. Office Life > Pets"},
                {"section_path": "NordTech Solutions — Benefits & Perks Guide > 2. Wellbeing"},
            ],
        }
    return store.log(state)


def _send_to_hr(client: TestClient, stores) -> str:
    """Joonas asks two questions; the second isn't in the documents and he sends it to HR."""
    store, users = stores
    _ask(store, users, "How much annual leave do I get?", session_id="s-1", answered=True)
    interaction_id = _ask(store, users, "Can I bring my dog to the office?", session_id="s-1", answered=False)
    _sign_in(client, EMPLOYEE)
    assert client.post(f"/interactions/{interaction_id}/hr-request", json={"ask_hr": True}).status_code == 200
    return interaction_id


def test_the_inbox_shows_who_asked_and_why_from_their_account(stores) -> None:
    with _client(stores, FakeKnowledge()) as client:
        interaction_id = _send_to_hr(client, stores)
        _sign_in(client, HR)
        inbox = client.get("/hr/questions").json()
        detail = client.get(f"/hr/questions/{interaction_id}").json()

    assert [item["interaction_id"] for item in inbox] == [interaction_id]
    # SQLite drops the time zone; the API puts it back so browsers don't read UTC as local time.
    assert inbox[0]["asked_at"].endswith("Z")
    assert inbox[0]["asker"] == {
        "name": "Joonas Laaksonen",
        "email": "joonas.laaksonen@nordtech.test",
        "job_title": "Senior Account Executive",
        "department": "Sales",
        "office": "Tampere",
        "country": "Finland",
    }
    assert detail["question"] == "Can I bring my dog to the office?"
    assert detail["reason"] == "The HR documents mention the topic but don't answer the question."
    assert detail["documents_checked"] == ["Employee Handbook v2.1", "Benefits & Perks Guide"]
    assert detail["earlier_turns"] == [{"question": "How much annual leave do I get?", "answer": "You get 25 days."}]
    # The asker is recorded from the session, not a placeholder.
    assert stores[0].get(interaction_id).employee_email == "joonas.laaksonen@nordtech.test"


def test_hr_answer_reaches_the_employee_and_the_knowledge_base(stores) -> None:
    knowledge = FakeKnowledge()
    with _client(stores, knowledge) as client:
        interaction_id = _send_to_hr(client, stores)
        _sign_in(client, HR)
        answered = client.post(
            f"/hr/questions/{interaction_id}/answer",
            json={"answer": "  Dogs are welcome on Fridays in Tampere.  ", "applies_to": "country"},
        )
        inbox = client.get("/hr/questions").json()
        answered_list = client.get("/hr/questions", params={"status": "answered"}).json()

        _sign_in(client, EMPLOYEE)
        sessions_before = client.get("/sessions").json()
        messages = client.get("/sessions/s-1/messages").json()
        sessions_after = client.get("/sessions").json()

    assert answered.status_code == 200
    body = answered.json()
    assert body["status"] == "answered"
    assert body["hr_answer"] == "Dogs are welcome on Fridays in Tampere."
    assert body["hr_answered_by"] == "Marju Ilves"
    assert body["hr_answer_country"] == "Finland"
    assert inbox == []
    assert [item["interaction_id"] for item in answered_list] == [interaction_id]
    # Indexed for the asker's country, while holding the lock that keeps embedding single-threaded.
    assert knowledge.added == [
        {
            "interaction_id": interaction_id,
            "question": "Can I bring my dog to the office?",
            "answer": "Dogs are welcome on Fridays in Tampere.",
            "country": "Finland",
        }
    ]
    assert knowledge.held_lock == [True]
    assert stores[0].get(interaction_id).hr_answer_chunk_id == f"chunk-{interaction_id}"

    assert sessions_before == [
        {
            "session_id": "s-1",
            "title": "How much annual leave do I get?",
            "updated_at": sessions_before[0]["updated_at"],
            "unread_hr_replies": 1,
        }
    ]
    assert messages[1]["escalation_status"] == "answered"
    assert messages[1]["hr_answer"] == "Dogs are welcome on Fridays in Tampere."
    assert messages[1]["hr_answered_by"] == "Marju Ilves"
    assert sessions_after[0]["unread_hr_replies"] == 0


def test_an_answer_for_everyone_is_indexed_for_all_countries(stores) -> None:
    knowledge = FakeKnowledge()
    with _client(stores, knowledge) as client:
        interaction_id = _send_to_hr(client, stores)
        _sign_in(client, HR)
        client.post(f"/hr/questions/{interaction_id}/answer", json={"answer": "Yes.", "applies_to": "everyone"})

    assert knowledge.added[0]["country"] == "All"


def test_a_question_can_only_be_answered_once(stores) -> None:
    knowledge = FakeKnowledge()
    with _client(stores, knowledge) as client:
        interaction_id = _send_to_hr(client, stores)
        _sign_in(client, HR)
        first = client.post(f"/hr/questions/{interaction_id}/answer", json={"answer": "Yes.", "applies_to": "everyone"})
        second = client.post(f"/hr/questions/{interaction_id}/answer", json={"answer": "No.", "applies_to": "everyone"})

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(knowledge.added) == 1


def test_nothing_is_sent_when_the_knowledge_base_is_unavailable(stores) -> None:
    with _client(stores, FakeKnowledge(error=RuntimeError("Qdrant is down"))) as client:
        interaction_id = _send_to_hr(client, stores)
        _sign_in(client, HR)
        response = client.post(f"/hr/questions/{interaction_id}/answer", json={"answer": "Yes.", "applies_to": "everyone"})

    assert response.status_code == 503
    assert "Qdrant" not in response.text
    assert stores[0].get(interaction_id).escalation_status == "requested"


def test_only_questions_sent_to_hr_can_be_opened_or_answered(stores) -> None:
    store, users = stores
    with _client(stores, FakeKnowledge()) as client:
        offered_id = _ask(store, users, "Is there parking?", session_id="s-2", answered=False)
        _sign_in(client, HR)
        assert client.get(f"/hr/questions/{offered_id}").status_code == 404
        assert client.get("/hr/questions/missing").status_code == 404
        answer = client.post(f"/hr/questions/{offered_id}/answer", json={"answer": "Yes.", "applies_to": "everyone"})

    assert answer.status_code == 404


def test_overview_counts_open_and_answered_questions_and_common_topics(stores) -> None:
    store, users = stores
    with _client(stores, FakeKnowledge()) as client:
        interaction_id = _send_to_hr(client, stores)
        _ask(store, users, "Can my cat come too?", session_id="s-3", answered=False)
        second_id = _ask(store, users, "Is there a dog walker?", session_id="s-4", answered=False)
        client.post(f"/interactions/{second_id}/hr-request", json={"ask_hr": True})
        _sign_in(client, HR)
        before = client.get("/hr/overview").json()
        client.post(f"/hr/questions/{interaction_id}/answer", json={"answer": "Yes.", "applies_to": "everyone"})
        after = client.get("/hr/overview").json()

    assert before["open_questions"] == 2
    assert before["answered_this_week"] == 0
    assert before["common_topics"] == [{"topic": "Employee Handbook v2.1 › 6. Office Life", "count": 3}]
    assert after["open_questions"] == 1
    assert after["answered_this_week"] == 1


def test_list_of_chats_only_has_the_signed_in_users_own(stores) -> None:
    store, users = stores
    hr_user = users.get_by_email(HR["email"])
    store.log({"session_id": "hr-chat", "user_id": hr_user.id, "question": "Hi", "final_response": {"text": "Hello"}})
    with _client(stores, FakeKnowledge()) as client:
        _ask(store, users, "How much annual leave do I get?", session_id="s-1", answered=True)
        _sign_in(client, EMPLOYEE)
        sessions = client.get("/sessions").json()
        others = client.get("/sessions/hr-chat/messages")

    assert [session["session_id"] for session in sessions] == ["s-1"]
    assert others.status_code == 404


def test_employees_rate_their_own_answers_only(stores) -> None:
    store, users = stores
    with _client(stores, FakeKnowledge()) as client:
        answered_id = _ask(store, users, "How much annual leave do I get?", session_id="s-1", answered=True)
        unanswered_id = _ask(store, users, "Can I bring my dog?", session_id="s-1", answered=False)
        _sign_in(client, HR)
        assert client.post(f"/interactions/{answered_id}/feedback", json={"rating": "up"}).status_code == 404
        _sign_in(client, EMPLOYEE)
        rated = client.post(f"/interactions/{answered_id}/feedback", json={"rating": "down", "comment": " Wrong "})
        not_an_answer = client.post(f"/interactions/{unanswered_id}/feedback", json={"rating": "down"})
        history = client.get("/sessions/s-1/messages").json()

    assert rated.json() == {"interaction_id": answered_id, "feedback": "down", "feedback_comment": "Wrong"}
    assert not_an_answer.status_code == 409
    assert (history[0]["feedback"], history[0]["feedback_comment"]) == ("down", "Wrong")


def test_answer_review_shows_every_question_without_who_asked(stores) -> None:
    store, users = stores
    with _client(stores, FakeKnowledge()) as client:
        sent_id = _send_to_hr(client, stores)
        answered_id = store.list_session("s-1")[0].id
        client.post(f"/interactions/{answered_id}/feedback", json={"rating": "down", "comment": "Wrong"})
        _sign_in(client, EMPLOYEE)
        assert client.get("/hr/review").status_code == 403
        _sign_in(client, HR)
        page = client.get("/hr/review").json()
        unhelpful = client.get("/hr/review", params={"show": "unhelpful"}).json()
        detail = client.get(f"/hr/review/{sent_id}").json()

    assert page["total"] == 2
    assert [item["interaction_id"] for item in page["items"]] == [sent_id, answered_id]
    assert [item["interaction_id"] for item in unhelpful["items"]] == [answered_id]
    assert unhelpful["items"][0]["feedback_comment"] == "Wrong"
    assert detail["country"] == "Finland"
    assert detail["escalation_status"] == "requested"
    assert detail["earlier_turns"] == [{"question": "How much annual leave do I get?", "answer": "You get 25 days."}]
    # Even for a question sent to HR, the review doesn't say who asked.
    text = json.dumps([page, detail])
    for detail_of_asker in ("Joonas", "joonas.laaksonen", "Senior Account Executive", "Tampere"):
        assert detail_of_asker not in text


def test_hr_reviews_an_answer_and_it_counts_down_from_the_overview(stores) -> None:
    store, users = stores
    with _client(stores, FakeKnowledge()) as client:
        interaction_id = _ask(store, users, "How much annual leave do I get?", session_id="s-1", answered=True)
        _sign_in(client, EMPLOYEE)
        client.post(f"/interactions/{interaction_id}/feedback", json={"rating": "down"})
        _sign_in(client, HR)
        before = client.get("/hr/overview").json()
        empty = client.post(f"/hr/review/{interaction_id}", json={"verdict": "corrected", "answer": "  "})
        reviewed = client.post(f"/hr/review/{interaction_id}", json={"verdict": "corrected", "answer": "28 days."})
        after = client.get("/hr/overview").json()
        missing = client.post("/hr/review/missing", json={"verdict": "correct"})

    assert before["unhelpful_to_review"] == 1
    assert empty.status_code == 422
    assert reviewed.json()["review_verdict"] == "corrected"
    assert reviewed.json()["review_answer"] == "28 days."
    assert reviewed.json()["reviewed_by"] == "Marju Ilves"
    assert after["unhelpful_to_review"] == 0
    assert missing.status_code == 404


def test_answer_review_takes_the_employees_name_out_of_what_was_said(stores) -> None:
    store, users = stores
    employee = users.get_by_email(EMPLOYEE["email"])
    interaction_id = store.log(
        {
            "session_id": "s-9",
            "user_id": employee.id,
            "question": "Hi, I'm Joonas Laaksonen. How much leave do I get?",
            "employee_context": employee.employee_context(),
            "final_response": {"text": "Hi Joonas, you get 25 days [1].", "sources": [], "answered": True},
        }
    )
    with _client(stores, FakeKnowledge()) as client:
        _sign_in(client, HR)
        detail = client.get(f"/hr/review/{interaction_id}").json()

    assert detail["question"] == "Hi, I'm [name]. How much leave do I get?"
    assert detail["answer"] == "Hi [name], you get 25 days [1]."
