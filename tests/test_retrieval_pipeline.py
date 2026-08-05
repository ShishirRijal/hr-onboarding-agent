from __future__ import annotations

from types import SimpleNamespace

from ingestion.models import IngestedChunk

from retrieval.bm25_index import build_bm25_index
from retrieval.pipeline import RetrievalEngine, retrieve
from retrieval.reranker import rerank


class FakeDenseModel:
    def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
        return [[1.0, 0.0, 0.0]]


class FakeDenseClient:
    def query_points(self, **kwargs):
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="dense-shared",
                    score=0.92,
                    payload={
                        "text": "Annual leave in Estonia is 28 calendar days.",
                        "country": "Estonia",
                    },
                ),
                SimpleNamespace(
                    id="dense-only",
                    score=0.71,
                    payload={
                        "text": "General handbook guidance.",
                        "country": "All",
                    },
                ),
            ]
        )


class FakeRerankerClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def rerank(self, *, model, query, documents, top_n):
        self.calls.append(
            {
                "model": model,
                "query": query,
                "documents": list(documents),
                "top_n": top_n,
            }
        )
        return SimpleNamespace(
            results=[
                SimpleNamespace(index=1, relevance_score=0.95),
                SimpleNamespace(index=0, relevance_score=0.80),
            ]
        )


def test_rerank_reorders_candidates() -> None:
    candidates = [
        SimpleNamespace(
            chunk_id="chunk-1",
            text="first",
            metadata={},
            score=0.1,
            source="fused",
            ranks={},
            scores={"fused": 0.1},
        ),
        SimpleNamespace(
            chunk_id="chunk-2",
            text="second",
            metadata={},
            score=0.2,
            source="fused",
            ranks={},
            scores={"fused": 0.2},
        ),
    ]

    reranked = rerank("query", candidates, top_n=2, client=FakeRerankerClient(), model="test-model")

    assert [chunk.chunk_id for chunk in reranked] == ["chunk-2", "chunk-1"]
    assert reranked[0].source == "reranked"
    assert reranked[0].scores["rerank"] == 0.95


def test_retrieve_runs_dense_bm25_fusion_and_rerank() -> None:
    corpus = [
        IngestedChunk(
            text="Annual leave in Estonia is 28 calendar days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "Estonia",
                "file_type": "markdown",
                "section_path": "Leave > Estonia",
                "chunk_index": "0.0",
            },
        ),
        IngestedChunk(
            text="Annual leave in Portugal is 22 working days.",
            metadata={
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "doc_type": "policy",
                "category": "HR",
                "country": "Portugal",
                "file_type": "markdown",
                "section_path": "Leave > Portugal",
                "chunk_index": "0.1",
            },
        ),
    ]

    engine = RetrievalEngine(
        client=FakeDenseClient(),
        collection_name="nordtech_hr",
        embedding_model=FakeDenseModel(),
        bm25_index=build_bm25_index(corpus),
    )

    reranker_client = FakeRerankerClient()
    results = retrieve(
        engine,
        "annual leave in estonia",
        top_n=2,
        dense_top_k=2,
        bm25_top_k=2,
        reranker_client=reranker_client,
    )

    assert reranker_client.calls
    assert len(results) == 2
    assert results[0].source == "reranked"
    assert results[0].scores["fused"] > 0
    assert results[0].scores["rerank"] == 0.95
