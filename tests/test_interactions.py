from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from interactions import InteractionStore


def _state(question: str, *, session_id: str, answered: bool) -> dict[str, object]:
    state: dict[str, object] = {
        "session_id": session_id,
        "question": question,
        "employee_context": {"employee_country": "Estonia"},
        "confidence_score": 0.7 if answered else 0.0,
        "confidence_label": "medium" if answered else "low",
        "retrieval_debug": {"retrieved_count": 5},
        "confidence_debug": {"score_basis": "dense"},
        "final_response": {
            "text": "28 calendar days." if answered else "Not in the HR documents. Ask HR?",
            "sources": [{"chunk_id": "chunk-1", "source_file": "leave_absence_policy.md"}] if answered else [],
            "answered": answered,
        },
    }
    if not answered:
        state["hr_handoff"] = {"reason": "answer_declined", "draft_answer": "", "candidate_sources": []}
    return state


def test_store_logs_answered_and_unanswered_questions(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'nested' / 'interactions.db'}")

    answered_id = store.log(_state("How much annual leave do I get?", session_id="s-1", answered=True))
    unanswered_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))
    store.log(_state("Other session question", session_id="s-2", answered=True))

    session = store.list_session("s-1")
    assert [interaction.id for interaction in session] == [answered_id, unanswered_id]
    answered, unanswered = session
    assert answered.answered is True
    assert answered.escalation_status is None
    assert answered.sources[0]["source_file"] == "leave_absence_policy.md"
    assert answered.employee_context == {"employee_country": "Estonia"}
    assert unanswered.answered is False
    assert unanswered.escalation_status == "offered"
    assert unanswered.escalated is False
    assert unanswered.escalation_reason == "answer_declined"
    assert unanswered.hr_handoff["reason"] == "answer_declined"
    assert store.list_escalations() == []


def test_hr_choice_is_recorded_on_the_interaction(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    asked_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))
    declined_id = store.log(_state("Is there parking?", session_id="s-1", answered=False))

    asked = store.record_hr_choice(asked_id, ask_hr=True)
    declined = store.record_hr_choice(declined_id, ask_hr=False)

    assert asked.escalation_status == "requested"
    assert asked.escalated is True
    assert asked.escalated_at is not None
    assert declined.escalation_status == "declined"
    assert declined.escalated is False
    assert [interaction.id for interaction in store.list_escalations()] == [asked_id]
    assert store.record_hr_choice("missing", ask_hr=True) is None


def test_unanswered_hr_offer_is_dismissed_when_the_employee_asks_something_else(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    offered_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))
    chosen_id = store.log(_state("Is there parking?", session_id="s-2", answered=False))
    store.record_hr_choice(chosen_id, ask_hr=True)

    store.log(_state("How much leave do I get?", session_id="s-1", answered=True))
    store.log(_state("And in Finland?", session_id="s-2", answered=True))

    assert store.get(offered_id).escalation_status == "dismissed"
    assert store.get(offered_id).escalated is False
    assert store.get(chosen_id).escalation_status == "requested"


def test_contact_details_are_kept_only_when_the_question_goes_to_hr(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    sent_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))
    declined_id = store.log(_state("Is there parking?", session_id="s-2", answered=False))

    store.record_hr_choice(sent_id, ask_hr=True, name="Shishir Rijal", email="shishir@nordtech.test")
    store.record_hr_choice(declined_id, ask_hr=False, name="Shishir Rijal", email="shishir@nordtech.test")

    sent = store.get(sent_id)
    assert (sent.employee_name, sent.employee_email) == ("Shishir Rijal", "shishir@nordtech.test")
    declined = store.get(declined_id)
    assert (declined.employee_name, declined.employee_email) == (None, None)


def test_pending_hr_requests_are_the_ones_not_yet_emailed(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    first_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))
    second_id = store.log(_state("Is there parking?", session_id="s-2", answered=False))
    store.log(_state("Bike storage?", session_id="s-3", answered=False))
    store.record_hr_choice(first_id, ask_hr=True, name="A", email="a@nordtech.test")
    store.record_hr_choice(second_id, ask_hr=True, name="B", email="b@nordtech.test")

    assert [item.id for item in store.pending_hr_requests()] == [first_id, second_id]
    store.mark_hr_notified([first_id])
    assert [item.id for item in store.pending_hr_requests()] == [second_id]
    assert store.get(first_id).hr_notified_at is not None


def test_answered_questions_cannot_be_sent_to_hr(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    answered_id = store.log(_state("How much annual leave do I get?", session_id="s-1", answered=True))

    with pytest.raises(ValueError):
        store.record_hr_choice(answered_id, ask_hr=True)


def test_store_adds_new_columns_to_an_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "interactions.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE interactions (id VARCHAR(36) PRIMARY KEY, created_at DATETIME, session_id VARCHAR(64), "
            "question TEXT, answer TEXT, escalated BOOLEAN, escalation_reason VARCHAR(64), confidence_score FLOAT, "
            "confidence_label VARCHAR(16), employee_context JSON, sources JSON, escalation JSON, debug JSON)"
        )

    store = InteractionStore(f"sqlite:///{database}")
    interaction_id = store.log({**_state("Can I bring my dog?", session_id="s-1", answered=False), "user_id": "u-1"})

    assert store.get(interaction_id).escalation_status == "offered"
    assert store.get(interaction_id).user_id == "u-1"
    assert store.get(interaction_id).hr_answer is None


def test_hr_answer_is_recorded_once_and_left_out_of_the_digest(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    asked_id = store.log({**_state("Can I bring my dog?", session_id="s-1", answered=False), "user_id": "u-1"})
    store.record_hr_choice(asked_id, ask_hr=True, name="A", email="a@nordtech.test")

    answered = store.record_hr_answer(
        asked_id, answer="Fridays only.", answered_by="Marju Ilves", answered_by_id="hr-1", country="All", chunk_id="c-1"
    )

    assert answered.escalation_status == "answered"
    assert answered.hr_answered_at is not None
    assert [item.id for item in store.hr_questions("answered")] == [asked_id]
    assert store.hr_questions("requested") == []
    assert store.pending_hr_requests() == []
    with pytest.raises(ValueError):
        store.record_hr_answer(
            asked_id, answer="Again.", answered_by="Marju Ilves", answered_by_id="hr-1", country="All", chunk_id=None
        )


def test_users_chats_are_listed_newest_first_with_unread_hr_replies(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    first_id = store.log({**_state("Can I bring my dog?", session_id="s-1", answered=False), "user_id": "u-1"})
    store.log({**_state("How much leave?", session_id="s-2", answered=True), "user_id": "u-1"})
    store.log({**_state("Someone else's chat", session_id="s-3", answered=True), "user_id": "u-2"})
    store.record_hr_choice(first_id, ask_hr=True)
    store.record_hr_answer(
        first_id, answer="Fridays only.", answered_by="Marju Ilves", answered_by_id="hr-1", country="All", chunk_id=None
    )

    # The HR reply is newer than the other chat, so its chat moves to the top.
    chats = store.list_user_sessions("u-1")
    assert [(chat.session_id, chat.title, chat.unread_hr_replies) for chat in chats] == [
        ("s-1", "Can I bring my dog?", 1),
        ("s-2", "How much leave?", 0),
    ]
    assert store.session_owners("s-1") == {"u-1"}
    assert store.session_owners("new") == set()

    store.mark_hr_answers_read("s-1")
    assert store.list_user_sessions("u-1")[0].unread_hr_replies == 0


def test_feedback_is_kept_on_answers_with_a_comment_only_for_a_thumbs_down(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    answered_id = store.log(_state("How much annual leave do I get?", session_id="s-1", answered=True))
    unanswered_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))

    down = store.record_feedback(answered_id, rating="down", comment="It's 28 days, not 25.")
    assert (down.feedback, down.feedback_comment) == ("down", "It's 28 days, not 25.")
    assert down.feedback_at is not None
    up = store.record_feedback(answered_id, rating="up", comment="ignored")
    assert (up.feedback, up.feedback_comment) == ("up", None)
    cleared = store.record_feedback(answered_id, rating=None)
    assert (cleared.feedback, cleared.feedback_at) == (None, None)
    with pytest.raises(ValueError):
        store.record_feedback(unanswered_id, rating="down")
    assert store.record_feedback("missing", rating="up") is None


def test_review_lists_questions_newest_first_by_kind(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    first = store.log(_state("Leave?", session_id="s-1", answered=True))
    second = store.log(_state("Dog?", session_id="s-2", answered=False))
    third = store.log(_state("Parking?", session_id="s-3", answered=True))
    store.record_feedback(first, rating="down")
    store.record_feedback(third, rating="up")

    def ids(show: str) -> list[str]:
        return [interaction.id for interaction in store.review_page(show)[0]]

    assert ids("all") == [third, second, first]
    assert ids("unhelpful") == [first]
    assert ids("helpful") == [third]
    assert ids("not_answered") == [second]
    page, total = store.review_page("all", offset=1, limit=1)
    assert ([interaction.id for interaction in page], total) == ([second], 3)
    assert store.count_unhelpful_to_review() == 1

    store.record_review(first, verdict="corrected", answer="28 days.", reviewed_by="Marju Ilves", reviewed_by_id="hr-1")
    assert ids("reviewed") == [first]
    assert store.count_unhelpful_to_review() == 0
    assert [interaction.id for interaction in store.rated_or_reviewed()] == [first, third]


def test_reviewing_again_replaces_the_review(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    interaction_id = store.log(_state("Leave?", session_id="s-1", answered=True))

    store.record_review(interaction_id, verdict="corrected", answer="28 days.", reviewed_by="Marju", reviewed_by_id="hr-1")
    review = store.record_review(interaction_id, verdict="correct", answer="ignored", reviewed_by="Marju", reviewed_by_id="hr-1")

    assert (review.review_verdict, review.review_answer) == ("correct", None)
    assert store.record_review("missing", verdict="correct", answer=None, reviewed_by="M", reviewed_by_id="hr-1") is None


def test_redact_names_takes_out_the_full_and_first_name() -> None:
    from interactions.inbox import redact_names

    context = {"employee_name": "Alex Rinne"}
    assert redact_names("Hi Alex, ALEX RINNE asked. Alexander isn't them.", context) == (
        "Hi [name], [name] asked. Alexander isn't them."
    )
    assert redact_names("No name here.", {}) == "No name here."
