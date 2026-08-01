from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from ingestion import (
    embed_texts,
    ingest_corpus,
    load_embedding_model,
    replace_corpus_points,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest NordTech corpus into Qdrant.")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("corpus"),
        help="Directory containing source documents and the corpus manifest.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("corpus/manifest.yaml"),
        help="Path to the corpus manifest file.",
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
    return parser.parse_args()


def summarize_chunks(chunks: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for chunk in chunks:
        grouped[str(chunk.metadata.get("source_doc", "unknown"))].append(chunk)

    summary: list[dict[str, Any]] = []
    for source_doc, items in sorted(grouped.items()):
        summary.append(
            {
                "source_doc": source_doc,
                "source_file": items[0].metadata.get("source_file", "unknown"),
                "doc_type": items[0].metadata.get("doc_type", "unknown"),
                "category": items[0].metadata.get("category", "unknown"),
                "chunk_count": len(items),
                "countries": sorted({str(chunk.metadata.get("country", "All")) for chunk in items}),
            }
        )
    return summary


def print_summary(summary: list[dict[str, Any]]) -> None:
    print("Ingestion summary")
    print("-----------------")
    for item in summary:
        countries = ", ".join(item["countries"])
        print(
            f"{item['source_file']} | {item['source_doc']} | {item['doc_type']} | "
            f"{item['category']} | chunks={item['chunk_count']} | countries={countries}"
        )


def main() -> None:
    load_dotenv()
    args = parse_args()

    chunks = ingest_corpus(
        args.corpus_dir,
        manifest_path=args.manifest,
    )
    if not chunks:
        print("No chunks found. Nothing to ingest.")
        return

    model = load_embedding_model(args.model)
    texts = [chunk.text for chunk in chunks]
    embeddings = embed_texts(model, texts)

    client = QdrantClient(url=args.qdrant_url)
    replace_corpus_points(client, args.collection, chunks, embeddings)

    summary = summarize_chunks(chunks)
    print_summary(summary)
    print(f"\nIngested {len(chunks)} chunks into collection '{args.collection}'.")


if __name__ == "__main__":
    main()
