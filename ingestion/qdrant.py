from __future__ import annotations

import uuid
from typing import Any

from .models import IngestedChunk


def to_qdrant_points(
    chunks: list[IngestedChunk],
    embeddings: list[list[float]],
    *,
    ids: list[str] | None = None,
) -> list[Any]:
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk and embedding counts must match.")

    try:
        from qdrant_client.http.models import PointStruct
    except ImportError:  # pragma: no cover - dependency guard
        PointStruct = None

    points: list[Any] = []
    for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
        point_id = ids[index] if ids else str(uuid.uuid4())
        payload = {
            **chunk.metadata,
            "text": chunk.text,
        }
        if PointStruct is not None:
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        else:
            points.append({"id": point_id, "vector": vector, "payload": payload})

    return points


def upsert_to_qdrant(
    client: Any,
    collection_name: str,
    chunks: list[IngestedChunk],
    embeddings: list[list[float]],
) -> None:
    """Upsert points by stable ID only.

    This updates existing points when IDs match, but it does not delete stale
    points for removed chunks. Use `replace_document_points` or
    `replace_corpus_points` when re-ingesting editable source documents.
    """
    ids = [stable_chunk_id(chunk.metadata) for chunk in chunks]
    points = to_qdrant_points(chunks, embeddings, ids=ids)
    client.upsert(collection_name=collection_name, points=points)


def replace_document_points(
    client: Any,
    collection_name: str,
    source_doc: str,
    chunks: list[IngestedChunk],
    embeddings: list[list[float]],
) -> None:
    try:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("qdrant-client is required for document replacement.") from exc

    client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="source_doc", match=MatchValue(value=source_doc))]
        ),
    )
    ids = [stable_chunk_id(chunk.metadata) for chunk in chunks]
    points = to_qdrant_points(chunks, embeddings, ids=ids)
    client.upsert(collection_name=collection_name, points=points)


def replace_corpus_points(
    client: Any,
    collection_name: str,
    chunks: list[IngestedChunk],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk and embedding counts must match.")

    grouped: dict[str, list[tuple[IngestedChunk, list[float]]]] = {}
    for chunk, vector in zip(chunks, embeddings, strict=True):
        source_doc = str(chunk.metadata.get("source_doc", ""))
        grouped.setdefault(source_doc, []).append((chunk, vector))

    for source_doc, items in grouped.items():
        grouped_chunks = [chunk for chunk, _ in items]
        grouped_embeddings = [vector for _, vector in items]
        replace_document_points(
            client,
            collection_name,
            source_doc,
            grouped_chunks,
            grouped_embeddings,
        )


def stable_chunk_id(metadata: dict[str, Any]) -> str:
    key_parts = [
        str(metadata.get("source_doc", "")),
        str(metadata.get("file_type", "")),
        str(metadata.get("section_path", "")),
        str(metadata.get("page_number", "")),
        str(metadata.get("row_number", "")),
        str(metadata.get("chunk_index", "")),
    ]
    key = "::".join(key_parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
