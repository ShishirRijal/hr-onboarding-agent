from __future__ import annotations

import os
from typing import Any

DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
INSUFFICIENT_CONTEXT_MARKER = "INSUFFICIENT_CONTEXT"
NO_ANSWER_MESSAGE = (
    "I could not find enough information in the HR knowledge base to answer this question reliably."
)
SYSTEM_PROMPT = f"""You are NordTech Solutions' HR onboarding assistant.
Answer only from the provided HR knowledge base excerpts.
If the excerpts do not contain enough information to answer the question, reply with exactly {INSUFFICIENT_CONTEXT_MARKER} and nothing else.
Do not invent policy details, dates, amounts, approvals, or contacts.
Keep the answer concise and practical."""


def generate_grounded_answer(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    if not chunks:
        return NO_ANSWER_MESSAGE

    client = llm or _load_default_llm(model=model)
    response = client.invoke(_build_messages(question, chunks))
    content = getattr(response, "content", response)
    return str(content).strip()


def is_insufficient_answer(text: str) -> bool:
    return INSUFFICIENT_CONTEXT_MARKER in text


def _load_default_llm(*, model: str = DEFAULT_ANSWER_MODEL) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to generate grounded answers.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("langchain-openai is required to generate grounded answers.") from exc

    return ChatOpenAI(model=model, temperature=0)


def _build_messages(question: str, chunks: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "\n\n".join(
                [
                    f"Question:\n{question.strip()}",
                    f"HR knowledge base excerpts:\n{_format_chunks(chunks)}",
                    "Answer with only the supported HR guidance. Do not include unsupported assumptions.",
                ]
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
