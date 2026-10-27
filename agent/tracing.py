from __future__ import annotations

import os
import re
from typing import Any, Iterable

# Traces of each agent run go to Langfuse when its keys are set (LANGFUSE_PUBLIC_KEY,
# LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL). They hold employees' questions, so names and
# email addresses are masked before anything leaves the app.

NAME_PLACEHOLDER = "[name]"
EMAIL_PLACEHOLDER = "[email]"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Details about the employee that together could say who they are; their country stays,
# since it decides which rules apply.
_PERSONAL_FIELDS = frozenset({"employee_id", "employee_name", "department", "role", "date_of_joining"})

_names: re.Pattern[str] | None = None
_enabled = False


def langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY", "").strip() and os.getenv("LANGFUSE_SECRET_KEY", "").strip())


def set_masked_names(names: Iterable[str]) -> None:
    """The names to mask: each full name and its parts, longest first, so "Joonas
    Laaksonen" becomes one placeholder rather than two."""
    global _names
    words = {name.strip() for name in names if name.strip()}
    words |= {part for name in words for part in name.split() if len(part) > 1}
    ordered = sorted(words, key=len, reverse=True)
    _names = re.compile(r"\b(?:" + "|".join(map(re.escape, ordered)) + r")\b", re.IGNORECASE) if ordered else None


def mask(*, data: Any, **kwargs: Any) -> Any:
    """Langfuse's mask hook: runs on every input, output and metadata value it sends."""
    if isinstance(data, str):
        text = _EMAIL.sub(EMAIL_PLACEHOLDER, data)
        return _names.sub(NAME_PLACEHOLDER, text) if _names else text
    if isinstance(data, dict):
        return {key: "[redacted]" if key in _PERSONAL_FIELDS else mask(data=value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask(data=item) for item in data]
    return data


def start_tracing(names: Iterable[str]) -> bool:
    """Sets up the Langfuse client, if its keys are set. Returns whether tracing is on."""
    global _enabled
    if not langfuse_configured():
        return False
    from langfuse import Langfuse

    set_masked_names(names)
    Langfuse(mask=mask)
    _enabled = True
    return True


def tracing_callbacks() -> list[Any]:
    """A Langfuse handler for one run, or nothing when tracing is off."""
    if not _enabled:
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]


def trace_metadata(*, session_id: str | None, user_id: str | None, tags: list[str]) -> dict[str, Any]:
    # The user is their account id, not their name, so a chat can be followed in Langfuse
    # without saying who it was.
    metadata: dict[str, Any] = {"langfuse_tags": tags}
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if user_id:
        metadata["langfuse_user_id"] = user_id
    return metadata


def stop_tracing() -> None:
    """Sends what's left before the app exits."""
    global _enabled
    if not _enabled:
        return
    from langfuse import get_client

    get_client().shutdown()
    _enabled = False
