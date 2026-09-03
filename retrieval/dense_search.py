from __future__ import annotations

from typing import Any

from ingestion.embeddings import embed_texts, prepare_query_text

from .models import RetrievedChunk, RetrievalFilters


def dense_search(
    client: Any,
    collection_name: str,
    query: str,
    model: Any,
    *,
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[RetrievedChunk]:
    if top_k <= 0:
        return []

    query_text = prepare_query_text(query)
    query_vector = embed_texts(model, [query_text])[0]
    query_filter = filters.to_qdrant_filter() if filters is not None else None

    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
        with_vectors=False,
    )

    points = getattr(response, "points", []) or []
    results: list[RetrievedChunk] = []
    for rank, point in enumerate(points, start=1):
        payload = point.payload or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            continue

        metadata = {key: value for key, value in payload.items() if key != "text"}
        score = float(point.score)
        results.append(
            RetrievedChunk(
                chunk_id=str(point.id),
                text=text,
                metadata=metadata,
                score=score,
                source="dense",
                ranks={"dense": rank},
                scores={"dense": score},
            )
        )

    return results
