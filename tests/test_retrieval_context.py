from __future__ import annotations

from types import SimpleNamespace

from ingestion.models import IngestedChunk
from retrieval.context import expand_with_neighbours, passage_chunk_ids

SECTION = "IT Setup Guide > 7. Equipment Ordering"
PIECES = [
    "Order peripherals through the IT request form.",
    "Requests are covered by a one-time budget of €300 per employee.",
    "budget of €300 per employee. Requests over €300 also need Ott Rebane (Finance Manager).",
    "Furniture is not ordered through IT.",
]


def _index():
    chunks = [
        IngestedChunk(text=text, metadata={"source_file": "it.md", "section_path": SECTION, "chunk_index": f"7.{i}"})
        for i, text in enumerate(PIECES)
    ]
    chunks.append(
        IngestedChunk(text="Payday is the 25th.", metadata={"source_file": "pay.md", "section_path": "Pay", "chunk_index": "3.0"})
    )
    return SimpleNamespace(chunks=chunks, chunk_ids=[f"it-{i}" for i in range(4)] + ["pay-0"])


def _found(chunk_id: str, position: str, file: str = "it.md", section: str = SECTION):
    return {
        "chunk_id": chunk_id,
        "text": "found",
        "metadata": {"source_file": file, "section_path": section, "chunk_index": position},
    }


def test_found_pieces_are_read_with_their_neighbours_without_repeating_the_overlap() -> None:
    [passage] = expand_with_neighbours(_index(), [_found("it-1", "7.1")])

    assert passage["chunk_id"] == "it-1"
    assert passage_chunk_ids(passage) == ["it-0", "it-1", "it-2"]
    assert "Ott Rebane" in passage["text"]
    assert passage["text"].count("budget of €300 per employee") == 1


def test_neighbouring_finds_become_one_passage_cited_by_the_better_ranked_piece() -> None:
    passages = expand_with_neighbours(_index(), [_found("it-3", "7.3"), _found("pay-0", "3.0", "pay.md", "Pay"), _found("it-1", "7.1")])

    assert [passage["chunk_id"] for passage in passages] == ["it-3", "pay-0"]
    assert passage_chunk_ids(passages[0]) == ["it-0", "it-1", "it-2", "it-3"]


def test_pieces_outside_the_index_are_kept_as_they_are() -> None:
    hr_answer = {"chunk_id": "hr-1", "text": "Dogs are welcome on Fridays.", "metadata": {}}

    assert expand_with_neighbours(_index(), [hr_answer]) == [hr_answer]
    assert expand_with_neighbours(SimpleNamespace(), [hr_answer]) == [hr_answer]
