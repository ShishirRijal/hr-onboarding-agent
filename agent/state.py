from __future__ import annotations

from typing import Any, TypedDict


class EmployeeContext(TypedDict, total=False):
    employee_id: str
    employee_country: str
    office_country: str
    office_location: str
    department: str
    role: str
    date_of_joining: str
    gender: str


class RetrievalOverrides(TypedDict, total=False):
    source_doc: str
    source_file: str
    doc_type: str
    category: str
    country: str
    file_type: str


class RetrievalConfig(TypedDict, total=False):
    top_n: int
    dense_top_k: int
    bm25_top_k: int
    apply_reranker: bool


class RetrievedChunkPayload(TypedDict, total=False):
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    source: str
    ranks: dict[str, int]
    scores: dict[str, float]


class RetrievalState(TypedDict, total=False):
    question: str
    employee_context: EmployeeContext
    retrieval_overrides: RetrievalOverrides
    retrieval_config: RetrievalConfig
    resolved_filters: dict[str, str]
    retrieved_chunks: list[RetrievedChunkPayload]
    retrieval_debug: dict[str, Any]
