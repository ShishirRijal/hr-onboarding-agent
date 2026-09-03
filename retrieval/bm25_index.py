from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from rank_bm25 import BM25Plus

from ingestion.models import IngestedChunk
from ingestion.qdrant import stable_chunk_id

from .models import RetrievedChunk, RetrievalFilters

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(slots=True)
class BM25Index:
    chunks: list[IngestedChunk]
    chunk_ids: list[str]
    tokenized_corpus: list[list[str]]
    bm25: BM25Plus | None

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        return bm25_search(self, query, top_k=top_k, filters=filters)


def build_bm25_index(chunks: Sequence[IngestedChunk]) -> BM25Index:
    chunk_list = list(chunks)
    chunk_ids = [stable_chunk_id(chunk.metadata) for chunk in chunk_list]
    tokenized_corpus = [tokenize_text(chunk.text) for chunk in chunk_list]
    bm25 = BM25Plus(tokenized_corpus) if tokenized_corpus else None
    return BM25Index(
        chunks=chunk_list,
        chunk_ids=chunk_ids,
        tokenized_corpus=tokenized_corpus,
        bm25=bm25,
    )


def bm25_search(
    index: BM25Index,
    query: str,
    *,
    top_k: int,
    filters: RetrievalFilters | None = None,
) -> list[RetrievedChunk]:
    if index.bm25 is None or top_k <= 0:
        return []

    query_tokens = tokenize_text(query)
    if not query_tokens:
        return []

    scores = index.bm25.get_scores(query_tokens)
    candidate_rows = _filtered_rows(index.chunks, filters)
    ranked_rows = sorted(
        candidate_rows,
        key=lambda row: scores[row],
        reverse=True,
    )

    results: list[RetrievedChunk] = []
    for rank, row in enumerate(ranked_rows, start=1):
        score = float(scores[row])
        chunk = index.chunks[row]
        results.append(
            RetrievedChunk(
                chunk_id=index.chunk_ids[row],
                text=chunk.text,
                metadata=dict(chunk.metadata),
                score=score,
                source="bm25",
                ranks={"bm25": rank},
                scores={"bm25": score},
            )
        )
        if len(results) >= top_k:
            break

    return results


def tokenize_text(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _filtered_rows(
    chunks: Sequence[IngestedChunk],
    filters: RetrievalFilters | None,
) -> list[int]:
    if filters is None or filters.is_empty():
        return list(range(len(chunks)))

    return [index for index, chunk in enumerate(chunks) if filters.matches(chunk.metadata)]
