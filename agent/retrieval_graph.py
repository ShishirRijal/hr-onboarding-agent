from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from retrieval import (
    DEFAULT_BM25_TOP_K,
    DEFAULT_DENSE_TOP_K,
    DEFAULT_RERANK_TOP_N,
    RetrievalEngine,
    RetrievalFilters,
    RetrievedChunk,
    retrieve,
)

from .answering import NO_ANSWER_MESSAGE, generate_grounded_answer, is_insufficient_answer
from .escalation import ESCALATION_MESSAGE, build_hr_escalation
from .state import (
    AnswerSource,
    EmployeeContext,
    FinalResponse,
    GeneratedAnswer,
    RetrievalConfig,
    RetrievalDebug,
    RetrievalOverrides,
    RetrievalState,
)

DEFAULT_COUNTRY_KEYS = (
    "employee_country",
    "office_country",
)
MAX_ANSWER_SOURCES = 3
ESCALATE_CONFIDENCE_LABELS = frozenset({"low"})
HIGH_CONFIDENCE = 0.75
MEDIUM_CONFIDENCE = 0.45
# Without a reranker, confidence comes from BGE cosine similarity, which is a weak
# relevance signal: answerable and unanswerable FAQ questions overlap between ~0.58 and
# ~0.74. Only clearly off-topic retrievals (below the floor) escalate on similarity alone,
# the rest relies on the answer model declining, and unreranked answers top out at medium.
DENSE_SIMILARITY_FLOOR = 0.50
DENSE_SIMILARITY_CEILING = 0.85
MAX_UNRERANKED_CONFIDENCE = 0.74


def build_retrieval_graph(
    engine: RetrievalEngine,
    *,
    retriever: Callable[..., list[RetrievedChunk]] = retrieve,
    answer_generator: Callable[[str, list[dict[str, Any]]], str] | None = None,
    interaction_logger: Callable[[RetrievalState], str] | None = None,
    state_graph_cls: Any | None = None,
    start_token: Any | None = None,
    end_token: Any | None = None,
) -> Any:
    if state_graph_cls is None:
        from langgraph.graph import END, START, StateGraph

        state_graph_cls = StateGraph
        start_token = START
        end_token = END

    if start_token is None or end_token is None:
        raise ValueError("start_token and end_token are required when overriding the graph class.")

    graph = state_graph_cls(RetrievalState)
    graph.add_node("resolve_filters", _resolve_filters_node)
    graph.add_node(
        "retrieve_documents",
        _make_retrieve_node(
            engine,
            retriever=retriever,
        ),
    )
    graph.add_node(
        "generate_answer",
        _make_generate_answer_node(answer_generator=answer_generator or generate_grounded_answer),
    )
    graph.add_node("score_confidence", _score_confidence_node)
    graph.add_node("respond_to_user", _respond_to_user_node)
    graph.add_node("escalate_to_hr", _escalate_to_hr_node)
    graph.add_node("log_interaction", _make_log_interaction_node(interaction_logger))
    graph.add_edge(start_token, "resolve_filters")
    graph.add_edge("resolve_filters", "retrieve_documents")
    graph.add_edge("retrieve_documents", "generate_answer")
    graph.add_edge("generate_answer", "score_confidence")
    graph.add_conditional_edges(
        "score_confidence",
        _route_after_confidence,
        {"respond_to_user": "respond_to_user", "escalate_to_hr": "escalate_to_hr"},
    )
    graph.add_edge("respond_to_user", "log_interaction")
    graph.add_edge("escalate_to_hr", "log_interaction")
    graph.add_edge("log_interaction", end_token)
    return graph.compile()


def _resolve_filters_node(state: RetrievalState) -> dict[str, Any]:
    employee_context = state.get("employee_context", {})
    overrides = state.get("retrieval_overrides", {})

    filters = RetrievalFilters(
        source_doc=_clean_optional_value(overrides.get("source_doc")),
        source_file=_clean_optional_value(overrides.get("source_file")),
        doc_type=_clean_optional_value(overrides.get("doc_type")),
        category=_clean_optional_value(overrides.get("category")),
        country=_clean_optional_value(overrides.get("country")) or _resolve_country(employee_context),
        file_type=_clean_optional_value(overrides.get("file_type")),
    )

    return {"resolved_filters": filters.as_dict()}


def _make_retrieve_node(
    engine: RetrievalEngine,
    *,
    retriever: Callable[..., list[RetrievedChunk]] = retrieve,
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _retrieve_node(state: RetrievalState) -> dict[str, Any]:
        question = _clean_required_value(state.get("question"), field_name="question")
        config = _normalize_retrieval_config(state.get("retrieval_config", {}))
        filters = RetrievalFilters(**state.get("resolved_filters", {}))

        results = retriever(
            engine,
            question,
            filters=filters if not filters.is_empty() else None,
            top_n=config["top_n"],
            dense_top_k=config["dense_top_k"],
            bm25_top_k=config["bm25_top_k"],
            apply_reranker=config["apply_reranker"],
        )

        retrieval_debug: RetrievalDebug = {
            "resolved_filters": filters.as_dict(),
            "top_n": config["top_n"],
            "dense_top_k": config["dense_top_k"],
            "bm25_top_k": config["bm25_top_k"],
            "apply_reranker": config["apply_reranker"],
            "retrieved_count": len(results),
        }

        return {
            "retrieved_chunks": [asdict(chunk) for chunk in results],
            "retrieval_debug": retrieval_debug,
        }

    return _retrieve_node


def _make_generate_answer_node(
    *,
    answer_generator: Callable[[str, list[dict[str, Any]]], str],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _generate_answer_node(state: RetrievalState) -> dict[str, Any]:
        question = _clean_required_value(state.get("question"), field_name="question")
        chunks = state.get("retrieved_chunks", [])

        if not chunks:
            answer: GeneratedAnswer = {"text": NO_ANSWER_MESSAGE, "sources": []}
            return {"generated_answer": answer, "answer_declined": True}

        text = answer_generator(question, chunks).strip()
        answer_declined = is_insufficient_answer(text)
        answer = {
            "text": NO_ANSWER_MESSAGE if answer_declined else text,
            "sources": _build_answer_sources(chunks),
        }
        return {"generated_answer": answer, "answer_declined": answer_declined}

    return _generate_answer_node


def _build_answer_sources(chunks: list[dict[str, Any]]) -> list[AnswerSource]:
    sources: list[AnswerSource] = []
    seen: set[tuple[Any, ...]] = set()

    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        if not chunk_id:
            continue

        metadata = chunk.get("metadata", {}) or {}
        source_key = (
            metadata.get("source_file"),
            metadata.get("source_doc"),
            metadata.get("section_path"),
            metadata.get("page_number"),
            metadata.get("row_number"),
        )
        if source_key in seen:
            continue

        seen.add(source_key)
        source: AnswerSource = {
            "chunk_id": chunk_id,
            "score": float(chunk.get("score", 0.0) or 0.0),
        }
        for key in ("source_doc", "source_file", "section_path", "page_number", "row_number"):
            value = metadata.get(key)
            if value is not None:
                source[key] = value

        sources.append(source)
        if len(sources) >= MAX_ANSWER_SOURCES:
            break

    return sources


def _score_confidence_node(state: RetrievalState) -> dict[str, Any]:
    chunks = state.get("retrieved_chunks", [])
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})
    top_chunk = chunks[0] if chunks else {}
    scores = top_chunk.get("scores", {}) if top_chunk else {}
    top_score = float(top_chunk.get("score", 0.0) or 0.0)
    top_dense_score = max(
        (float((chunk.get("scores", {}) or {}).get("dense", 0.0) or 0.0) for chunk in chunks),
        default=0.0,
    )
    has_answer = bool(str(generated_answer.get("text", "")).strip())
    has_sources = bool(generated_answer.get("sources", []))
    has_rerank_signal = "rerank" in scores
    answer_declined = bool(state.get("answer_declined", False))

    confidence_score = _calculate_confidence_score(
        retrieved_count=len(chunks),
        top_score=top_score,
        top_dense_score=top_dense_score,
        has_answer=has_answer,
        has_sources=has_sources,
        has_rerank_signal=has_rerank_signal,
        answer_declined=answer_declined,
    )

    return {
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "confidence_debug": {
            "retrieved_count": len(chunks),
            "top_score": top_score,
            "top_dense_score": top_dense_score,
            "score_basis": _score_basis(len(chunks), has_rerank_signal),
            "has_answer": has_answer,
            "has_sources": has_sources,
            "has_rerank_signal": has_rerank_signal,
            "answer_declined": answer_declined,
        },
    }


def _score_basis(retrieved_count: int, has_rerank_signal: bool) -> str:
    if retrieved_count == 0:
        return "none"
    return "rerank" if has_rerank_signal else "dense"


def _calculate_confidence_score(
    *,
    retrieved_count: int,
    top_score: float,
    top_dense_score: float,
    has_answer: bool,
    has_sources: bool,
    has_rerank_signal: bool,
    answer_declined: bool,
) -> float:
    if retrieved_count == 0 or not has_answer or not has_sources or answer_declined:
        return 0.0

    if not has_rerank_signal:
        return _dense_confidence(top_dense_score)

    score = min(max(top_score, 0.0), 1.0)
    if retrieved_count >= 2:
        score += 0.03
    if has_rerank_signal:
        score += 0.04

    return round(min(score, 0.97), 3)


def _route_after_confidence(state: RetrievalState) -> str:
    if state.get("confidence_label", "low") in ESCALATE_CONFIDENCE_LABELS:
        return "escalate_to_hr"
    return "respond_to_user"


def _respond_to_user_node(state: RetrievalState) -> dict[str, Any]:
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})
    response: FinalResponse = {
        "text": generated_answer.get("text", ""),
        "sources": generated_answer.get("sources", []),
        "escalated": False,
    }
    return {"final_response": response}


def _escalate_to_hr_node(state: RetrievalState) -> dict[str, Any]:
    response: FinalResponse = {
        "text": ESCALATION_MESSAGE,
        "sources": [],
        "escalated": True,
    }
    return {
        "escalation": build_hr_escalation(state),
        "final_response": response,
    }


def _dense_confidence(similarity: float) -> float:
    if similarity < DENSE_SIMILARITY_FLOOR:
        return round(max(similarity, 0.0) / DENSE_SIMILARITY_FLOOR * MEDIUM_CONFIDENCE * 0.99, 3)

    position = (min(similarity, DENSE_SIMILARITY_CEILING) - DENSE_SIMILARITY_FLOOR) / (
        DENSE_SIMILARITY_CEILING - DENSE_SIMILARITY_FLOOR
    )
    return round(MEDIUM_CONFIDENCE + position * (MAX_UNRERANKED_CONFIDENCE - MEDIUM_CONFIDENCE), 3)


def _make_log_interaction_node(
    interaction_logger: Callable[[RetrievalState], str] | None,
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _log_interaction_node(state: RetrievalState) -> dict[str, Any]:
        if interaction_logger is None:
            return {}
        return {"interaction_id": interaction_logger(state)}

    return _log_interaction_node


def _confidence_label(score: float) -> str:
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def _normalize_retrieval_config(raw_config: RetrievalConfig) -> dict[str, Any]:
    return {
        "top_n": int(raw_config.get("top_n", DEFAULT_RERANK_TOP_N)),
        "dense_top_k": int(raw_config.get("dense_top_k", DEFAULT_DENSE_TOP_K)),
        "bm25_top_k": int(raw_config.get("bm25_top_k", DEFAULT_BM25_TOP_K)),
        "apply_reranker": bool(raw_config.get("apply_reranker", True)),
    }


def _resolve_country(employee_context: EmployeeContext) -> str | None:
    for key in DEFAULT_COUNTRY_KEYS:
        value = _clean_optional_value(employee_context.get(key))
        if value and value.lower() != "remote":
            return value
    return None


def _clean_required_value(value: Any, *, field_name: str) -> str:
    cleaned = _clean_optional_value(value)
    if not cleaned:
        raise ValueError(f"Retrieval state field '{field_name}' is required.")
    return cleaned


def _clean_optional_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
