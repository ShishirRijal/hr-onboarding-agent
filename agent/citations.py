from __future__ import annotations

import re
from typing import Any

from .state import AnswerSource

# The answer model cites the numbered sections it was given, as "[2]", "[1][3]" or "[1, 3]".
# A "[2](...)" is a Markdown link, not a citation.
_CITATION = re.compile(r"[ \t]*\[(?:sources?\s*)?(\d+(?:\s*,\s*\d+)*)\](?!\()", re.IGNORECASE)
_REPEATED = re.compile(r"(\[\d+\])(?:\1)+")


def number_citations(text: str, chunks: list[dict[str, Any]]) -> tuple[str, list[AnswerSource]]:
    """Renumbers the answer's citations to the sources it actually cites, in the order it
    first cites them: the first source cited is [1], and every citation of it stays [1],
    even when the model cited two sections of it under different numbers. Returns the
    renumbered text and its sources, where [n] is sources[n - 1]."""
    numbers: dict[tuple[Any, ...], int] = {}
    sources: list[AnswerSource] = []

    def renumber(match: re.Match[str]) -> str:
        cited: list[int] = []
        for value in re.split(r"\s*,\s*", match.group(1)):
            position = int(value)
            if not 0 < position <= len(chunks):
                continue
            chunk = chunks[position - 1]
            key = source_key(chunk)
            if key not in numbers:
                numbers[key] = len(sources) + 1
                sources.append(answer_source(chunk))
            if numbers[key] not in cited:
                cited.append(numbers[key])
        return "".join(f"[{number}]" for number in sorted(cited))

    text = _REPEATED.sub(r"\1", _CITATION.sub(renumber, text))
    return text, sources


def has_citations(text: str) -> bool:
    return bool(_CITATION.search(text))


def strip_citations(text: str) -> str:
    """The answer without its citations, for earlier turns shown to a model: their numbers
    point to sections from another search."""
    return _CITATION.sub("", text)


def source_key(chunk: dict[str, Any]) -> tuple[Any, ...]:
    """What makes two passages the same source: the same section of the same document."""
    metadata = chunk.get("metadata", {}) or {}
    return (
        metadata.get("source_file"),
        metadata.get("source_doc"),
        metadata.get("section_path"),
        metadata.get("page_number"),
        metadata.get("row_number"),
    )


def answer_source(chunk: dict[str, Any]) -> AnswerSource:
    metadata = chunk.get("metadata", {}) or {}
    source: AnswerSource = {
        "chunk_id": str(chunk.get("chunk_id", "")).strip(),
        "score": float(chunk.get("score", 0.0) or 0.0),
    }
    for key in ("source_doc", "source_file", "section_path", "page_number", "row_number"):
        value = metadata.get(key)
        if value is not None:
            source[key] = value
    return source
