from __future__ import annotations

from types import SimpleNamespace

from retrieval.evaluation import RetrievalEvalRow, evaluate_retrieval


class FakeEngine:
    pass


def test_evaluate_retrieval_computes_hit_rate_and_mrr(monkeypatch) -> None:
    rows = [
        RetrievalEvalRow(
            question="Q1",
            ground_truth_answer="A1",
            source_doc="it_guide",
            category="IT",
            country="All",
        ),
        RetrievalEvalRow(
            question="Q2",
            ground_truth_answer="A2",
            source_doc="leave_policy",
            category="HR",
            country="Estonia",
        ),
        RetrievalEvalRow(
            question="Q3",
            ground_truth_answer="A3",
            source_doc="NONE",
            category="Escalation",
            country="All",
        ),
    ]

    def fake_retrieve(engine, query, **kwargs):
        if query == "Q1":
            return [
                SimpleNamespace(metadata={"source_doc": "it_guide"}),
                SimpleNamespace(metadata={"source_doc": "leave_policy"}),
            ]
        if query == "Q2":
            return [
                SimpleNamespace(metadata={"source_doc": "benefits_guide"}),
                SimpleNamespace(metadata={"source_doc": "leave_policy"}),
            ]
        return []

    monkeypatch.setattr("retrieval.evaluation.retrieve", fake_retrieve)

    result = evaluate_retrieval(FakeEngine(), rows, top_n=2, apply_reranker=False)

    assert result.total_rows == 3
    assert result.evaluated_rows == 2
    assert result.hit_at_1 == 0.5
    assert result.hit_at_k == 1.0
    assert result.mean_reciprocal_rank == 0.75
    assert result.misses == []
