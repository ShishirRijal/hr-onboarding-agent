from __future__ import annotations

from typing import Sequence

from .models import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RetrievedChunk]],
    *,
    k: int = 60,
) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}

    for ranked_list in ranked_lists:
        for rank, chunk in enumerate(ranked_list, start=1):
            contribution = 1.0 / (k + rank)
            existing = fused.get(chunk.chunk_id)

            if existing is None:
                existing = RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    metadata=dict(chunk.metadata),
                    score=0.0,
                    source="fused",
                    ranks=dict(chunk.ranks),
                    scores=dict(chunk.scores),
                )
                fused[chunk.chunk_id] = existing

            existing.score += contribution
            existing.ranks.update(chunk.ranks)
            existing.scores.update(chunk.scores)

            if not existing.text:
                existing.text = chunk.text
            if not existing.metadata:
                existing.metadata = dict(chunk.metadata)

    return sorted(fused.values(), key=lambda chunk: (-chunk.score, chunk.chunk_id))
