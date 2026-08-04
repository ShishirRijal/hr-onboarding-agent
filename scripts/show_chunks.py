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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect chunks stored in Qdrant.")
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
        "--limit",
        type=int,
        default=20,
        help="Maximum number of chunks to print.",
    )
    parser.add_argument(
        "--source-doc",
        help="Optional source_doc filter.",
    )
    return parser.parse_args()


def format_payload(payload: dict[str, Any]) -> str:
    source_file = payload.get("source_file", "unknown")
    source_doc = payload.get("source_doc", "unknown")
    doc_type = payload.get("doc_type", "unknown")
    category = payload.get("category", "unknown")
    country = payload.get("country", "unknown")
    section_path = payload.get("section_path")
    page_number = payload.get("page_number")
    row_number = payload.get("row_number")
    text = str(payload.get("text", "")).strip()

    location = section_path
    if page_number is not None:
        location = f"page {page_number}"
    elif row_number is not None:
        location = f"row {row_number}"

    lines = [
        f"source_file: {source_file}",
        f"source_doc: {source_doc}",
        f"doc_type: {doc_type}",
        f"category: {category}",
        f"country: {country}",
        f"location: {location or 'unknown'}",
        f"text: {text}",
    ]
    return "\n".join(lines)


def main() -> None:
    load_dotenv()
    args = parse_args()

    try:
        client = QdrantClient(url=args.qdrant_url)
        scroll_kwargs: dict[str, Any] = {
            "collection_name": args.collection,
            "limit": max(1, min(args.limit, 100)),
            "with_payload": True,
            "with_vectors": False,
        }
        if args.source_doc:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            scroll_kwargs["scroll_filter"] = Filter(
                must=[FieldCondition(key="source_doc", match=MatchValue(value=args.source_doc))]
            )

        points, _ = client.scroll(**scroll_kwargs)
    except Exception as exc:
        print(
            f"Error: unable to read from Qdrant at {args.qdrant_url}. "
            "Make sure the container is running and the URL is reachable.",
            file=sys.stderr,
        )
        print(f"Reason: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not points:
        print("No chunks found.")
        return

    for index, point in enumerate(points, start=1):
        payload = point.payload or {}
        print(f"\n[{index}] id={point.id}")
        print(format_payload(payload))


if __name__ == "__main__":
    main()
