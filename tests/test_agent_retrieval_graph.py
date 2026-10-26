from __future__ import annotations

from types import SimpleNamespace

from agent import HR_CONTACT_EMAIL, build_retrieval_graph
from agent.escalation import ESCALATION_MESSAGE
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


def fake_answer_generator(question, chunks):
    del question
    return str(chunks[0]["text"])


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

    def answer_generator(question, chunks):
        answer_generator_calls.append({"question": question, "chunks": chunks})
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
    assert result["generated_answer"]["sources"] == []
    assert "could not find enough information" in result["generated_answer"]["text"]
    assert result["confidence_score"] == 0.0
    assert result["confidence_label"] == "low"
    assert result["confidence_debug"] == {
        "retrieved_count": 0,
        "top_score": 0.0,
        "has_answer": True,
        "has_sources": False,
        "has_rerank_signal": False,
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
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "How much annual leave do I get?"})

    assert graph.visited[-1] == "respond_to_user"
    assert "escalate_to_hr" not in graph.visited
    assert "escalation" not in result
    assert result["final_response"] == {
        "text": "Annual leave in Estonia is 28 calendar days.",
        "sources": result["generated_answer"]["sources"],
        "escalated": False,
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
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "Can I work from abroad?"})

    assert result["confidence_label"] == "medium"
    assert graph.visited[-1] == "respond_to_user"
    assert result["final_response"]["escalated"] is False


def test_retrieval_graph_escalates_to_hr_on_low_confidence() -> None:
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
    assert graph.visited[-1] == "escalate_to_hr"
    assert "respond_to_user" not in graph.visited
    assert result["final_response"] == {
        "text": ESCALATION_MESSAGE,
        "sources": [],
        "escalated": True,
    }
    assert result["escalation"] == {
        "reason": "low_confidence",
        "contact": HR_CONTACT_EMAIL,
        "question": "How do I raise a grievance against my manager?",
        "employee_context": {"employee_country": "Estonia"},
        "confidence_score": 0.24,
        "confidence_label": "low",
        "draft_answer": "Grievances are handled case by case.",
        "candidate_sources": result["generated_answer"]["sources"],
    }


def test_retrieval_graph_escalates_when_no_documents_found() -> None:
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
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )

    result = graph.invoke({"question": "Can I bring my dog to the Porto office?"})

    assert graph.visited[-1] == "escalate_to_hr"
    assert result["escalation"]["reason"] == "no_documents_found"
    assert result["escalation"]["candidate_sources"] == []
    assert result["final_response"]["escalated"] is True
