from __future__ import annotations

from typing import Any

from agent.citations import strip_citations

from .inbox import redact_names
from .store import REVIEW_CORRECTED, InteractionStore, as_utc

# Employee ratings and HR reviews, exported as examples for evaluating and training the
# assistant. Like the answer review, they say nothing about who asked: only the country,
# with the employee's name taken out of what was said.


def answer_examples(store: InteractionStore) -> list[dict[str, Any]]:
    """Every answer with an employee rating or an HR review, with the chat before it."""
    examples = []
    for interaction in store.rated_or_reviewed():
        context = interaction.employee_context or {}
        earlier = []
        for turn in store.list_session(interaction.session_id) if interaction.session_id else []:
            if turn.id == interaction.id:
                break
            earlier.append(
                {
                    "question": redact_names(turn.question, context),
                    "answer": redact_names(strip_citations(turn.hr_answer or turn.answer), context),
                }
            )
        examples.append(
            {
                "interaction_id": interaction.id,
                "asked_at": as_utc(interaction.created_at).isoformat(),
                "country": context.get("employee_country") or context.get("office_country"),
                "earlier_turns": earlier,
                "question": redact_names(interaction.question, context),
                "answer": redact_names(interaction.answer, context),
                # The sections the answer cites, by chunk id, to rebuild what the assistant read.
                "sources": [source.get("chunk_id") for source in interaction.sources or []],
                "feedback": interaction.feedback,
                "feedback_comment": redact_names(interaction.feedback_comment or "", context) or None,
                "review_verdict": interaction.review_verdict,
                "review_answer": interaction.review_answer,
            }
        )
    return examples


def preference_pairs(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Answers HR rewrote, as pairs where HR's answer is preferred over the assistant's, in
    OpenAI's preference fine-tuning (DPO) format. Citations are left out of both, so the
    pair differs only in what it says."""
    pairs = []
    for example in examples:
        if example["review_verdict"] != REVIEW_CORRECTED or not example["review_answer"]:
            continue
        messages = []
        for turn in example["earlier_turns"]:
            messages += [{"role": "user", "content": turn["question"]}, {"role": "assistant", "content": turn["answer"]}]
        messages.append({"role": "user", "content": example["question"]})
        pairs.append(
            {
                "input": {"messages": messages},
                "preferred_output": [{"role": "assistant", "content": example["review_answer"]}],
                "non_preferred_output": [{"role": "assistant", "content": strip_citations(example["answer"])}],
            }
        )
    return pairs
