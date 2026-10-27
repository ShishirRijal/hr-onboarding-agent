from __future__ import annotations

from typing import Any, TypedDict


class EmployeeContext(TypedDict, total=False):
    employee_id: str
    employee_name: str
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


class AnswerSource(TypedDict, total=False):
    chunk_id: str
    source_doc: str
    source_file: str
    section_path: str
    page_number: int
    row_number: int
    score: float


class GeneratedAnswer(TypedDict):
    text: str
    sources: list[AnswerSource]


class RetrievalDebug(TypedDict):
    resolved_filters: dict[str, str]
    top_n: int
    dense_top_k: int
    bm25_top_k: int
    apply_reranker: bool
    retrieved_count: int


class ConfidenceDebug(TypedDict, total=False):
    retrieved_count: int
    top_score: float
    top_dense_score: float
    score_basis: str
    has_sources: bool
    has_rerank_signal: bool
    answer_declined: bool


class HRHandoff(TypedDict):
    reason: str
    contact: str
    question: str
    employee_context: EmployeeContext
    confidence_score: float
    confidence_label: str
    draft_answer: str
    candidate_sources: list[AnswerSource]


class FinalResponse(TypedDict):
    text: str
    sources: list[AnswerSource]
    answered: bool


class ConversationTurn(TypedDict):
    question: str
    answer: str


class MessageRoute(TypedDict):
    # "chat" for small talk answered directly, "hr" for questions answered from the documents.
    kind: str
    # The question rewritten to stand on its own, for searching; empty for small talk.
    search_query: str


class AnswerCheck(TypedDict):
    # Whether the draft answers what was asked; when not, the employee is offered HR instead.
    answers_question: bool
    unsupported_claims: list[str]
    missing_details: list[str]
    # True once the draft has been rewritten to fix the problems above.
    revised: bool


class RetrievalState(TypedDict, total=False):
    session_id: str
    # The signed-in user asking, so the logged question belongs to them.
    user_id: str
    question: str
    employee_context: EmployeeContext
    # Earlier turns of this chat, oldest first.
    history: list[ConversationTurn]
    message_route: MessageRoute
    retrieval_overrides: RetrievalOverrides
    retrieval_config: RetrievalConfig
    resolved_filters: dict[str, str]
    retrieved_chunks: list[RetrievedChunkPayload]
    retrieval_debug: RetrievalDebug
    generated_answer: GeneratedAnswer
    answer_check: AnswerCheck
    answer_declined: bool
    confidence_score: float
    confidence_label: str
    confidence_debug: ConfidenceDebug
    hr_handoff: HRHandoff
    final_response: FinalResponse
    interaction_id: str
