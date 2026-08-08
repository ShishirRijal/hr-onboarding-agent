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

from .state import EmployeeContext, RetrievalConfig, RetrievalDebug, RetrievalOverrides, RetrievalState

DEFAULT_COUNTRY_KEYS = (
    "employee_country",
    "office_country",
)


def build_retrieval_graph(
    engine: RetrievalEngine,
    *,
    retriever: Callable[..., list[RetrievedChunk]] = retrieve,
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
    graph.add_edge(start_token, "resolve_filters")
    graph.add_edge("resolve_filters", "retrieve_documents")
    graph.add_edge("retrieve_documents", end_token)
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
