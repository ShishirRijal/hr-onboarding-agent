from __future__ import annotations

from pathlib import Path

from .chunking import process_csv_file, process_markdown_file, process_pdf_file
from .manifest import DEFAULT_MANIFEST_PATH, build_base_metadata, load_manifest
from .models import IngestedChunk
from .settings import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    EXCLUDED_FROM_INGESTION,
    SUPPORTED_EXTENSIONS,
)


def iter_source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.name not in EXCLUDED_FROM_INGESTION
    )


def ingest_corpus(
    source_dir: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestedChunk]:
    return load_corpus(
        source_dir,
        manifest_path=manifest_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def load_corpus(
    source_dir: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestedChunk]:
    manifest = load_manifest(manifest_path)
    chunks: list[IngestedChunk] = []

    for filepath in iter_source_files(source_dir):
        base_metadata = build_base_metadata(filepath, manifest)
        suffix = filepath.suffix.lower()

        if suffix in {".md", ".markdown"}:
            chunks.extend(
                process_markdown_file(
                    filepath,
                    base_metadata,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            )
        elif suffix == ".csv":
            chunks.extend(
                process_csv_file(
                    filepath,
                    base_metadata,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            )
        elif suffix == ".pdf":
            chunks.extend(
                process_pdf_file(
                    filepath,
                    base_metadata,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            )

    return chunks
