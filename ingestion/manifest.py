from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_MANIFEST_PATH = Path("corpus/manifest.yaml")
ALLOWED_DOC_TYPES = {
    "handbook",
    "checklist",
    "guide",
    "policy",
    "directory",
    "summary",
    "faq_log",
}
ALLOWED_CATEGORIES = {
    "HR",
    "IT",
    "Benefits",
    "Finance",
    "Org",
    "Legal",
    "FAQ",
}


def load_manifest(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError("Manifest must be a mapping of filename to metadata.")

    manifest: dict[str, dict[str, Any]] = {}
    for filename, entry in loaded.items():
        if not isinstance(filename, str):
            raise ValueError("Manifest keys must be filenames.")
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry for {filename} must be a mapping.")
        manifest[filename] = entry

    return manifest


def build_base_metadata(filepath: Path, manifest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = manifest.get(filepath.name)
    if entry is None:
        raise ValueError(
            f"No manifest entry for {filepath.name}. Add it to {DEFAULT_MANIFEST_PATH} before ingesting."
        )

    required_fields = ("doc_type", "category")
    missing = [field for field in required_fields if field not in entry]
    if missing:
        raise ValueError(
            f"Manifest entry for {filepath.name} is missing required field(s): {missing}"
        )

    doc_type = entry["doc_type"]
    category = entry["category"]
    if doc_type not in ALLOWED_DOC_TYPES:
        raise ValueError(
            f"Manifest entry for {filepath.name} has invalid doc_type {doc_type!r}. "
            f"Allowed values: {sorted(ALLOWED_DOC_TYPES)}"
        )
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Manifest entry for {filepath.name} has invalid category {category!r}. "
            f"Allowed values: {sorted(ALLOWED_CATEGORIES)}"
        )

    return {
        "source_doc": entry.get("source_doc", filepath.stem),
        "doc_type": doc_type,
        "category": category,
        "country": entry.get("country", "All"),
        "file_type": filepath.suffix.lower().lstrip("."),
        "source_file": filepath.name,
        "section_path": None,
        "page_number": None,
        "row_number": None,
        "chunk_index": None,
    }
