from __future__ import annotations

from types import SimpleNamespace

from retrieval.dense_search import dense_search
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.models import RetrievedChunk, RetrievalFilters
from retrieval.settings import DEFAULT_RRF_K


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
        captured = list(texts)
        self.calls.append(captured)
        return [[1.0, 0.0, 0.0]]


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="chunk-1",
                    score=0.91,
                    payload={
                        "text": "Annual leave in Estonia is 28 calendar days.",
                        "country": "Estonia",
                        "source_doc": "leave_policy",
                    },
                ),
                SimpleNamespace(
                    id="chunk-2",
                    score=0.72,
                    payload={
                        "text": "Benefits are described here.",
                        "country": "All",
                        "source_doc": "benefits_guide",
                    },
                ),
            ]
        )


def test_dense_search_prefixes_query_and_forwards_filter() -> None:
    client = FakeClient()
    model = FakeModel()

    results = dense_search(
        client,
        "nordtech_hr",
        "annual leave in estonia",
        model,
        top_k=2,
        filters=RetrievalFilters(country="Estonia"),
    )

    assert model.calls == [["Represent this sentence for searching relevant passages: annual leave in estonia"]]
    assert len(client.calls) == 1
    assert client.calls[0]["collection_name"] == "nordtech_hr"
    assert client.calls[0]["query_filter"] is not None
    assert results[0].source == "dense"
    assert results[0].metadata["country"] == "Estonia"


def test_reciprocal_rank_fusion_merges_duplicate_chunks() -> None:
    dense = [
        RetrievedChunk(
            chunk_id="shared",
            text="Annual leave in Estonia is 28 calendar days.",
            metadata={"country": "Estonia"},
            score=0.91,
            source="dense",
            ranks={"dense": 1},
            scores={"dense": 0.91},
        ),
        RetrievedChunk(
            chunk_id="dense-only",
            text="Another dense-only chunk.",
            metadata={"country": "All"},
            score=0.7,
            source="dense",
            ranks={"dense": 2},
            scores={"dense": 0.7},
        ),
    ]
    bm25 = [
        RetrievedChunk(
            chunk_id="shared",
            text="Annual leave in Estonia is 28 calendar days.",
            metadata={"country": "Estonia"},
            score=0.8,
            source="bm25",
            ranks={"bm25": 1},
            scores={"bm25": 0.8},
        ),
        RetrievedChunk(
            chunk_id="bm25-only",
            text="Another bm25-only chunk.",
            metadata={"country": "All"},
            score=0.6,
            source="bm25",
            ranks={"bm25": 2},
            scores={"bm25": 0.6},
        ),
    ]

    fused = reciprocal_rank_fusion([dense, bm25], k=DEFAULT_RRF_K)

    assert [chunk.chunk_id for chunk in fused] == ["shared", "bm25-only", "dense-only"]
    assert fused[0].source == "fused"
    assert fused[0].ranks == {"dense": 1, "bm25": 1}
    assert fused[0].scores == {"dense": 0.91, "bm25": 0.8}
    expected_score = (1 / (DEFAULT_RRF_K + 1)) + (1 / (DEFAULT_RRF_K + 1))
    assert fused[0].score == expected_score
