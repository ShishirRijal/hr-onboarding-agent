from __future__ import annotations

from pathlib import Path

from ingestion.models import IngestedChunk
from ingestion.qdrant import stable_chunk_id
from retrieval.passages import PassageLibrary, locate_chunk

DOCUMENT = """# Leave Policy

## 2. Estonia

Employees get **28 calendar days** of annual leave.
Unused days carry over.

## 3. Finland

Employees get 25 working days.
Unused days carry over.
"""


def test_locate_chunk_ignores_whitespace_changes_from_the_splitter() -> None:
    start, end = locate_chunk(DOCUMENT, "Employees get **28 calendar days** of annual leave.  \nUnused days carry over.")

    assert DOCUMENT[start:end] == "Employees get **28 calendar days** of annual leave.\nUnused days carry over."


def test_locate_chunk_searches_from_its_own_section() -> None:
    start, _ = locate_chunk(DOCUMENT, "Unused days carry over.", "Leave Policy > 3. Finland")

    assert start > DOCUMENT.index("## 3. Finland")


def test_locate_chunk_returns_none_when_the_text_is_not_there() -> None:
    assert locate_chunk(DOCUMENT, "Employees get 40 days.") is None


def _chunk(text: str, **metadata: object) -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata={"source_doc": "leave_policy", "file_type": "markdown", "chunk_index": "0.0", **metadata},
    )


def test_passage_returns_the_whole_document_with_the_chunk_span(tmp_path: Path) -> None:
    (tmp_path / "leave.md").write_text(DOCUMENT, encoding="utf-8")
    chunk = _chunk("Employees get 25 working days.", source_file="leave.md", section_path="Leave Policy > 3. Finland")
    library = PassageLibrary([chunk], tmp_path)

    passage = library.passage(stable_chunk_id(chunk.metadata))

    assert passage.content == DOCUMENT
    assert passage.content[passage.highlight_start : passage.highlight_end] == "Employees get 25 working days."


def test_passage_falls_back_to_the_chunk_when_the_file_is_missing_or_outside_the_corpus(tmp_path: Path) -> None:
    chunks = [
        _chunk("Only the chunk.", source_file="missing.md"),
        _chunk("Not readable.", source_file="../secret.md", chunk_index="0.1"),
    ]
    (tmp_path.parent / "secret.md").write_text("secret", encoding="utf-8")
    library = PassageLibrary(chunks, tmp_path)

    for chunk in chunks:
        passage = library.passage(stable_chunk_id(chunk.metadata))
        assert passage.content == chunk.text
        assert (passage.highlight_start, passage.highlight_end) == (0, len(chunk.text))


def test_passage_returns_none_for_unknown_ids(tmp_path: Path) -> None:
    assert PassageLibrary([], tmp_path).passage("nope") is None
