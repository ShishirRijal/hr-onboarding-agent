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

from .state import (
    AnswerSource,
    EmployeeContext,
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


def build_retrieval_graph(
    engine: RetrievalEngine,
    *,
    retriever: Callable[..., list[RetrievedChunk]] = retrieve,
    answer_generator: Callable[[str, list[dict[str, Any]]], str] | None = None,
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
        _make_generate_answer_node(answer_generator=answer_generator or _default_answer_generator),
    )
    graph.add_node("score_confidence", _score_confidence_node)
    graph.add_edge(start_token, "resolve_filters")
    graph.add_edge("resolve_filters", "retrieve_documents")
    graph.add_edge("retrieve_documents", "generate_answer")
    graph.add_edge("generate_answer", "score_confidence")
    graph.add_edge("score_confidence", end_token)
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
            answer: GeneratedAnswer = {
                "text": (
                    "I could not find enough information in the HR knowledge base to answer this "
                    "question reliably."
                ),
                "sources": [],
            }
            return {"generated_answer": answer}

        answer = {
            "text": answer_generator(question, chunks).strip(),
            "sources": _build_answer_sources(chunks),
        }
        return {"generated_answer": answer}

    return _generate_answer_node


def _default_answer_generator(question: str, chunks: list[dict[str, Any]]) -> str:
    del question
    top_chunk = chunks[0]
    return str(top_chunk.get("text", "")).strip()


def _build_answer_sources(chunks: list[dict[str, Any]]) -> list[AnswerSource]:
    sources: list[AnswerSource] = []
    seen: set[str] = set()

    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        if not chunk_id or chunk_id in seen:
            continue

        seen.add(chunk_id)
        metadata = chunk.get("metadata", {}) or {}
        source: AnswerSource = {
            "chunk_id": chunk_id,
            "score": float(chunk.get("score", 0.0) or 0.0),
        }
        for key in ("source_doc", "source_file", "section_path", "page_number", "row_number"):
            value = metadata.get(key)
            if value is not None:
                source[key] = value

        sources.append(source)

    return sources


def _score_confidence_node(state: RetrievalState) -> dict[str, Any]:
    chunks = state.get("retrieved_chunks", [])
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})
    top_chunk = chunks[0] if chunks else {}
    scores = top_chunk.get("scores", {}) if top_chunk else {}
    top_score = float(top_chunk.get("score", 0.0) or 0.0)
    has_answer = bool(str(generated_answer.get("text", "")).strip())
    has_sources = bool(generated_answer.get("sources", []))
    has_rerank_signal = "rerank" in scores

    confidence_score = _calculate_confidence_score(
        retrieved_count=len(chunks),
        top_score=top_score,
        has_answer=has_answer,
        has_sources=has_sources,
        has_rerank_signal=has_rerank_signal,
    )

    return {
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "confidence_debug": {
            "retrieved_count": len(chunks),
            "top_score": top_score,
            "has_answer": has_answer,
            "has_sources": has_sources,
            "has_rerank_signal": has_rerank_signal,
        },
    }


def _calculate_confidence_score(
    *,
    retrieved_count: int,
    top_score: float,
    has_answer: bool,
    has_sources: bool,
    has_rerank_signal: bool,
) -> float:
    if retrieved_count == 0 or not has_answer or not has_sources:
        return 0.0

    score = min(max(top_score, 0.0), 1.0)
    if retrieved_count >= 2:
        score += 0.05
    if has_rerank_signal:
        score += 0.05

    return round(min(score, 1.0), 3)


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
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
