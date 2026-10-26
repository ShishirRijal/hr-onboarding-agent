from __future__ import annotations

from pathlib import Path

from ingestion.manifest import ALLOWED_CATEGORIES, ALLOWED_DOC_TYPES
from ingestion.models import IngestedChunk
from ingestion.qdrant import stable_chunk_id
from retrieval import RetrievalEngine, RetrievalFilters, bm25_search, build_bm25_index
from retrieval.hr_answers import KnowledgeBase, hr_answer_chunk
from retrieval.passages import PassageLibrary

QUESTION = "Can I bring my dog to the Tampere office?"
ANSWER = "Yes, dogs are welcome on Fridays if they are calm around people."


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeQdrant:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[object]]] = []

    def upsert(self, *, collection_name, points):
        self.upserts.append((collection_name, points))


def _corpus_chunk(text: str, section: str) -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata={
            "source_doc": "employee_handbook",
            "doc_type": "handbook",
            "category": "HR",
            "country": "All",
            "file_type": "markdown",
            "source_file": "employee_handbook_v2.1.md",
            "section_path": section,
            "page_number": None,
            "row_number": None,
            "chunk_index": "0.0",
        },
    )


def _engine() -> RetrievalEngine:
    chunks = [
        _corpus_chunk("Core working hours are 10:00 to 15:00 local time.", "Handbook > Working Hours"),
        _corpus_chunk("The office kitchen is cleaned every evening.", "Handbook > Office Life"),
    ]
    return RetrievalEngine(
        client=FakeQdrant(),
        collection_name="nordtech_hr_test",
        embedding_model=FakeEmbeddingModel(),
        bm25_index=build_bm25_index(chunks),
    )


def test_hr_answer_chunk_uses_metadata_the_manifest_allows() -> None:
    chunk = hr_answer_chunk(interaction_id="i-1", question=f"  {QUESTION}\n", answer=ANSWER, country="Finland")

    assert chunk.text.startswith(f"Question an employee asked HR: {QUESTION}")
    assert ANSWER in chunk.text
    assert chunk.metadata["source_doc"] == "hr_answers"
    assert chunk.metadata["doc_type"] in ALLOWED_DOC_TYPES
    assert chunk.metadata["category"] in ALLOWED_CATEGORIES
    assert chunk.metadata["country"] == "Finland"
    assert chunk.metadata["section_path"] == f"Answers from HR > {QUESTION}"
    # Each answered question gets its own stable id.
    other = hr_answer_chunk(interaction_id="i-2", question=QUESTION, answer=ANSWER, country="Finland")
    assert stable_chunk_id(chunk.metadata) != stable_chunk_id(other.metadata)


def test_adding_an_answer_makes_it_searchable_straight_away(tmp_path: Path) -> None:
    engine = _engine()
    passages = PassageLibrary(engine.bm25_index.chunks, tmp_path)
    knowledge = KnowledgeBase(engine, passages)

    chunk_id = knowledge.add_hr_answer(interaction_id="i-1", question=QUESTION, answer=ANSWER, country="Finland")

    # Embedded once and written to the running collection.
    assert len(engine.embedding_model.calls) == 1
    collection, points = engine.client.upserts[0]
    assert collection == "nordtech_hr_test"
    assert str(points[0].id) == chunk_id
    assert points[0].payload["source_doc"] == "hr_answers"
    # Keyword search finds it without a restart, for Finland but not for other countries.
    finland = bm25_search(engine.bm25_index, "bring a dog to the office", top_k=3, filters=RetrievalFilters(country="Finland"))
    assert finland[0].chunk_id == chunk_id
    portugal = bm25_search(engine.bm25_index, "bring a dog to the office", top_k=3, filters=RetrievalFilters(country="Portugal"))
    assert chunk_id not in [result.chunk_id for result in portugal]
    # The source viewer opens it on its own.
    passage = passages.passage(chunk_id)
    assert passage.content == hr_answer_chunk(
        interaction_id="i-1", question=QUESTION, answer=ANSWER, country="Finland"
    ).text
    assert passage.content[passage.highlight_start : passage.highlight_end] == passage.content


def test_adding_the_same_chunk_again_replaces_it() -> None:
    index = build_bm25_index([_corpus_chunk("Core working hours are 10:00 to 15:00.", "Handbook > Hours")])
    first = hr_answer_chunk(interaction_id="i-1", question=QUESTION, answer="No.", country="All")
    second = hr_answer_chunk(interaction_id="i-1", question=QUESTION, answer="Yes, on Fridays.", country="All")

    index.add([first])
    index.add([second])

    assert len(index.chunks) == 2
    assert "Fridays" in index.chunks[-1].text
