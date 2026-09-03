from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import RetrievedChunk, RetrievalFilters
from .pipeline import RetrievalEngine, retrieve

EXCLUDED_EVAL_SOURCE_DOCS = {"", "none", "n/a"}


@dataclass(slots=True)
class RetrievalEvalRow:
    question: str
    ground_truth_answer: str
    source_doc: str
    category: str
    country: str


@dataclass(slots=True)
class RetrievalEvalResult:
    total_rows: int
    evaluated_rows: int
    hit_at_1: float
    hit_at_k: float
    mean_reciprocal_rank: float
    misses: list[dict[str, Any]]


def load_eval_rows(path: Path) -> list[RetrievalEvalRow]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[RetrievalEvalRow] = []
        for row in reader:
            rows.append(
                RetrievalEvalRow(
                    question=(row.get("question") or "").strip(),
                    ground_truth_answer=(row.get("ground_truth_answer") or "").strip(),
                    source_doc=(row.get("source_doc") or "").strip(),
                    category=(row.get("category") or "").strip(),
                    country=(row.get("country") or "").strip(),
                )
            )
    return rows


def evaluate_retrieval(
    engine: RetrievalEngine,
    rows: Sequence[RetrievalEvalRow],
    *,
    top_n: int = 5,
    apply_reranker: bool = False,
) -> RetrievalEvalResult:
    evaluated_rows = 0
    hit_at_1 = 0
    hit_at_k = 0
    reciprocal_ranks = 0.0
    misses: list[dict[str, Any]] = []

    for row in rows:
        expected_source_doc = row.source_doc.lower()
        if expected_source_doc in EXCLUDED_EVAL_SOURCE_DOCS:
            continue

        filters = RetrievalFilters(
            country=row.country if row.country and row.country.lower() not in {"all", "any"} else None,
        )
        results = retrieve(
            engine,
            row.question,
            filters=filters if not filters.is_empty() else None,
            top_n=top_n,
            apply_reranker=apply_reranker,
        )

        evaluated_rows += 1
        result_source_docs = [str(chunk.metadata.get("source_doc", "")).lower() for chunk in results]
        match_rank = _first_match_rank(result_source_docs, expected_source_doc)

        if match_rank is None:
            misses.append(
                {
                    "question": row.question,
                    "expected_source_doc": row.source_doc,
                    "retrieved_source_docs": result_source_docs,
                }
            )
            continue

        reciprocal_ranks += 1.0 / match_rank
        if match_rank == 1:
            hit_at_1 += 1
        if match_rank <= top_n:
            hit_at_k += 1

    if evaluated_rows == 0:
        return RetrievalEvalResult(
            total_rows=len(rows),
            evaluated_rows=0,
            hit_at_1=0.0,
            hit_at_k=0.0,
            mean_reciprocal_rank=0.0,
            misses=misses,
        )

    return RetrievalEvalResult(
        total_rows=len(rows),
        evaluated_rows=evaluated_rows,
        hit_at_1=hit_at_1 / evaluated_rows,
        hit_at_k=hit_at_k / evaluated_rows,
        mean_reciprocal_rank=reciprocal_ranks / evaluated_rows,
        misses=misses,
    )


def format_eval_report(result: RetrievalEvalResult, *, top_n: int) -> str:
    lines = [
        "Retrieval Evaluation",
        "--------------------",
        f"rows_loaded={result.total_rows}",
        f"rows_evaluated={result.evaluated_rows}",
        f"hit@1={result.hit_at_1:.3f}",
        f"hit@{top_n}={result.hit_at_k:.3f}",
        f"mrr={result.mean_reciprocal_rank:.3f}",
    ]
    if result.misses:
        lines.append("")
        lines.append("Misses")
        lines.append("------")
        for miss in result.misses[:5]:
            lines.append(
                f"- expected={miss['expected_source_doc']} | retrieved={miss['retrieved_source_docs']} | "
                f"question={miss['question']}"
            )
    return "\n".join(lines)


def _first_match_rank(items: Iterable[str], expected: str) -> int | None:
    for index, item in enumerate(items, start=1):
        if item == expected:
            return index
    return None
