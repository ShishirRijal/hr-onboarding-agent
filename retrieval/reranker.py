from __future__ import annotations

import os
from typing import Any

from .models import RetrievedChunk
from .settings import DEFAULT_COHERE_RERANK_MODEL


def rerank(
    query: str,
    candidates: list[RetrievedChunk],
    *,
    top_n: int = 5,
    client: Any | None = None,
    model: str = DEFAULT_COHERE_RERANK_MODEL,
) -> list[RetrievedChunk]:
    if not candidates or top_n <= 0:
        return []

    if client is None:
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            return candidates[:top_n]

        try:
            import cohere
        except ImportError:
            return candidates[:top_n]

        client = cohere.ClientV2(api_key=api_key)

    response = client.rerank(
        model=model,
        query=query,
        documents=[candidate.text for candidate in candidates],
        top_n=min(top_n, len(candidates)),
    )

    ranked_results = getattr(response, "results", []) or []
    reranked: list[RetrievedChunk] = []
    for rank, result in enumerate(ranked_results, start=1):
        index = int(getattr(result, "index"))
        if index < 0 or index >= len(candidates):
            continue

        source_candidate = candidates[index]
        score = float(getattr(result, "relevance_score", getattr(result, "score", 0.0)))
        reranked.append(
            RetrievedChunk(
                chunk_id=source_candidate.chunk_id,
                text=source_candidate.text,
                metadata=dict(source_candidate.metadata),
                score=score,
                source="reranked",
                ranks={**source_candidate.ranks, "rerank": rank},
                scores={**source_candidate.scores, "rerank": score},
            )
        )

    return reranked or candidates[:top_n]
