from __future__ import annotations

from ingestion.models import IngestedChunk

from retrieval.bm25_index import bm25_search, build_bm25_index, tokenize_text
from retrieval.models import RetrievalFilters


def test_tokenize_text_normalizes_words() -> None:
    assert tokenize_text("Annual leave in Estonia!") == ["annual", "leave", "in", "estonia"]


def test_bm25_search_ranks_relevant_chunk_first() -> None:
    chunks = [
        IngestedChunk(
            text="Annual leave in Estonia is 28 calendar days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "Estonia",
                "file_type": "markdown",
                "section_path": "Leave > Estonia",
                "chunk_index": "0.0",
            },
        ),
        IngestedChunk(
            text="Benefits are described in the guide.",
            metadata={
                "source_doc": "benefits_guide",
                "source_file": "benefits_perks_guide.md",
                "doc_type": "guide",
                "category": "Benefits",
                "country": "All",
                "file_type": "markdown",
                "section_path": "Benefits",
                "chunk_index": "1.0",
            },
        ),
    ]

    index = build_bm25_index(chunks)
    results = bm25_search(index, "How much annual leave do I get in Estonia?", top_k=5)

    assert results
    assert results[0].metadata["country"] == "Estonia"
    assert results[0].source == "bm25"
    assert results[0].score > 0


def test_bm25_search_applies_filters() -> None:
    chunks = [
        IngestedChunk(
            text="Annual leave in Estonia is 28 calendar days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "Estonia",
                "file_type": "markdown",
                "section_path": "Leave > Estonia",
                "chunk_index": "0.0",
            },
        ),
        IngestedChunk(
            text="Annual leave in Portugal is 22 working days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "Portugal",
                "file_type": "markdown",
                "section_path": "Leave > Portugal",
                "chunk_index": "0.1",
            },
        ),
        IngestedChunk(
            text="Unused annual leave can be carried over up to 5 days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "All",
                "file_type": "markdown",
                "section_path": "Leave > All Countries",
                "chunk_index": "0.2",
            },
        ),
    ]

    index = build_bm25_index(chunks)
    results = bm25_search(
        index,
        "How much annual leave do I get?",
        top_k=5,
        filters=RetrievalFilters(country="Portugal"),
    )

    assert len(results) == 2
    assert {result.metadata["country"] for result in results} == {"Portugal", "All"}
