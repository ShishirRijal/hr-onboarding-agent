from __future__ import annotations

import csv
import warnings
from pathlib import Path
from typing import Any

from .models import IngestedChunk
from .settings import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE


COUNTRY_MARKERS = {
    "estonia": "Estonia",
    "finland": "Finland",
    "portugal": "Portugal",
}
MIN_MARKDOWN_CHUNK_LENGTH = 40


def process_markdown_file(
    filepath: Path,
    base_metadata: dict[str, Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestedChunk]:
    try:
        from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
    except ImportError:  # pragma: no cover - dependency guard
        MarkdownHeaderTextSplitter = None
        RecursiveCharacterTextSplitter = None
        warnings.warn(
            "langchain_text_splitters is not installed; using fallback markdown and character splitters.",
            RuntimeWarning,
            stacklevel=2,
        )

    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ]

    raw_text = filepath.read_text(encoding="utf-8")
    header_splitter = (
        _MarkdownHeaderSplitter(headers_to_split_on)
        if MarkdownHeaderTextSplitter is None
        else MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    )
    char_splitter = (
        _RecursiveCharacterSplitter(chunk_size, chunk_overlap)
        if RecursiveCharacterTextSplitter is None
        else RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    )

    chunks: list[IngestedChunk] = []
    section_docs = header_splitter.split_text(raw_text)

    for section_index, doc in enumerate(section_docs):
        section_path = _build_section_path(doc.metadata)
        section_country = infer_country_from_section(section_path, default=base_metadata["country"])
        sub_chunks = _merge_short_chunks(char_splitter.split_text(doc.page_content))

        for chunk_index, chunk_text in enumerate(sub_chunks):
            metadata = {
                **base_metadata,
                "file_type": "markdown",
                "section_path": section_path,
                "country": section_country,
                "page_number": None,
                "chunk_index": f"{section_index}.{chunk_index}",
            }
            chunks.append(IngestedChunk(text=chunk_text, metadata=metadata))

    return chunks


def process_csv_file(
    filepath: Path,
    base_metadata: dict[str, Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestedChunk]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:  # pragma: no cover - dependency guard
        RecursiveCharacterTextSplitter = None
        warnings.warn(
            "langchain_text_splitters is not installed; using fallback character splitter for CSV ingestion.",
            RuntimeWarning,
            stacklevel=2,
        )

    char_splitter = (
        _RecursiveCharacterSplitter(chunk_size, chunk_overlap)
        if RecursiveCharacterTextSplitter is None
        else RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    )

    chunks: list[IngestedChunk] = []
    with filepath.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=1):
            text = _row_to_text(row)
            sub_chunks = char_splitter.split_text(text)

            for chunk_index, chunk_text in enumerate(sub_chunks):
                metadata = {
                    **base_metadata,
                    "file_type": "csv",
                    "section_path": row.get("category") or row.get("source_doc") or "faq",
                    "row_number": row_number,
                    "chunk_index": f"{row_number}.{chunk_index}",
                    "question": row.get("question"),
                    "ground_truth_answer": row.get("ground_truth_answer"),
                }
                chunks.append(IngestedChunk(text=chunk_text, metadata=metadata))

    return chunks


def process_pdf_file(
    filepath: Path,
    base_metadata: dict[str, Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestedChunk]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("PDF ingestion requires PyMuPDF (pymupdf).") from exc

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:  # pragma: no cover - dependency guard
        RecursiveCharacterTextSplitter = None
        warnings.warn(
            "langchain_text_splitters is not installed; using fallback character splitter for PDF ingestion.",
            RuntimeWarning,
            stacklevel=2,
        )

    char_splitter = (
        _RecursiveCharacterSplitter(chunk_size, chunk_overlap)
        if RecursiveCharacterTextSplitter is None
        else RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    )

    chunks: list[IngestedChunk] = []
    document = fitz.open(filepath)

    for page_index, page in enumerate(document, start=1):
        page_text = page.get_text().strip()
        if not page_text:
            continue

        sub_chunks = char_splitter.split_text(page_text)
        for chunk_index, chunk_text in enumerate(sub_chunks):
            metadata = {
                **base_metadata,
                "file_type": "pdf",
                "section_path": None,
                "page_number": page_index,
                "chunk_index": f"{page_index}.{chunk_index}",
            }
            chunks.append(IngestedChunk(text=chunk_text, metadata=metadata))

    document.close()
    return chunks


def infer_country_from_section(section_path: str | None, default: str = "All") -> str:
    if not section_path:
        return default

    lowered = section_path.lower()
    for marker, label in COUNTRY_MARKERS.items():
        if marker in lowered:
            return label
    return default


def _build_section_path(metadata: dict[str, Any]) -> str | None:
    parts = [metadata.get("h1"), metadata.get("h2"), metadata.get("h3")]
    cleaned = [part for part in parts if part]
    return " > ".join(cleaned) if cleaned else None


def _row_to_text(row: dict[str, str]) -> str:
    question = (row.get("question") or "").strip()
    answer = (row.get("ground_truth_answer") or row.get("answer") or "").strip()

    if question and answer:
        return f"Question: {question}\nAnswer: {answer}"

    parts: list[str] = []
    for key, value in row.items():
        if value is None:
            continue
        value = value.strip()
        if value:
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def _merge_short_chunks(chunks: list[str], min_length: int = MIN_MARKDOWN_CHUNK_LENGTH) -> list[str]:
    if not chunks:
        return []

    merged: list[str] = []
    buffer = ""

    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue

        candidate = f"{buffer}\n{cleaned}".strip() if buffer else cleaned
        if len(candidate) < min_length:
            buffer = candidate
            continue

        merged.append(candidate)
        buffer = ""

    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]}\n{buffer}".strip()
        elif len(buffer) >= min_length:
            merged.append(buffer)

    return merged


class _MarkdownHeaderSplitter:
    def __init__(self, headers_to_split_on: list[tuple[str, str]]) -> None:
        self.headers_to_split_on = headers_to_split_on

    def split_text(self, text: str) -> list[Any]:
        header_tokens = {prefix: key for prefix, key in self.headers_to_split_on}
        docs: list[Any] = []
        current_lines: list[str] = []
        current_metadata: dict[str, str] = {}

        def flush() -> None:
            if not current_lines:
                return
            page_content = "\n".join(current_lines).strip()
            if not page_content:
                return
            docs.append(type("Doc", (), {"page_content": page_content, "metadata": dict(current_metadata)}))

        for line in text.splitlines():
            stripped = line.strip()
            matched = False
            for prefix, key in header_tokens.items():
                if stripped.startswith(prefix + " "):
                    flush()
                    current_lines = [line]
                    level_text = stripped[len(prefix):].strip()
                    current_metadata[key] = level_text
                    if key == "h1":
                        current_metadata.pop("h2", None)
                        current_metadata.pop("h3", None)
                    elif key == "h2":
                        current_metadata.pop("h3", None)
                    matched = True
                    break
            if not matched:
                current_lines.append(line)

        flush()
        return docs


class _RecursiveCharacterSplitter:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        cleaned = text.strip()
        if len(cleaned) <= self.chunk_size:
            return [cleaned] if cleaned else []

        chunks: list[str] = []
        start = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + self.chunk_size)
            chunk = cleaned[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(cleaned):
                break
            start = max(0, end - self.chunk_overlap)
        return chunks
