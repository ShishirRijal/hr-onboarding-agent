from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from retrieval.evaluation import evaluate_retrieval, format_eval_report, load_eval_rows
from retrieval.pipeline import build_retrieval_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against the held-out FAQ log.")
    parser.add_argument(
        "--faq-log",
        type=Path,
        default=Path("corpus/hr_faq_log.csv"),
        help="Path to the held-out FAQ CSV.",
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
    parser.add_argument(
        "--model",
        default="BAAI/bge-small-en-v1.5",
        help="Sentence-transformers embedding model.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of chunks to consider for hit@k.",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Evaluate the reranked retrieval pipeline instead of fused retrieval only.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    rows = load_eval_rows(args.faq_log)
    client = QdrantClient(url=args.qdrant_url)
    engine = build_retrieval_engine(
        client,
        collection_name=args.collection,
        model_name=args.model,
    )
    result = evaluate_retrieval(
        engine,
        rows,
        top_n=args.top_n,
        apply_reranker=args.rerank,
    )
    print(format_eval_report(result, top_n=args.top_n))


if __name__ == "__main__":
    main()
