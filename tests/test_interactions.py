from __future__ import annotations

from pathlib import Path

from interactions import InteractionStore


def _state(question: str, *, session_id: str, escalated: bool) -> dict[str, object]:
    state: dict[str, object] = {
        "session_id": session_id,
        "question": question,
        "employee_context": {"employee_country": "Estonia"},
        "confidence_score": 0.2 if escalated else 0.7,
        "confidence_label": "low" if escalated else "medium",
        "retrieval_debug": {"retrieved_count": 5},
        "confidence_debug": {"score_basis": "dense"},
        "final_response": {
            "text": "Logged for HR." if escalated else "28 calendar days.",
            "sources": [] if escalated else [{"chunk_id": "chunk-1", "source_file": "leave_absence_policy.md"}],
            "escalated": escalated,
        },
    }
    if escalated:
        state["escalation"] = {"reason": "answer_declined", "draft_answer": "", "candidate_sources": []}
    return state


def test_store_logs_answers_and_escalations(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'nested' / 'interactions.db'}")

    answered_id = store.log(_state("How much annual leave do I get?", session_id="s-1", escalated=False))
    escalated_id = store.log(_state("Can I bring my dog?", session_id="s-1", escalated=True))
    store.log(_state("Other session question", session_id="s-2", escalated=False))

    session = store.list_session("s-1")
    assert [interaction.id for interaction in session] == [answered_id, escalated_id]
    assert session[0].answer == "28 calendar days."
    assert session[0].sources[0]["source_file"] == "leave_absence_policy.md"
    assert session[0].employee_context == {"employee_country": "Estonia"}

    escalations = store.list_escalations()
    assert [interaction.id for interaction in escalations] == [escalated_id]
    assert escalations[0].escalation_reason == "answer_declined"
    assert escalations[0].debug["confidence"] == {"score_basis": "dense"}
