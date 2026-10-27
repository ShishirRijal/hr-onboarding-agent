from __future__ import annotations

from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from .answering import _format_chunks, _load_default_llm
from .state import ConversationTurn, DocumentGrade

# Grading sections is a reading task, not a writing one, so a small fast model is enough.
DEFAULT_GRADE_MODEL = "gpt-4.1-mini"
COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"

GRADE_PROMPT = """You check which HR document sections a search found are useful for answering an employee's question, before an answer is written from them. You get the question and numbered sections.

relevant: the numbers of the sections that state something needed to answer this specific question (a rule, amount, condition, approver, deadline or step for the thing asked about). Leave out sections that only share words or a general topic with it, and sections about other countries when the question is about one country.

coverage:
- "complete" when the relevant sections together answer everything asked.
- "partial" when they answer some of it, or answer it but the question also needs something they don't state.
- "none" when no section answers it.

missing: when coverage isn't "complete", a short search query for the information still needed, in the words an HR policy would use (for example "sick pay after day 9 Finland Kela"). Empty when coverage is "complete"."""


class _Grade(BaseModel):
    relevant: list[int] = Field(default_factory=list)
    coverage: Literal["complete", "partial", "none"]
    missing: str = ""


def grade_documents(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    history: Sequence[ConversationTurn] = (),
    llm: Any | None = None,
    model: str = DEFAULT_GRADE_MODEL,
) -> DocumentGrade:
    """Grades the found sections against the question (corrective RAG's retrieval
    evaluator): which ones help, whether together they answer it, and what to search for
    when they don't."""
    if not chunks:
        return {"relevant_chunk_ids": [], "coverage": COVERAGE_NONE, "missing": question, "searched_again": False}

    grader = (llm or _load_default_llm(model=model)).with_structured_output(_Grade)
    parts = []
    if history:
        conversation = "\n".join(f"Employee: {turn['question']}\nAssistant: {turn['answer']}" for turn in history)
        parts.append(f"Conversation so far:\n{conversation}")
    parts += [f"Question:\n{question.strip()}", f"Sections:\n{_format_chunks(chunks)}"]
    grade = grader.invoke([("system", GRADE_PROMPT), ("human", "\n\n".join(parts))])

    relevant = [chunks[number - 1]["chunk_id"] for number in dict.fromkeys(grade.relevant) if 0 < number <= len(chunks)]
    complete = grade.coverage == COVERAGE_COMPLETE and relevant
    return {
        "relevant_chunk_ids": relevant,
        "coverage": grade.coverage if relevant or grade.coverage == COVERAGE_NONE else COVERAGE_NONE,
        "missing": "" if complete else (grade.missing.strip() or question.strip()),
        "searched_again": False,
    }
