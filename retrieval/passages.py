from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ingestion.models import IngestedChunk
from ingestion.qdrant import stable_chunk_id

WHITESPACE = re.compile(r"\s+")


@dataclass(slots=True)
class Passage:
    """A retrieved chunk shown in place: the whole source document plus where the chunk sits in it."""

    chunk_id: str
    source_doc: str | None
    source_file: str | None
    section_path: str | None
    content: str
    highlight_start: int | None
    highlight_end: int | None


class PassageLibrary:
    """Looks up chunks by id and finds them in their source documents."""

    def __init__(self, chunks: Sequence[IngestedChunk], corpus_dir: Path) -> None:
        self._chunks = {stable_chunk_id(chunk.metadata): chunk for chunk in chunks}
        self._corpus_dir = corpus_dir.resolve()
        self._documents: dict[str, str | None] = {}

    def add(self, chunk: IngestedChunk) -> None:
        """Makes a chunk added while the API runs (like an HR answer) openable as a source."""
        self._chunks[stable_chunk_id(chunk.metadata)] = chunk

    def passage(self, chunk_id: str) -> Passage | None:
        chunk = self._chunks.get(chunk_id)
        if chunk is None:
            return None

        metadata = chunk.metadata
        document = None
        if metadata.get("file_type") == "markdown":
            document = self._read_document(metadata.get("source_file"))
        span = locate_chunk(document, chunk.text, metadata.get("section_path")) if document else None

        if document is None or span is None:
            # Without its document the chunk is shown on its own.
            document, span = chunk.text, (0, len(chunk.text))

        return Passage(
            chunk_id=chunk_id,
            source_doc=metadata.get("source_doc"),
            source_file=metadata.get("source_file"),
            section_path=metadata.get("section_path"),
            content=document,
            highlight_start=span[0],
            highlight_end=span[1],
        )

    def _read_document(self, source_file: str | None) -> str | None:
        if not source_file:
            return None
        if source_file not in self._documents:
            path = (self._corpus_dir / source_file).resolve()
            inside = path.is_relative_to(self._corpus_dir)
            self._documents[source_file] = path.read_text(encoding="utf-8") if inside and path.is_file() else None
        return self._documents[source_file]


def locate_chunk(document: str, chunk_text: str, section_path: str | None = None) -> tuple[int, int] | None:
    """Returns the (start, end) character span of `chunk_text` in `document`.

    The markdown splitter rewrites whitespace, so both texts are compared with whitespace
    collapsed. The search starts at the chunk's own section heading, because overlapping
    chunks and repeated phrases can appear earlier in the document.
    """
    needle = WHITESPACE.sub(" ", chunk_text).strip()
    if not needle:
        return None

    collapsed, positions = _collapse_whitespace(document)
    section_start = _section_offset(document, section_path)
    from_index = _collapsed_index(positions, section_start)

    found = collapsed.find(needle, from_index)
    if found == -1:
        found = collapsed.find(needle)
    if found == -1:
        return None
    return positions[found], positions[found + len(needle) - 1] + 1


def _collapse_whitespace(text: str) -> tuple[str, list[int]]:
    """Collapses whitespace runs to one space, remembering each kept character's original offset."""
    characters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(text):
        if character.isspace():
            if characters and characters[-1] == " ":
                continue
            character = " "
        characters.append(character)
        positions.append(index)
    return "".join(characters), positions


def _collapsed_index(positions: list[int], offset: int) -> int:
    for index, position in enumerate(positions):
        if position >= offset:
            return index
    return 0


def _section_offset(document: str, section_path: str | None) -> int:
    """Offset of the deepest heading named in `section_path`, or 0 when it can't be found."""
    if not section_path:
        return 0
    offset = 0
    for heading in section_path.split(" > "):
        match = re.search(rf"^#+\s+{re.escape(heading.strip())}\s*$", document[offset:], re.MULTILINE)
        if match is None:
            break
        offset += match.start()
    return offset
