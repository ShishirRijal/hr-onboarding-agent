from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ingestion.embeddings import load_embedding_model
from ingestion.models import IngestedChunk

from .bm25_index import BM25Index, build_bm25_index, bm25_search
from .dense_search import dense_search
from .fusion import reciprocal_rank_fusion
from .models import RetrievedChunk, RetrievalFilters
from .reranker import rerank
from .settings import (
    DEFAULT_BM25_TOP_K,
    DEFAULT_COHERE_RERANK_MODEL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DENSE_TOP_K,
    DEFAULT_RERANK_TOP_N,
    DEFAULT_RRF_K,
)


@dataclass(slots=True)
class RetrievalEngine:
    client: Any
    collection_name: str
    embedding_model: Any
    bm25_index: BM25Index


def build_retrieval_engine(
    client: Any,
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    model_name: str = "BAAI/bge-small-en-v1.5",
) -> RetrievalEngine:
    chunks = scroll_qdrant_chunks(client, collection_name)
    if not chunks:
        raise RuntimeError(f"No chunks found in Qdrant collection '{collection_name}'.")

    return RetrievalEngine(
        client=client,
        collection_name=collection_name,
        embedding_model=load_embedding_model(model_name),
        bm25_index=build_bm25_index(chunks),
    )


def scroll_qdrant_chunks(client: Any, collection_name: str, *, page_size: int = 256) -> list[IngestedChunk]:
    chunks: list[IngestedChunk] = []
    offset: str | None = None

    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for record in records:
            payload = record.payload or {}
            text = str(payload.get("text", "")).strip()
            if not text:
                continue

            metadata = {key: value for key, value in payload.items() if key != "text"}
            chunks.append(IngestedChunk(text=text, metadata=metadata))

        if not offset:
            break

    return chunks


def retrieve(
    engine: RetrievalEngine,
    query: str,
    *,
    filters: RetrievalFilters | None = None,
    top_n: int = DEFAULT_RERANK_TOP_N,
    dense_top_k: int = DEFAULT_DENSE_TOP_K,
    bm25_top_k: int = DEFAULT_BM25_TOP_K,
    reranker_client: Any | None = None,
    reranker_model: str = DEFAULT_COHERE_RERANK_MODEL,
    apply_reranker: bool = True,
) -> list[RetrievedChunk]:
    if top_n <= 0:
        return []

    dense = dense_search(
        engine.client,
        engine.collection_name,
        query,
        engine.embedding_model,
        top_k=dense_top_k,
        filters=filters,
    )
    bm25 = bm25_search(
        engine.bm25_index,
        query,
        top_k=bm25_top_k,
        filters=filters,
    )

    fused = reciprocal_rank_fusion([dense, bm25], k=DEFAULT_RRF_K)
    for chunk in fused:
        chunk.scores.setdefault("fused", chunk.score)

    if not apply_reranker:
        return fused[:top_n]

    reranked = rerank(
        query,
        fused,
        top_n=top_n,
        client=reranker_client,
        model=reranker_model,
    )
    return reranked[:top_n]
