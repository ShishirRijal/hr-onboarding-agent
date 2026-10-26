from __future__ import annotations

import os
from typing import Any, Sequence

from .state import ConversationTurn, EmployeeContext

DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
INSUFFICIENT_CONTEXT_MARKER = "INSUFFICIENT_CONTEXT"
NO_ANSWER_MESSAGE = (
    "I could not find enough information in the HR knowledge base to answer this question reliably."
)
SYSTEM_PROMPT = f"""You are NordTech Solutions' HR onboarding assistant, answering an employee in a chat.

Answer only from the HR document excerpts you are given. Do not invent policy details, dates, amounts, approvals or contacts.
If the excerpts do not contain enough information to answer the question, reply with exactly {INSUFFICIENT_CONTEXT_MARKER} and nothing else.

Write like a helpful colleague: warm, plain and to the point. Start with the direct answer, then only the details or steps they need, using a short list for steps.
When a rule differs by country, give the one for the employee's country.
If the question has several parts and the documents fully answer some of them, answer those and say the rest isn't covered in the HR documents. If the documents only mention the topic without answering what was asked, reply with exactly {INSUFFICIENT_CONTEXT_MARKER}.
Never write your own reply saying the documents don't have the answer or that they should ask HR: reply with exactly {INSUFFICIENT_CONTEXT_MARKER} instead, and the app will offer to send the question to HR.
Never mention "excerpts", "context" or a "knowledge base". Refer to documents by name, such as the Leave & Absence Policy."""


def generate_grounded_answer(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    history: Sequence[ConversationTurn] = (),
    employee_context: EmployeeContext | None = None,
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    if not chunks:
        return NO_ANSWER_MESSAGE

    client = llm or _load_default_llm(model=model)
    response = client.invoke(_build_messages(question, chunks, history, employee_context or {}))
    content = getattr(response, "content", response)
    return str(content).strip()


def is_insufficient_answer(text: str) -> bool:
    return INSUFFICIENT_CONTEXT_MARKER in text


def describe_employee(employee_context: EmployeeContext) -> str:
    """Where the employee works, in words that follow "an employee" or "the employee is":
    "based in Tallinn, Estonia" or "working remotely"."""
    country = employee_context.get("employee_country") or employee_context.get("office_country")
    location = employee_context.get("office_location")
    if country == "Remote" or location == "Remote":
        return "working remotely"
    place = ", ".join(part for part in (location, country) if part)
    return f"based in {place}" if place else ""


def history_messages(history: Sequence[ConversationTurn]) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for turn in history:
        messages.append(("human", turn["question"]))
        messages.append(("ai", turn["answer"]))
    return messages


def _load_default_llm(*, model: str = DEFAULT_ANSWER_MODEL, temperature: float = 0) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to generate grounded answers.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("langchain-openai is required to generate grounded answers.") from exc

    return ChatOpenAI(model=model, temperature=temperature)


def _build_messages(
    question: str,
    chunks: list[dict[str, Any]],
    history: Sequence[ConversationTurn],
    employee_context: EmployeeContext,
) -> list[tuple[str, str]]:
    employee = describe_employee(employee_context)
    # Earlier turns come first so follow-ups like "and in Finland?" read naturally.
    return [
        ("system", SYSTEM_PROMPT),
        *history_messages(history),
        (
            "human",
            "\n\n".join(
                part
                for part in [
                    f"The employee is {employee}." if employee else "",
                    f"Question:\n{question.strip()}",
                    f"HR document excerpts:\n{_format_chunks(chunks)}",
                ]
                if part
            ),
        ),
    ]


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    formatted: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {}) or {}
        source_parts = [
            str(metadata.get("source_file") or metadata.get("source_doc") or "unknown source"),
        ]
        location = metadata.get("section_path") or metadata.get("page_number") or metadata.get("row_number")
        if location is not None:
            source_parts.append(f"location: {location}")

        text = str(chunk.get("text", "")).strip()
        formatted.append(f"[{index}] Source: {' | '.join(source_parts)}\n{text}")

    return "\n\n".join(formatted)
