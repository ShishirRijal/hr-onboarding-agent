from __future__ import annotations

import re
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
from retrieval.context import expand_with_neighbours, passage_chunk_ids
from retrieval.vocabulary import add_policy_terms

from .answer_check import check_answer, revision_feedback
from .answering import generate_grounded_answer, is_insufficient_answer
from .citations import answer_source, number_citations, source_key
from .conversation import MESSAGE_CHAT, generate_chat_reply, recent_history, route_message
from .document_grading import COVERAGE_COMPLETE, grade_documents
from .escalation import NOT_FOUND_MESSAGE, build_hr_handoff
from .state import (
    AnswerCheck,
    AnswerSource,
    ConversationTurn,
    DocumentGrade,
    EmployeeContext,
    FinalResponse,
    GeneratedAnswer,
    MessageRoute,
    RetrievalConfig,
    RetrievalDebug,
    RetrievalOverrides,
    RetrievalState,
)

DEFAULT_COUNTRY_KEYS = (
    "employee_country",
    "office_country",
)
# Words that tie a question to one country's rules, so "and in Finland?" searches
# Finland's sections even for an employee in Tallinn.
COUNTRY_MENTIONS = {
    "Estonia": ("estonia", "estonian", "tallinn"),
    "Finland": ("finland", "finnish", "tampere"),
    "Portugal": ("portugal", "portuguese", "porto"),
}
MAX_ANSWER_SOURCES = 3
NOT_FOUND_CONFIDENCE_LABELS = frozenset({"low"})
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
    answer_generator: Callable[..., str] | None = None,
    message_router: Callable[[str, list[ConversationTurn]], MessageRoute] = route_message,
    chat_responder: Callable[..., str] = generate_chat_reply,
    answer_checker: Callable[..., AnswerCheck] = check_answer,
    document_grader: Callable[..., DocumentGrade] = grade_documents,
    context_expander: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]] = expand_with_neighbours,
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
    graph.add_node("understand_message", _make_understand_message_node(message_router))
    graph.add_node("reply_in_chat", _make_reply_in_chat_node(chat_responder))
    graph.add_node("resolve_filters", _resolve_filters_node)
    graph.add_node(
        "retrieve_documents",
        _make_retrieve_node(
            engine,
            retriever=retriever,
        ),
    )
    graph.add_node("score_confidence", _score_confidence_node)
    graph.add_node("read_neighbours", _make_read_neighbours_node(engine, context_expander))
    graph.add_node("grade_documents", _make_grade_documents_node(document_grader))
    graph.add_node(
        "search_again",
        _make_search_again_node(engine, retriever, document_grader, context_expander),
    )
    graph.add_node(
        "generate_answer",
        _make_generate_answer_node(answer_generator=answer_generator or generate_grounded_answer),
    )
    graph.add_node("check_answer", _make_check_answer_node(answer_checker))
    graph.add_node(
        "revise_answer",
        _make_revise_answer_node(answer_generator=answer_generator or generate_grounded_answer),
    )
    graph.add_node("respond_to_user", _respond_to_user_node)
    graph.add_node("answer_not_found", _answer_not_found_node)
    graph.add_node("log_interaction", _make_log_interaction_node(interaction_logger))
    graph.add_edge(start_token, "understand_message")
    # Small talk is answered directly; only HR questions search the documents, so a
    # greeting never ends in "not found, ask HR?".
    graph.add_conditional_edges(
        "understand_message",
        _route_after_understanding,
        {"reply_in_chat": "reply_in_chat", "resolve_filters": "resolve_filters"},
    )
    graph.add_edge("reply_in_chat", "log_interaction")
    graph.add_edge("resolve_filters", "retrieve_documents")
    graph.add_edge("retrieve_documents", "score_confidence")
    # Retrieval is scored before generating, so a clearly off-topic search goes straight to
    # the HR offer without spending a model call.
    graph.add_conditional_edges(
        "score_confidence",
        _route_after_confidence,
        {"read_neighbours": "read_neighbours", "answer_not_found": "answer_not_found"},
    )
    # Corrective RAG, when switched on (retrieval_config["corrective_search"]): the passages
    # are graded, and when they don't answer everything asked, one more search looks for
    # what's missing. Off by default: on the evaluation set it added ~1s per answer without
    # changing the results, because reading neighbours already brings in what was missing.
    graph.add_conditional_edges(
        "read_neighbours",
        _route_after_reading,
        {"grade_documents": "grade_documents", "generate_answer": "generate_answer"},
    )
    graph.add_conditional_edges(
        "grade_documents",
        _route_after_grading,
        {"generate_answer": "generate_answer", "search_again": "search_again"},
    )
    graph.add_conditional_edges(
        "search_again",
        _route_after_search_again,
        {"generate_answer": "generate_answer", "answer_not_found": "answer_not_found"},
    )
    graph.add_conditional_edges(
        "generate_answer",
        _route_after_answer,
        {"check_answer": "check_answer", "answer_not_found": "answer_not_found"},
    )
    # Self-check before the employee sees anything: a draft that doesn't really answer
    # becomes an offer to ask HR, and one with unsupported or missing details is rewritten once.
    graph.add_conditional_edges(
        "check_answer",
        _route_after_check,
        {
            "respond_to_user": "respond_to_user",
            "revise_answer": "revise_answer",
            "answer_not_found": "answer_not_found",
        },
    )
    graph.add_conditional_edges(
        "revise_answer",
        _route_after_revision,
        {"respond_to_user": "respond_to_user", "answer_not_found": "answer_not_found"},
    )
    graph.add_edge("respond_to_user", "log_interaction")
    graph.add_edge("answer_not_found", "log_interaction")
    graph.add_edge("log_interaction", end_token)
    return graph.compile()


def _make_understand_message_node(
    message_router: Callable[[str, list[ConversationTurn]], MessageRoute],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _understand_message_node(state: RetrievalState) -> dict[str, Any]:
        question = _clean_required_value(state.get("question"), field_name="question")
        history = recent_history(state.get("history", []))
        return {"history": history, "message_route": message_router(question, history)}

    return _understand_message_node


def _route_after_understanding(state: RetrievalState) -> str:
    route = state.get("message_route") or {}
    return "reply_in_chat" if route.get("kind") == MESSAGE_CHAT else "resolve_filters"


def _make_reply_in_chat_node(chat_responder: Callable[..., str]) -> Callable[[RetrievalState], dict[str, Any]]:
    def _reply_in_chat_node(state: RetrievalState) -> dict[str, Any]:
        text = chat_responder(
            _clean_required_value(state.get("question"), field_name="question"),
            history=state.get("history", []),
            employee_context=state.get("employee_context", {}),
        )
        response: FinalResponse = {"text": text, "sources": [], "answered": True}
        return {"final_response": response}

    return _reply_in_chat_node


def _resolve_filters_node(state: RetrievalState) -> dict[str, Any]:
    employee_context = state.get("employee_context", {})
    overrides = state.get("retrieval_overrides", {})

    route = state.get("message_route") or {}
    mentioned = _countries_mentioned(route.get("search_query") or state.get("question") or "")
    # A country named in the question wins over the employee's own; naming several
    # (comparing countries) searches them all.
    if len(mentioned) == 1:
        country = mentioned[0]
    elif mentioned:
        country = None
    else:
        country = _resolve_country(employee_context)

    filters = RetrievalFilters(
        source_doc=_clean_optional_value(overrides.get("source_doc")),
        source_file=_clean_optional_value(overrides.get("source_file")),
        doc_type=_clean_optional_value(overrides.get("doc_type")),
        category=_clean_optional_value(overrides.get("category")),
        country=_clean_optional_value(overrides.get("country")) or country,
        file_type=_clean_optional_value(overrides.get("file_type")),
    )

    return {"resolved_filters": filters.as_dict()}


def _make_retrieve_node(
    engine: RetrievalEngine,
    *,
    retriever: Callable[..., list[RetrievedChunk]] = retrieve,
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _retrieve_node(state: RetrievalState) -> dict[str, Any]:
        # Follow-ups are searched as the standalone question the router rewrote them into.
        route = state.get("message_route") or {}
        question = route.get("search_query") or _clean_required_value(state.get("question"), field_name="question")
        config = _normalize_retrieval_config(state.get("retrieval_config", {}))
        filters = RetrievalFilters(**state.get("resolved_filters", {}))

        results = retriever(
            engine,
            add_policy_terms(question),
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


def _make_read_neighbours_node(
    engine: RetrievalEngine,
    context_expander: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _read_neighbours_node(state: RetrievalState) -> dict[str, Any]:
        # Documents are split into ~500-character pieces and the condition that matters is
        # often in the next one, so each found piece is read with its neighbours.
        return {"retrieved_chunks": context_expander(engine.bm25_index, list(state.get("retrieved_chunks", [])))}

    return _read_neighbours_node


def _make_grade_documents_node(
    document_grader: Callable[..., DocumentGrade],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _grade_documents_node(state: RetrievalState) -> dict[str, Any]:
        grade = document_grader(
            _clean_required_value(state.get("question"), field_name="question"),
            state.get("retrieved_chunks", []),
            history=state.get("history", []),
        )
        # Grading never removes a passage: dropping the ones graded unhelpful cost more
        # answers than it saved (a general section often frames the specific one).
        return {"document_grade": grade}

    return _grade_documents_node


def _make_search_again_node(
    engine: RetrievalEngine,
    retriever: Callable[..., list[RetrievedChunk]],
    document_grader: Callable[..., DocumentGrade],
    context_expander: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _search_again_node(state: RetrievalState) -> dict[str, Any]:
        first_grade = state["document_grade"]
        graded = list(state.get("retrieved_chunks", []))
        seen = {chunk_id for passage in graded for chunk_id in passage_chunk_ids(passage)}
        config = _normalize_retrieval_config(state.get("retrieval_config", {}))
        filters = RetrievalFilters(**state.get("resolved_filters", {}))

        results = retriever(
            engine,
            add_policy_terms(first_grade["missing"]),
            filters=filters if not filters.is_empty() else None,
            top_n=config["top_n"],
            dense_top_k=config["dense_top_k"],
            bm25_top_k=config["bm25_top_k"],
            apply_reranker=config["apply_reranker"],
        )
        found = [asdict(chunk) for chunk in results if chunk.chunk_id not in seen]
        new_passages = context_expander(engine.bm25_index, found) if found else []
        grade = first_grade
        if new_passages:
            # The new passages are graded alongside the helpful ones from the first search,
            # so coverage is judged on everything the answer would be written from.
            grade = document_grader(
                _clean_required_value(state.get("question"), field_name="question"),
                _relevant(graded, first_grade) + new_passages,
                history=state.get("history", []),
            )
        grade = {**grade, "searched_again": True}
        retrieval_debug = {**state.get("retrieval_debug", {}), "search_again_query": first_grade["missing"]}

        # Only new passages that help are added; the first search's passages all stay.
        added = _relevant(new_passages, grade)
        if added or first_grade["relevant_chunk_ids"]:
            return {"retrieved_chunks": graded + added, "document_grade": grade, "retrieval_debug": retrieval_debug}
        # Neither search found anything that answers it: the employee is offered HR.
        return {
            "retrieved_chunks": graded,
            "document_grade": grade,
            "retrieval_debug": retrieval_debug,
            "confidence_score": 0.0,
            "confidence_label": "low",
            "confidence_debug": {**state.get("confidence_debug", {}), "no_relevant_sections": True},
        }

    return _search_again_node


def _relevant(passages: list[dict[str, Any]], grade: DocumentGrade) -> list[dict[str, Any]]:
    wanted = set(grade["relevant_chunk_ids"])
    return [passage for passage in passages if passage.get("chunk_id") in wanted]


def _make_generate_answer_node(
    *,
    answer_generator: Callable[..., str],
) -> Callable[[RetrievalState], dict[str, Any]]:
    def _generate_answer_node(state: RetrievalState) -> dict[str, Any]:
        question = _clean_required_value(state.get("question"), field_name="question")
        chunks = state.get("retrieved_chunks", [])

        text = answer_generator(
            question,
            chunks,
            history=state.get("history", []),
            employee_context=state.get("employee_context", {}),
            country=state.get("resolved_filters", {}).get("country"),
        ).strip()
        answer: GeneratedAnswer = {"text": text, "sources": _build_answer_sources(chunks)}
        if text and not is_insufficient_answer(text):
            return {"generated_answer": answer, "answer_declined": False}

        # The model found the excerpts insufficient, so there is no answer to give.
        return {
            "generated_answer": {"text": "", "sources": answer["sources"]},
            "answer_declined": True,
            "confidence_score": 0.0,
            "confidence_label": "low",
            "confidence_debug": {**state.get("confidence_debug", {}), "answer_declined": True},
        }

    return _generate_answer_node


def _declined_update(state: RetrievalState, **extra: Any) -> dict[str, Any]:
    """There is no answer to give: the employee is offered HR instead."""
    sources = state.get("generated_answer", {}).get("sources", [])
    return {
        "generated_answer": {"text": "", "sources": sources},
        "answer_declined": True,
        "confidence_score": 0.0,
        "confidence_label": "low",
        "confidence_debug": {**state.get("confidence_debug", {}), "answer_declined": True},
        **extra,
    }


def _make_check_answer_node(answer_checker: Callable[..., AnswerCheck]) -> Callable[[RetrievalState], dict[str, Any]]:
    def _check_answer_node(state: RetrievalState) -> dict[str, Any]:
        draft = state.get("generated_answer", {}).get("text", "")
        check = answer_checker(
            _clean_required_value(state.get("question"), field_name="question"),
            state.get("retrieved_chunks", []),
            draft,
            history=state.get("history", []),
        )
        if not check["answers_question"]:
            # The draft talks around the question ("not covered", "case by case"), so it
            # goes to HR rather than to the employee.
            return _declined_update(state, answer_check=check)
        return {"answer_check": check}

    return _check_answer_node


def _make_revise_answer_node(*, answer_generator: Callable[..., str]) -> Callable[[RetrievalState], dict[str, Any]]:
    def _revise_answer_node(state: RetrievalState) -> dict[str, Any]:
        check = state["answer_check"]
        chunks = state.get("retrieved_chunks", [])
        text = answer_generator(
            _clean_required_value(state.get("question"), field_name="question"),
            chunks,
            history=state.get("history", []),
            employee_context=state.get("employee_context", {}),
            country=state.get("resolved_filters", {}).get("country"),
            draft=state.get("generated_answer", {}).get("text", ""),
            feedback=revision_feedback(check),
        ).strip()
        revised_check: AnswerCheck = {**check, "revised": True}
        if not text or is_insufficient_answer(text):
            return _declined_update(state, answer_check=revised_check)
        return {
            "generated_answer": {"text": text, "sources": _build_answer_sources(chunks)},
            "answer_check": revised_check,
        }

    return _revise_answer_node


def _build_answer_sources(chunks: list[dict[str, Any]]) -> list[AnswerSource]:
    sources: list[AnswerSource] = []
    seen: set[tuple[Any, ...]] = set()

    for chunk in chunks:
        if not str(chunk.get("chunk_id", "")).strip():
            continue

        key = source_key(chunk)
        if key in seen:
            continue

        seen.add(key)
        sources.append(answer_source(chunk))
        if len(sources) >= MAX_ANSWER_SOURCES:
            break

    return sources


def _score_confidence_node(state: RetrievalState) -> dict[str, Any]:
    chunks = state.get("retrieved_chunks", [])
    top_chunk = chunks[0] if chunks else {}
    scores = top_chunk.get("scores", {}) if top_chunk else {}
    top_score = float(top_chunk.get("score", 0.0) or 0.0)
    top_dense_score = max(
        (float((chunk.get("scores", {}) or {}).get("dense", 0.0) or 0.0) for chunk in chunks),
        default=0.0,
    )
    has_sources = bool(_build_answer_sources(chunks))
    has_rerank_signal = "rerank" in scores

    confidence_score = _calculate_confidence_score(
        retrieved_count=len(chunks),
        top_score=top_score,
        top_dense_score=top_dense_score,
        has_sources=has_sources,
        has_rerank_signal=has_rerank_signal,
    )

    return {
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "confidence_debug": {
            "retrieved_count": len(chunks),
            "top_score": top_score,
            "top_dense_score": top_dense_score,
            "score_basis": _score_basis(len(chunks), has_rerank_signal),
            "has_sources": has_sources,
            "has_rerank_signal": has_rerank_signal,
            "answer_declined": False,
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
    has_sources: bool,
    has_rerank_signal: bool,
) -> float:
    if retrieved_count == 0 or not has_sources:
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
    if state.get("confidence_label", "low") in NOT_FOUND_CONFIDENCE_LABELS:
        return "answer_not_found"
    return "read_neighbours"


def _route_after_reading(state: RetrievalState) -> str:
    config = _normalize_retrieval_config(state.get("retrieval_config", {}))
    return "grade_documents" if config["corrective_search"] else "generate_answer"


def _route_after_grading(state: RetrievalState) -> str:
    grade = state.get("document_grade") or {}
    return "generate_answer" if grade.get("coverage") == COVERAGE_COMPLETE else "search_again"


def _route_after_search_again(state: RetrievalState) -> str:
    no_sections = (state.get("confidence_debug") or {}).get("no_relevant_sections")
    return "answer_not_found" if no_sections else "generate_answer"


def _route_after_answer(state: RetrievalState) -> str:
    return "answer_not_found" if state.get("answer_declined") else "check_answer"


def _route_after_check(state: RetrievalState) -> str:
    check = state.get("answer_check")
    if check is None:
        return "respond_to_user"
    if not check["answers_question"]:
        return "answer_not_found"
    if check["unsupported_claims"] or check["missing_details"]:
        return "revise_answer"
    return "respond_to_user"


def _route_after_revision(state: RetrievalState) -> str:
    return "answer_not_found" if state.get("answer_declined") else "respond_to_user"


def _respond_to_user_node(state: RetrievalState) -> dict[str, Any]:
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})
    # The answer cites sections by the numbers they were given in; renumbered here, once
    # the answer is final, so the employee sees [1], [2], ... for the sources it uses.
    text, sources = number_citations(generated_answer.get("text", ""), state.get("retrieved_chunks", []))
    response: FinalResponse = {
        "text": text,
        # An answer that cites nothing still lists where it came from.
        "sources": sources or generated_answer.get("sources", []),
        "answered": True,
    }
    return {"final_response": response}


def _answer_not_found_node(state: RetrievalState) -> dict[str, Any]:
    # Nothing goes to HR yet: the employee is asked first, and their choice is recorded
    # against the logged interaction.
    response: FinalResponse = {"text": NOT_FOUND_MESSAGE, "sources": [], "answered": False}
    return {
        "hr_handoff": build_hr_handoff(state, _build_answer_sources(state.get("retrieved_chunks", []))),
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
        "corrective_search": bool(raw_config.get("corrective_search", False)),
    }


def _countries_mentioned(text: str) -> list[str]:
    lowered = text.lower()
    return [
        country
        for country, words in COUNTRY_MENTIONS.items()
        if any(re.search(rf"\b{word}\b", lowered) for word in words)
    ]


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
