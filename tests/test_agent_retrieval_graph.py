from __future__ import annotations

from types import SimpleNamespace

from agent import HR_CONTACT_EMAIL, build_retrieval_graph
from agent.escalation import NOT_FOUND_MESSAGE
from retrieval import RetrievedChunk, RetrievalEngine


class FakeRetriever:
    def __init__(self, results: list[RetrievedChunk] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.results = results

    def __call__(self, engine, query, **kwargs):
        self.calls.append(
            {
                "engine": engine,
                "query": query,
                "kwargs": kwargs,
            }
        )
        if self.results is not None:
            return self.results

        return [
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Annual leave in Estonia is 28 calendar days.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "doc_type": "policy",
                    "category": "HR",
                    "country": "Estonia",
                },
                score=0.91,
                source="reranked",
                ranks={"dense": 1, "bm25": 1, "rerank": 1},
                scores={"dense": 0.91, "bm25": 12.4, "fused": 0.5, "rerank": 0.95},
            )
        ]


class FakeCompiledGraph:
    def __init__(
        self,
        nodes: dict[str, object],
        edges: dict[object, str],
        conditional_edges: dict[str, tuple[object, dict[str, str]]],
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.visited: list[str] = []

    def invoke(self, state):
        current_state = dict(state)
        current = "__start__"
        self.visited = []
        while True:
            if current in self.conditional_edges:
                router, path_map = self.conditional_edges[current]
                target = path_map[router(current_state)]
            else:
                target = self.edges[current]

            if target == "__end__":
                return current_state

            self.visited.append(target)
            current_state.update(self.nodes[target](current_state))
            current = target


class FakeStateGraph:
    def __init__(self, state_schema) -> None:
        self.state_schema = state_schema
        self.nodes: dict[str, object] = {}
        self.edges: dict[object, str] = {}
        self.conditional_edges: dict[str, tuple[object, dict[str, str]]] = {}

    def add_node(self, name, fn):
        self.nodes[name] = fn

    def add_edge(self, source, target):
        self.edges[source] = target

    def add_conditional_edges(self, source, path, path_map):
        self.conditional_edges[source] = (path, path_map)

    def compile(self):
        return FakeCompiledGraph(self.nodes, self.edges, self.conditional_edges)


def fake_answer_generator(question, chunks, **_):
    del question
    return str(chunks[0]["text"])


def route_to_hr(question, history):
    del history
    return {"kind": "hr", "search_query": question}


def test_retrieval_graph_resolves_country_from_employee_context() -> None:
    retriever = FakeRetriever()
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "How much annual leave do I get?",
            "employee_context": {"employee_country": "Estonia", "office_country": "Estonia"},
        }
    )

    assert retriever.calls
    call_kwargs = retriever.calls[0]["kwargs"]
    assert call_kwargs["top_n"] == 5
    assert call_kwargs["dense_top_k"] == 20
    assert call_kwargs["bm25_top_k"] == 20
    assert call_kwargs["apply_reranker"] is True
    assert call_kwargs["filters"].as_dict()["country"] == "Estonia"
    assert result["resolved_filters"]["country"] == "Estonia"
    assert result["retrieval_debug"]["retrieved_count"] == 1
    assert result["retrieved_chunks"][0]["metadata"]["country"] == "Estonia"
    assert result["retrieved_chunks"][0]["source"] == "reranked"
    assert result["generated_answer"]["text"] == "Annual leave in Estonia is 28 calendar days."
    assert result["generated_answer"]["sources"][0]["source_file"] == "leave_absence_policy.md"
    assert result["confidence_label"] == "high"
    assert result["confidence_debug"]["has_rerank_signal"] is True


def test_retrieval_graph_prefers_explicit_override() -> None:
    retriever = FakeRetriever()
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "How much annual leave do I get?",
            "employee_context": {"employee_country": "Estonia", "office_country": "Estonia"},
            "retrieval_overrides": {"country": "Portugal"},
            "retrieval_config": {"apply_reranker": False, "top_n": 1},
        }
    )

    call_kwargs = retriever.calls[0]["kwargs"]
    assert call_kwargs["filters"].as_dict()["country"] == "Portugal"
    assert call_kwargs["apply_reranker"] is False
    assert call_kwargs["top_n"] == 1
    assert result["resolved_filters"]["country"] == "Portugal"


def test_retrieval_graph_ignores_remote_office_country_for_filtering() -> None:
    retriever = FakeRetriever()
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "How much annual leave do I get?",
            "employee_context": {"employee_country": "", "office_country": "Remote"},
        }
    )

    call_kwargs = retriever.calls[0]["kwargs"]
    assert call_kwargs["filters"] is None
    assert result["resolved_filters"] == {}


def test_retrieval_graph_uses_injected_answer_generator() -> None:
    retriever = FakeRetriever()
    answer_generator_calls: list[dict[str, object]] = []

    def answer_generator(question, chunks, **context):
        answer_generator_calls.append({"question": question, "chunks": chunks, **context})
        return "Employees in Estonia receive 28 calendar days of annual leave."

    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "How much annual leave do I get?",
            "employee_context": {"employee_country": "Estonia"},
        }
    )

    assert answer_generator_calls
    assert answer_generator_calls[0]["question"] == "How much annual leave do I get?"
    assert result["generated_answer"]["text"] == "Employees in Estonia receive 28 calendar days of annual leave."
    assert result["generated_answer"]["sources"] == [
        {
            "chunk_id": "chunk-1",
            "score": 0.91,
            "source_doc": "leave_policy",
            "source_file": "leave_absence_policy.md",
        }
    ]
    assert result["confidence_score"] == 0.95
    assert result["confidence_label"] == "high"


def test_retrieval_graph_returns_low_confidence_without_chunks() -> None:
    retriever = FakeRetriever(results=[])
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "Can I work from another country for six months?",
            "employee_context": {"employee_country": "Estonia"},
        }
    )

    assert result["retrieved_chunks"] == []
    assert "generated_answer" not in result
    assert result["final_response"]["answered"] is False
    assert result["confidence_score"] == 0.0
    assert result["confidence_label"] == "low"
    assert result["confidence_debug"] == {
        "retrieved_count": 0,
        "top_score": 0.0,
        "top_dense_score": 0.0,
        "score_basis": "none",
        "has_sources": False,
        "has_rerank_signal": False,
        "answer_declined": False,
    }


def test_retrieval_graph_deduplicates_answer_sources_by_location() -> None:
    retriever = FakeRetriever(
        results=[
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Annual leave in Estonia is 28 calendar days.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "section_path": "Leave Policy > Estonia",
                },
                score=0.9,
                source="reranked",
                scores={"rerank": 0.9},
            ),
            RetrievedChunk(
                chunk_id="chunk-2",
                text="Leave accrues monthly.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "section_path": "Leave Policy > Estonia",
                },
                score=0.7,
                source="reranked",
                scores={"rerank": 0.7},
            ),
            RetrievedChunk(
                chunk_id="chunk-3",
                text="Portugal annual leave is 22 working days.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "section_path": "Leave Policy > Portugal",
                },
                score=0.6,
                source="reranked",
                scores={"rerank": 0.6},
            ),
            RetrievedChunk(
                chunk_id="chunk-4",
                text="Tampere employees follow Finnish annual holiday rules.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "section_path": "Leave Policy > Finland",
                },
                score=0.5,
                source="reranked",
                scores={"rerank": 0.5},
            ),
            RetrievedChunk(
                chunk_id="chunk-5",
                text="Sick leave requires manager and HR notice.",
                metadata={
                    "source_doc": "leave_policy",
                    "source_file": "leave_absence_policy.md",
                    "section_path": "Leave Policy > Sick Leave",
                },
                score=0.4,
                source="reranked",
                scores={"rerank": 0.4},
            ),
        ]
    )
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "How much annual leave do I get?"})

    assert result["generated_answer"]["sources"] == [
        {
            "chunk_id": "chunk-1",
            "score": 0.9,
            "source_doc": "leave_policy",
            "source_file": "leave_absence_policy.md",
            "section_path": "Leave Policy > Estonia",
        },
        {
            "chunk_id": "chunk-3",
            "score": 0.6,
            "source_doc": "leave_policy",
            "source_file": "leave_absence_policy.md",
            "section_path": "Leave Policy > Portugal",
        },
        {
            "chunk_id": "chunk-4",
            "score": 0.5,
            "source_doc": "leave_policy",
            "source_file": "leave_absence_policy.md",
            "section_path": "Leave Policy > Finland",
        },
    ]


def test_retrieval_graph_caps_confidence_below_perfect_score() -> None:
    retriever = FakeRetriever(
        results=[
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Annual leave in Estonia is 28 calendar days.",
                metadata={"source_doc": "leave_policy"},
                score=0.99,
                source="reranked",
                scores={"rerank": 0.99},
            ),
            RetrievedChunk(
                chunk_id="chunk-2",
                text="Annual leave accrues monthly.",
                metadata={"source_doc": "leave_policy", "section_path": "Accrual"},
                score=0.8,
                source="reranked",
                scores={"rerank": 0.8},
            ),
        ]
    )
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "How much annual leave do I get?"})

    assert result["confidence_score"] == 0.97
    assert result["confidence_label"] == "high"


def test_retrieval_graph_responds_to_user_on_high_confidence() -> None:
    retriever = FakeRetriever()
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "How much annual leave do I get?"})

    assert "respond_to_user" in graph.visited
    assert "answer_not_found" not in graph.visited
    assert "hr_handoff" not in result
    assert result["final_response"] == {
        "text": "Annual leave in Estonia is 28 calendar days.",
        "sources": result["generated_answer"]["sources"],
        "answered": True,
    }


def test_retrieval_graph_responds_to_user_on_medium_confidence() -> None:
    retriever = FakeRetriever(
        results=[
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Remote work abroad needs manager approval.",
                metadata={"source_doc": "employee_handbook"},
                score=0.5,
                source="reranked",
                scores={"rerank": 0.5},
            )
        ]
    )
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "Can I work from abroad?"})

    assert result["confidence_label"] == "medium"
    assert "respond_to_user" in graph.visited
    assert result["final_response"]["answered"] is True


def test_low_confidence_offers_hr_without_generating_an_answer() -> None:
    retriever = FakeRetriever(
        results=[
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Grievances are handled case by case.",
                metadata={
                    "source_doc": "employee_handbook",
                    "source_file": "employee_handbook_v2.1.md",
                },
                score=0.2,
                source="reranked",
                scores={"rerank": 0.2},
            )
        ]
    )
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke(
        {
            "question": "How do I raise a grievance against my manager?",
            "employee_context": {"employee_country": "Estonia"},
        }
    )

    assert result["confidence_label"] == "low"
    assert "answer_not_found" in graph.visited
    assert "generate_answer" not in graph.visited
    assert "respond_to_user" not in graph.visited
    assert result["final_response"] == {
        "text": NOT_FOUND_MESSAGE,
        "sources": [],
        "answered": False,
    }
    assert result["hr_handoff"] == {
        "reason": "low_confidence",
        "contact": HR_CONTACT_EMAIL,
        "question": "How do I raise a grievance against my manager?",
        "employee_context": {"employee_country": "Estonia"},
        "confidence_score": 0.24,
        "confidence_label": "low",
        "draft_answer": "",
        "candidate_sources": [
            {
                "chunk_id": "chunk-1",
                "score": 0.2,
                "source_doc": "employee_handbook",
                "source_file": "employee_handbook_v2.1.md",
            }
        ],
    }


def test_no_documents_found_offers_hr() -> None:
    retriever = FakeRetriever(results=[])
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "Can I bring my dog to the Porto office?"})

    assert "answer_not_found" in graph.visited
    assert result["hr_handoff"]["reason"] == "no_documents_found"
    assert result["hr_handoff"]["candidate_sources"] == []
    assert result["final_response"]["answered"] is False


def _fused_chunk(dense_score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        text="Annual leave in Estonia is 28 calendar days.",
        metadata={"source_doc": "leave_policy", "source_file": "leave_absence_policy.md"},
        score=0.0325,
        source="fused",
        ranks={"dense": 1, "bm25": 1},
        scores={"dense": dense_score, "bm25": 9.1, "fused": 0.0325},
    )


def _build_graph(retriever, answer_generator=fake_answer_generator, message_router=route_to_hr):
    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    return build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=answer_generator,
        message_router=message_router,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )


def test_unreranked_answer_uses_dense_similarity_and_caps_at_medium() -> None:
    graph = _build_graph(FakeRetriever(results=[_fused_chunk(0.92)]))

    result = graph.invoke({"question": "How much annual leave do I get?"})

    assert result["confidence_debug"]["score_basis"] == "dense"
    assert result["confidence_score"] == 0.74
    assert result["confidence_label"] == "medium"
    assert result["final_response"]["answered"] is True


def test_unreranked_off_topic_retrieval_offers_hr() -> None:
    graph = _build_graph(FakeRetriever(results=[_fused_chunk(0.42)]))

    result = graph.invoke({"question": "What's the weather in Tallinn?"})

    assert result["confidence_label"] == "low"
    assert "generate_answer" not in graph.visited
    assert result["hr_handoff"]["reason"] == "low_confidence"


def test_declined_answer_offers_hr_even_with_strong_retrieval() -> None:
    graph = _build_graph(
        FakeRetriever(results=[_fused_chunk(0.8)]),
        answer_generator=lambda question, chunks, **_: "INSUFFICIENT_CONTEXT",
    )

    result = graph.invoke({"question": "Can I bring my dog to the office?"})

    assert result["answer_declined"] is True
    assert result["generated_answer"]["text"] == ""
    assert result["confidence_score"] == 0.0
    assert result["confidence_label"] == "low"
    assert result["hr_handoff"]["reason"] == "answer_declined"
    assert result["hr_handoff"]["candidate_sources"]
    assert result["final_response"] == {"text": NOT_FOUND_MESSAGE, "sources": [], "answered": False}


def test_graph_logs_every_interaction_and_returns_its_id() -> None:
    logged_states: list[dict[str, object]] = []

    def interaction_logger(state):
        logged_states.append(dict(state))
        return "interaction-1"

    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=FakeRetriever(),
        answer_generator=fake_answer_generator,
        interaction_logger=interaction_logger,
        message_router=route_to_hr,
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "How much annual leave do I get?", "session_id": "session-1"})

    assert graph.visited[-1] == "log_interaction"
    assert result["interaction_id"] == "interaction-1"
    assert logged_states[0]["session_id"] == "session-1"
    assert logged_states[0]["final_response"]["answered"] is True


def test_small_talk_is_answered_without_searching_or_offering_hr() -> None:
    retriever = FakeRetriever()
    logged: list[dict[str, object]] = []
    chat_calls: list[dict[str, object]] = []

    def chat_responder(question, **context):
        chat_calls.append({"question": question, **context})
        return "Hi Shishir! What can I help you with?"

    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=fake_answer_generator,
        message_router=lambda question, history: {"kind": "chat", "search_query": ""},
        chat_responder=chat_responder,
        interaction_logger=lambda state: logged.append(state) or "interaction-1",
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    history = [{"question": "hey", "answer": "Hello!"}]
    result = graph.invoke({"question": "hi i'm shishir", "history": history, "employee_context": {}})

    assert graph.visited == ["understand_message", "reply_in_chat", "log_interaction"]
    assert retriever.calls == []
    assert chat_calls[0]["history"] == history
    assert result["final_response"] == {
        "text": "Hi Shishir! What can I help you with?",
        "sources": [],
        "answered": True,
    }
    assert "hr_handoff" not in result
    assert len(logged) == 1


def test_follow_up_searches_with_the_rewritten_question_and_answers_with_history() -> None:
    retriever = FakeRetriever()
    answer_calls: list[dict[str, object]] = []

    def answer_generator(question, chunks, **context):
        answer_calls.append({"question": question, **context})
        return "In Finland you get 25 working days."

    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=SimpleNamespace(),
    )
    graph = build_retrieval_graph(
        engine,
        retriever=retriever,
        answer_generator=answer_generator,
        message_router=lambda question, history: {
            "kind": "hr",
            "search_query": "How much annual leave do employees in Finland get?",
        },
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    history = [{"question": "How much leave do I get?", "answer": "28 calendar days."}]
    graph.invoke(
        {"question": "and in Finland?", "history": history, "employee_context": {"employee_country": "Estonia"}}
    )

    assert retriever.calls[0]["query"] == "How much annual leave do employees in Finland get?"
    assert answer_calls[0]["question"] == "and in Finland?"
    assert answer_calls[0]["history"] == history
    assert answer_calls[0]["employee_context"] == {"employee_country": "Estonia"}


def _filters_for(question, search_query=None):
    graph = _build_graph(
        FakeRetriever(),
        message_router=lambda message, history: {"kind": "hr", "search_query": search_query or message},
    )
    result = graph.invoke({"question": question, "employee_context": {"employee_country": "Estonia"}})
    return result["resolved_filters"].get("country")


def test_country_named_in_the_question_overrides_the_employees_country() -> None:
    assert _filters_for("How much annual leave do I get?") == "Estonia"
    assert _filters_for("and there?", search_query="How much annual leave do employees in Finland get?") == "Finland"
    assert _filters_for("Is there parking at the Porto office?") == "Portugal"
    assert _filters_for("Compare sick pay in Estonia and Finland") is None
