from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import build_retrieval_graph
from agent.usage import UsageTracker, describe_usage
from interactions import USAGE_SCRIPT, InteractionStore
from retrieval import build_retrieval_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the HR onboarding agent a question.")
    parser.add_argument("question", help="Question to ask the agent.")
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
    parser.add_argument(
        "--embedding-model",
        default="BAAI/bge-small-en-v1.5",
        help="Sentence-transformers embedding model.",
    )
    parser.add_argument("--employee-country", help="Optional employee country context.")
    parser.add_argument("--office-country", help="Optional office country context.")
    parser.add_argument("--country", help="Optional explicit retrieval country override.")
    parser.add_argument("--doc-type", help="Optional doc_type retrieval override.")
    parser.add_argument("--category", help="Optional category retrieval override.")
    parser.add_argument("--source-doc", help="Optional source_doc retrieval override.")
    parser.add_argument("--top-n", type=int, default=5, help="Number of chunks after reranking.")
    parser.add_argument("--dense-top-k", type=int, default=20, help="Dense retrieval candidate count.")
    parser.add_argument("--bm25-top-k", type=int, default=20, help="BM25 retrieval candidate count.")
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip Cohere reranking and return fused retrieval results.",
    )
    parser.add_argument(
        "--corrective-search",
        action="store_true",
        help="Grade the found sections and search again for what they leave out.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    client = QdrantClient(url=args.qdrant_url)
    engine = build_retrieval_engine(
        client,
        collection_name=args.collection,
        model_name=args.embedding_model,
    )
    graph = build_retrieval_graph(engine)

    state: dict[str, Any] = {
        "question": args.question,
        "employee_context": {
            key: value
            for key, value in {
                "employee_country": args.employee_country,
                "office_country": args.office_country,
            }.items()
            if value
        },
        "retrieval_overrides": {
            key: value
            for key, value in {
                "country": args.country,
                "doc_type": args.doc_type,
                "category": args.category,
                "source_doc": args.source_doc,
            }.items()
            if value
        },
        "retrieval_config": {
            "top_n": args.top_n,
            "dense_top_k": args.dense_top_k,
            "bm25_top_k": args.bm25_top_k,
            "apply_reranker": not args.no_rerank,
            "corrective_search": args.corrective_search,
        },
    }

    usage = UsageTracker()
    try:
        result = graph.invoke(state, config={"callbacks": [usage]})
    finally:
        InteractionStore().record_model_calls(usage.calls, source=USAGE_SCRIPT)
    response = result.get("final_response", {})
    sources = response.get("sources", [])

    print("\nAnswer")
    print("------")
    print(response.get("text", "No answer generated."))

    print("\nConfidence")
    print("----------")
    print(f"{result.get('confidence_label', 'unknown')} ({result.get('confidence_score', 0.0)})")

    handoff = result.get("hr_handoff")
    if handoff:
        print("\nNot found in the HR documents (employee is offered to ask HR)")
        print("-------------------------------------------------------------")
        print(f"reason={handoff['reason']} | contact={handoff['contact']}")
        print(f"draft answer (not shown to employee): {handoff['draft_answer'] or '(none)'}")
        sources = handoff["candidate_sources"]

    print("\nSources")
    print("-------")
    if not sources:
        print("No sources.")
    for index, source in enumerate(sources, start=1):
        source_file = source.get("source_file") or source.get("source_doc") or "unknown"
        location = source.get("section_path") or source.get("page_number") or source.get("row_number")
        score = source.get("score", 0.0)
        location_text = f" | {location}" if location is not None else ""
        print(f"[{index}] {source_file}{location_text} | score={score}")

    print("\nDebug")
    print("-----")
    print(f"retrieval={result.get('retrieval_debug', {})}")
    print(f"confidence={result.get('confidence_debug', {})}")

    print("\nModel usage")
    print("-----------")
    print(describe_usage(usage.calls))


if __name__ == "__main__":
    main()
