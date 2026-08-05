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

from retrieval import RetrievalFilters, build_retrieval_engine, retrieve


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask a question and inspect retrieved chunks.")
    parser.add_argument("query", help="Question to retrieve against the corpus.")
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
        help="Number of chunks to show after reranking.",
    )
    parser.add_argument(
        "--dense-top-k",
        type=int,
        default=20,
        help="Dense retrieval candidate count.",
    )
    parser.add_argument(
        "--bm25-top-k",
        type=int,
        default=20,
        help="BM25 candidate count.",
    )
    parser.add_argument(
        "--country",
        help="Optional country filter.",
    )
    parser.add_argument(
        "--doc-type",
        dest="doc_type",
        help="Optional doc_type filter.",
    )
    parser.add_argument(
        "--category",
        help="Optional category filter.",
    )
    parser.add_argument(
        "--source-doc",
        help="Optional source_doc filter.",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Skip Cohere reranking and return fused results directly.",
    )
    return parser.parse_args()


def print_chunk(index: int, chunk: object) -> None:
    metadata = getattr(chunk, "metadata", {}) or {}
    scores = getattr(chunk, "scores", {}) or {}
    ranks = getattr(chunk, "ranks", {}) or {}
    text = str(getattr(chunk, "text", "")).strip()

    print(f"\n[{index}] chunk_id={getattr(chunk, 'chunk_id', 'unknown')}")
    print(f"source={getattr(chunk, 'source', 'unknown')} score={getattr(chunk, 'score', 0.0):.4f}")
    if ranks:
        print(f"ranks={ranks}")
    if scores:
        print(f"scores={scores}")
    print(
        "metadata="
        f"source_file={metadata.get('source_file', 'unknown')} | "
        f"source_doc={metadata.get('source_doc', 'unknown')} | "
        f"doc_type={metadata.get('doc_type', 'unknown')} | "
        f"category={metadata.get('category', 'unknown')} | "
        f"country={metadata.get('country', 'unknown')}"
    )
    location = metadata.get("section_path") or metadata.get("page_number") or metadata.get("row_number")
    if location is not None:
        print(f"location={location}")
    print(f"text={text}")


def main() -> None:
    load_dotenv()
    args = parse_args()

    filters = RetrievalFilters(
        source_doc=args.source_doc,
        doc_type=args.doc_type,
        category=args.category,
        country=args.country,
    )

    client = QdrantClient(url=args.qdrant_url)
    engine = build_retrieval_engine(
        client,
        collection_name=args.collection,
        model_name=args.model,
    )

    results = retrieve(
        engine,
        args.query,
        filters=filters if not filters.is_empty() else None,
        top_n=args.top_n,
        dense_top_k=args.dense_top_k,
        bm25_top_k=args.bm25_top_k,
        apply_reranker=not args.no_rerank,
    )

    print(f"Query: {args.query}")
    if not results:
        print("No retrieved chunks.")
        return

    for index, chunk in enumerate(results, start=1):
        print_chunk(index, chunk)


if __name__ == "__main__":
    main()
