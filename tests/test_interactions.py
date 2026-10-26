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
    interaction_id = store.log(_state("Can I bring my dog?", session_id="s-1", answered=False))

    assert store.get(interaction_id).escalation_status == "offered"
