from __future__ import annotations

from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from .answering import _format_chunks, _load_default_llm, conversation_text
from .state import AnswerCheck, ConversationTurn

# A stronger model than the one writing, so it doesn't wave its own kind of draft through.
DEFAULT_CHECK_MODEL = "gpt-4.1"

CHECK_PROMPT = """You review a draft answer from NordTech Solutions' HR assistant before the employee sees it. You get the employee's question, the HR document sections the draft was written from, and the draft. The numbers in square brackets in the draft cite the sections it used.

reasoning: first, in two or three sentences, say exactly what was asked and what the sections say about that specific thing.

verdict:
- "answered" when the sections contain the specific information asked for and the draft gives it. If the question has several parts, the sections answering one of them counts.
- "not_answered" when the sections don't contain the specific information asked for. Mentioning the topic is not answering it: a draft that summarises related policy, says the documents don't cover it, says it's handled case by case, or tells them to contact HR or their manager is "not_answered", however politely it's worded.

unsupported_claims: factual claims in the draft (numbers, rules, names, steps, deadlines) that the sections don't support. Ignore greetings.

missing_details: only for "answered". Conditions, exceptions, approvers, limits or deadlines that the sections attach to the exact thing asked about and that the draft leaves out, quoted briefly in the sections' words. Never list that something isn't covered or that they should contact someone, and never list information about other topics, countries, or items the question didn't ask about. Usually this list is empty."""


class _CheckDecision(BaseModel):
    reasoning: str
    verdict: Literal["answered", "not_answered"]
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_details: list[str] = Field(default_factory=list)


def check_answer(
    question: str,
    chunks: list[dict[str, Any]],
    answer: str,
    *,
    history: Sequence[ConversationTurn] = (),
    summary: str = "",
    llm: Any | None = None,
    model: str = DEFAULT_CHECK_MODEL,
) -> AnswerCheck:
    """Reviews a draft against its sections: does it answer the question, is every claim
    backed, and does it leave out a condition that matters (Self-RAG's critique step)."""
    reviewer = (llm or _load_default_llm(model=model)).with_structured_output(_CheckDecision)
    parts = []
    if history or summary:
        parts.append(conversation_text(history, summary))
    parts += [
        f"Question:\n{question.strip()}",
        f"HR document sections:\n{_format_chunks(chunks)}",
        f"Draft answer:\n{answer.strip()}",
    ]
    decision = reviewer.invoke([("system", CHECK_PROMPT), ("human", "\n\n".join(parts))])
    answered = decision.verdict == "answered"
    return {
        "answers_question": answered,
        "unsupported_claims": list(decision.unsupported_claims),
        "missing_details": list(decision.missing_details) if answered else [],
        "revised": False,
    }


def revision_feedback(check: AnswerCheck) -> str:
    """What to fix, in words the answer model can act on."""
    lines = ["A reviewer checked your draft against the HR document sections. Rewrite the answer to fix this:"]
    for claim in check["unsupported_claims"]:
        lines.append(f"- Remove or correct, because the sections don't support it: {claim}")
    for detail in check["missing_details"]:
        lines.append(f"- Add, because the sections state it and it matters here: {detail}")
    lines.append("Keep citing each fact with its section's number in square brackets.")
    return "\n".join(lines)
