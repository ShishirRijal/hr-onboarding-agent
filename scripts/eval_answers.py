from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import DEFAULT_ANSWER_MODEL, build_retrieval_graph, generate_grounded_answer
from evaluation import (
    DEFAULT_JUDGE_MODEL,
    Judge,
    format_summary,
    judge_results,
    load_conversation_cases,
    load_faq_cases,
    run_cases,
    save_report,
    summarize,
)
from evaluation.runner import DEFAULT_REPORT_DIR, latest_summary
from retrieval import build_retrieval_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the HR assistant on the FAQ log and test conversations, and grade its answers."
    )
    parser.add_argument(
        "--cases",
        choices=["all", "faq", "conversations"],
        default="all",
        help="Which test cases to run.",
    )
    parser.add_argument("--limit", type=int, help="Run only the first N cases (for a quick check).")
    parser.add_argument(
        "--answer-model",
        default=DEFAULT_ANSWER_MODEL,
        help="Model that writes the answers, to compare models before switching.",
    )
    parser.add_argument(
        "--judge-model",
        default=DEFAULT_JUDGE_MODEL,
        help="Model that grades correctness and grounding.",
    )
    parser.add_argument(
        "--corrective-search",
        action="store_true",
        help="Grade the found sections and search again for what they leave out (corrective RAG).",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip the model-graded checks (correctness, grounding); behaviour, sources and country still run.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Where to save the JSON and Markdown reports.",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("QDRANT_COLLECTION", "nordtech_hr"),
        help="Qdrant collection name.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant base URL.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    cases = []
    if args.cases in ("all", "faq"):
        cases += load_faq_cases()
    if args.cases in ("all", "conversations"):
        cases += load_conversation_cases()
    if args.limit:
        cases = cases[: args.limit]

    engine = build_retrieval_engine(QdrantClient(url=args.qdrant_url), collection_name=args.collection)
    # No interaction logger: evaluation runs stay out of the interactions database.
    graph = build_retrieval_graph(
        engine, answer_generator=partial(generate_grounded_answer, model=args.answer_model)
    )
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = sum(len(case.turns) for case in cases)

    def progress(result) -> None:
        mark = "." if result.behaviour_ok else "x"
        print(mark, end="", flush=True)

    print(f"Running {total} turns from {len(cases)} cases ", end="", flush=True)
    retrieval_config = {"apply_reranker": False, "corrective_search": args.corrective_search}
    results = run_cases(graph, cases, on_turn=progress, retrieval_config=retrieval_config)
    print()

    if not args.no_judge:
        print(f"Grading answers with {args.judge_model}...")
        judge_results(results, Judge(model=args.judge_model))

    summary = summarize(results)
    meta = {
        "started_at": started_at,
        "answer_model": args.answer_model,
        "corrective_search": args.corrective_search,
        "judge_model": None if args.no_judge else args.judge_model,
        "cases": args.cases if not args.limit else f"{args.cases} (first {args.limit})",
    }
    json_path, markdown_path = save_report(results, summary, meta, args.out_dir)
    previous = latest_summary(args.out_dir, before=json_path)

    print()
    print(format_summary(summary, previous))
    print(f"\nReport: {markdown_path}")


if __name__ == "__main__":
    main()
