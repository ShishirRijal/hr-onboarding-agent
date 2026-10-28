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

Answer only from the HR document excerpts you are given. Every sentence must be backed by them: no tips, reminders, general advice or next steps the documents don't state, and no invented policy details, dates, amounts, approvals or contacts.
Include every condition, exception, approval, limit and deadline the documents attach to the answer, even when it makes the answer longer.
Show where each fact comes from: right after every sentence and every list item that states something from the documents, put the number of the excerpt it comes from in square brackets, like [2], or [1][3] when it draws on two. Each one needs its own, not just the last line. Greetings need none.

Write like a helpful colleague: warm, plain and to the point. Start with the direct answer, making sure it agrees with the details that follow. Use a short list only for steps the documents themselves give. Don't end with offers of further help.
If the question names a country, answer for that country, even when the employee works somewhere else. Otherwise, when a rule differs by country, give the one for the employee's country.
If the question has several parts and the documents fully answer some of them, answer those and say the rest isn't covered in the HR documents.

If the excerpts don't answer what was asked, reply with exactly {INSUFFICIENT_CONTEXT_MARKER} and nothing else, and the app will offer to send the question to HR. That includes when the documents only mention the topic, say it isn't covered, or say it's handled case by case. Never write that reply in your own words or suggest asking HR yourself.
Never mention "excerpts", "context" or a "knowledge base". Refer to documents by name, such as the Leave & Absence Policy."""


def generate_grounded_answer(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    history: Sequence[ConversationTurn] = (),
    summary: str = "",
    employee_context: EmployeeContext | None = None,
    country: str | None = None,
    draft: str | None = None,
    feedback: str | None = None,
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    if not chunks:
        return NO_ANSWER_MESSAGE

    client = llm or _load_default_llm(model=model)
    messages = _build_messages(question, chunks, history, employee_context or {}, country, summary)
    if draft and feedback:
        # A rewrite after review: the model sees its draft and what to fix, and answers again.
        messages += [("ai", draft), ("human", feedback)]
    response = client.invoke(messages)
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


def first_name(employee_context: EmployeeContext) -> str:
    return (employee_context.get("employee_name") or "").split(" ")[0]


def history_messages(history: Sequence[ConversationTurn], summary: str = "") -> list[tuple[str, str]]:
    """The chat so far as chat messages: the summary of older turns, then the latest turns."""
    messages: list[tuple[str, str]] = [("system", summary_note(summary))] if summary else []
    for turn in history:
        messages.append(("human", turn["question"]))
        messages.append(("ai", turn["answer"]))
    return messages


def summary_note(summary: str) -> str:
    return f"Summary of earlier in this chat:\n{summary}" if summary else ""


def conversation_text(history: Sequence[ConversationTurn], summary: str = "") -> str:
    """The chat so far as text, for models that get it inside one message."""
    turns = "\n".join(f"Employee: {turn['question']}\nAssistant: {turn['answer']}" for turn in history)
    parts = [summary_note(summary), f"Latest turns:\n{turns}" if summary else f"Conversation so far:\n{turns}"]
    return "\n\n".join(part for part in parts if part) if turns or summary else ""


def _load_default_llm(*, model: str = DEFAULT_ANSWER_MODEL, temperature: float = 0) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to generate grounded answers.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("langchain-openai is required to generate grounded answers.") from exc

    # stream_usage keeps token counts when LangGraph streams the call, so usage is always tracked.
    return ChatOpenAI(model=model, temperature=temperature, stream_usage=True)


def _build_messages(
    question: str,
    chunks: list[dict[str, Any]],
    history: Sequence[ConversationTurn],
    employee_context: EmployeeContext,
    country: str | None = None,
    summary: str = "",
) -> list[tuple[str, str]]:
    employee = describe_employee(employee_context)
    name = first_name(employee_context)
    # Earlier turns come first so follow-ups like "and in Finland?" read naturally.
    return [
        ("system", SYSTEM_PROMPT),
        *history_messages(history, summary),
        (
            "human",
            "\n\n".join(
                part
                for part in [
                    f"The employee is {name + ', ' if name else ''}{employee}." if employee else "",
                    _country_note(country, employee_context),
                    _greeting_note(name, first_message=not history and not summary),
                    f"Question:\n{question.strip()}",
                    f"HR document excerpts:\n{_format_chunks(chunks)}",
                ]
                if part
            ),
        ),
    ]


def _country_note(country: str | None, employee_context: EmployeeContext) -> str:
    # Without this, an employee in Porto asking about Estonia gets "not covered": the model
    # reads Estonia's rules as not applying to them.
    own = employee_context.get("employee_country") or employee_context.get("office_country")
    if not country or not own or country == own:
        return ""
    return f"They're asking about {country}, so answer with {country}'s rules, not their own country's."


def _greeting_note(name: str, *, first_message: bool) -> str:
    # Greeting once per chat reads friendly; using the name in every answer reads scripted.
    if name and first_message:
        note = f'This is their first message in this chat: open with "Hi {name}," and then answer.'
    elif first_message:
        note = "Answer directly, without a greeting."
    else:
        note = "You're mid-conversation: answer directly, without a greeting or their name."
    return note + " End when the answer is complete, with no closing offer of more help."


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
