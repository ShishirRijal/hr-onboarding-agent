from __future__ import annotations

from pathlib import Path

from interactions import InteractionStore
from interactions.examples import answer_examples, preference_pairs


def _log(store: InteractionStore, question: str, answer: str) -> str:
    return store.log(
        {
            "session_id": "s-1",
            "user_id": "user-1",
            "question": question,
            "employee_context": {"employee_name": "Joonas Laaksonen", "employee_country": "Finland"},
            "final_response": {"text": answer, "sources": [{"chunk_id": "leave-3"}], "answered": True},
        }
    )


def test_rated_and_reviewed_answers_export_without_who_asked(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    _log(store, "How much leave do I get?", "25 days [1].")
    corrected = _log(store, "And in Estonia? Joonas here", "Hi Joonas, 25 days too [1].")
    store.log({"session_id": "s-2", "question": "Not rated", "final_response": {"text": "Hi", "answered": True}})
    store.record_feedback(corrected, rating="down", comment="Estonia is 28")
    store.record_review(corrected, verdict="corrected", answer="28 calendar days.", reviewed_by="Marju", reviewed_by_id="hr-1")

    examples = answer_examples(store)
    pairs = preference_pairs(examples)

    assert [example["question"] for example in examples] == ["And in Estonia? [name] here"]
    example = examples[0]
    assert example["country"] == "Finland"
    assert example["earlier_turns"] == [{"question": "How much leave do I get?", "answer": "25 days."}]
    assert example["sources"] == ["leave-3"]
    assert (example["feedback"], example["review_answer"]) == ("down", "28 calendar days.")
    assert "Joonas" not in str(examples) and "user-1" not in str(examples)
    assert pairs == [
        {
            "input": {
                "messages": [
                    {"role": "user", "content": "How much leave do I get?"},
                    {"role": "assistant", "content": "25 days."},
                    {"role": "user", "content": "And in Estonia? [name] here"},
                ]
            },
            "preferred_output": [{"role": "assistant", "content": "28 calendar days."}],
            "non_preferred_output": [{"role": "assistant", "content": "Hi [name], 25 days too."}],
        }
    ]
