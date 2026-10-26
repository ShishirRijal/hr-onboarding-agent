from __future__ import annotations

from typing import Any

from ingestion.embeddings import embed_texts
from ingestion.models import IngestedChunk
from ingestion.qdrant import stable_chunk_id, upsert_to_qdrant

from .pipeline import RetrievalEngine

HR_ANSWERS_SOURCE = "hr_answers"
HR_ANSWERS_TITLE = "Answers from HR"
# Values ingestion/manifest.py allows for the HR FAQ material.
HR_ANSWERS_DOC_TYPE = "faq_log"
HR_ANSWERS_CATEGORY = "FAQ"
HR_ANSWERS_FILE_TYPE = "hr_answer"


def hr_answer_chunk(*, interaction_id: str, question: str, answer: str, country: str) -> IngestedChunk:
    """A question HR answered, as a chunk of the knowledge base. The question comes first so
    similar questions find it."""
    question = " ".join(question.split())
    return IngestedChunk(
        text=f"Question an employee asked HR: {question}\n\nHR's answer: {answer.strip()}",
        metadata={
            "source_doc": HR_ANSWERS_SOURCE,
            "doc_type": HR_ANSWERS_DOC_TYPE,
            "category": HR_ANSWERS_CATEGORY,
            "country": country,
            "file_type": HR_ANSWERS_FILE_TYPE,
            "source_file": None,
            # Shown like a document section: "Answers from HR > <question>".
            "section_path": f"{HR_ANSWERS_TITLE} > {question}",
            "page_number": None,
            "row_number": None,
            # The question's interaction id keeps each answer's chunk id unique and stable.
            "chunk_index": interaction_id,
        },
    )


class KnowledgeBase:
    """Adds HR's answers to what the running assistant searches: Qdrant for dense search, the
    in-memory BM25 index for keyword search, and the passages the source viewer opens.

    Embedding isn't safe to run on several threads at once, so callers hold the API's graph
    lock while adding.
    """

    def __init__(self, engine: RetrievalEngine, passages: Any | None = None) -> None:
        self._engine = engine
        self._passages = passages

    def add_hr_answer(self, *, interaction_id: str, question: str, answer: str, country: str) -> str:
        """Indexes the answer and returns its chunk id."""
        chunk = hr_answer_chunk(interaction_id=interaction_id, question=question, answer=answer, country=country)
        embeddings = embed_texts(self._engine.embedding_model, [chunk.text])
        upsert_to_qdrant(self._engine.client, self._engine.collection_name, [chunk], embeddings)
        self._engine.bm25_index.add([chunk])
        if self._passages is not None:
            self._passages.add(chunk)
        return stable_chunk_id(chunk.metadata)
