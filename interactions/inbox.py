from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

from .store import Interaction

# How a question sent to HR is described to HR, shared by the daily email and the HR inbox.

# Why the assistant couldn't answer, in words for HR (keys match escalation_reason).
REASONS = {
    "no_documents_found": "No HR document matched the question.",
    "no_sources": "No HR document matched the question.",
    "low_confidence": "The closest HR documents weren't a close enough match to answer from.",
    "answer_declined": "The HR documents mention the topic but don't answer the question.",
    "no_relevant_sections": "Two searches found sections on nearby topics, but none that answer the question.",
}
DEFAULT_REASON = "The HR documents don't cover this."
NO_DOCUMENT_TOPIC = "Not near any document"
DOCUMENT_TITLE_PREFIX = "NordTech Solutions — "


NAME_PLACEHOLDER = "[name]"


def redact_names(text: str, employee_context: dict[str, Any]) -> str:
    """The text without the employee's name, for places that don't say who asked: answers
    greet employees by first name, and people mention their own."""
    names = str(employee_context.get("employee_name") or "").split()
    # The full name first, so "Joonas Laaksonen" becomes one placeholder, not two.
    for name in [" ".join(names), *names]:
        if len(name) > 1:
            text = re.sub(rf"\b{re.escape(name)}\b", NAME_PLACEHOLDER, text, flags=re.IGNORECASE)
    return text


def reason_text(reason: str | None) -> str:
    return REASONS.get(reason or "", DEFAULT_REASON)


def documents_checked(handoff: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for source in handoff.get("candidate_sources", []) or []:
        # Section paths start with the document's title: "NordTech Solutions — Leave & Absence Policy > …".
        title = str(source.get("section_path") or source.get("source_file") or "").split(" > ")[0]
        title = title.removeprefix(DOCUMENT_TITLE_PREFIX).strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def workplace(employee_context: dict[str, Any]) -> str:
    country = employee_context.get("employee_country") or employee_context.get("office_country")
    location = employee_context.get("office_location")
    if country == "Remote":
        return "Remote"
    return ", ".join(part for part in (location, country) if part) or "Not given"


def question_topic(interaction: Interaction) -> str:
    """The part of the documents a question came closest to: the best match's document and
    top-level section, like "Employee Handbook v2.1 › 6. Office Life"."""
    sources = (interaction.hr_handoff or {}).get("candidate_sources") or []
    if not sources:
        return NO_DOCUMENT_TOPIC
    parts = str(sources[0].get("section_path") or sources[0].get("source_file") or "").split(" > ")
    parts[0] = parts[0].removeprefix(DOCUMENT_TITLE_PREFIX).strip()
    return " › ".join(part for part in parts[:2] if part) or NO_DOCUMENT_TOPIC


def common_topics(interactions: Sequence[Interaction], *, limit: int = 5) -> list[tuple[str, int]]:
    """Where unanswered questions cluster, most frequent first: the gaps worth documenting."""
    return Counter(question_topic(interaction) for interaction in interactions).most_common(limit)
