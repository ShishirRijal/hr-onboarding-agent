from __future__ import annotations

from typing import Any, NotRequired, TypedDict


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
    # Grade the found sections and search again for what they leave out (corrective RAG).
    corrective_search: bool


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
    # Graded sections didn't answer the question, even after searching again.
    no_relevant_sections: bool


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
    # "chat" or "hr", as the router sorted the question; small talk doesn't fill the memory.
    kind: NotRequired[str]
    # The chunks the answer cited, so a follow-up can read them again.
    sources: NotRequired[list[str]]


class ChatMemory(TypedDict):
    # Older turns of the chat, summarised; the latest turns are given to the models in full.
    summary: str
    # How many turns, from the start of the chat, the summary covers.
    turns_covered: int


class MessageRoute(TypedDict):
    # "chat" for small talk answered directly, "hr" for questions answered from the documents.
    kind: str
    # The question rewritten to stand on its own, for searching; empty for small talk.
    search_query: str
    # True when it builds on the last answer, which then has its sections read again.
    follows_up: NotRequired[bool]


class AnswerCheck(TypedDict):
    # Whether the draft answers what was asked; when not, the employee is offered HR instead.
    answers_question: bool
    unsupported_claims: list[str]
    missing_details: list[str]
    # True once the draft has been rewritten to fix the problems above.
    revised: bool


class DocumentGrade(TypedDict):
    # The found sections that help answer the question; the others aren't shown to the answer model.
    relevant_chunk_ids: list[str]
    # "complete", "partial" or "none": how much of the question those sections answer.
    coverage: str
    # What to search for when they don't answer all of it.
    missing: str
    # True once a second search has been run for what was missing.
    searched_again: bool


class RetrievalState(TypedDict, total=False):
    session_id: str
    # The signed-in user asking, so the logged question belongs to them.
    user_id: str
    question: str
    employee_context: EmployeeContext
    # Earlier turns of this chat, oldest first: all of them going in, only the ones not
    # covered by the memory's summary after remember_conversation.
    history: list[ConversationTurn]
    memory: ChatMemory
    message_route: MessageRoute
    retrieval_overrides: RetrievalOverrides
    retrieval_config: RetrievalConfig
    resolved_filters: dict[str, str]
    retrieved_chunks: list[RetrievedChunkPayload]
    retrieval_debug: RetrievalDebug
    document_grade: DocumentGrade
    generated_answer: GeneratedAnswer
    answer_check: AnswerCheck
    answer_declined: bool
    confidence_score: float
    confidence_label: str
    confidence_debug: ConfidenceDebug
    hr_handoff: HRHandoff
    final_response: FinalResponse
    interaction_id: str
