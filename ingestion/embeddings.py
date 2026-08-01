from __future__ import annotations

from typing import Any, Iterable


BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def load_embedding_model(model_name: str = "BAAI/bge-small-en-v1.5") -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "sentence-transformers is required to load the embedding model."
        ) from exc

    return SentenceTransformer(model_name)


def embed_texts(
    model: Any,
    texts: Iterable[str],
    *,
    normalize_embeddings: bool = True,
) -> list[list[float]]:
    embeddings = model.encode(
        list(texts),
        show_progress_bar=False,
        normalize_embeddings=normalize_embeddings,
    )
    return [embedding.tolist() if hasattr(embedding, "tolist") else list(embedding) for embedding in embeddings]


def prepare_query_text(query: str) -> str:
    return f"{BGE_QUERY_INSTRUCTION}{query}"

