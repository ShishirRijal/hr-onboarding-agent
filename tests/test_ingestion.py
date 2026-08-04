from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import (
    build_base_metadata,
    infer_country_from_section,
    ingest_corpus,
    process_markdown_file,
    load_manifest,
    stable_chunk_id,
)


def test_load_manifest_and_build_base_metadata(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: policy
  category: HR
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)
    metadata = build_base_metadata(tmp_path / "sample.md", manifest)

    assert metadata["source_doc"] == "sample_doc"
    assert metadata["doc_type"] == "policy"
    assert metadata["category"] == "HR"
    assert metadata["country"] == "All"
    assert metadata["file_type"] == "md"


def test_build_base_metadata_raises_for_missing_manifest_entry(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: policy
  category: HR
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="No manifest entry for missing.md"):
        build_base_metadata(tmp_path / "missing.md", manifest)


def test_build_base_metadata_raises_for_missing_required_manifest_field(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  category: HR
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="missing required field\\(s\\)"):
        build_base_metadata(tmp_path / "sample.md", manifest)


def test_build_base_metadata_raises_for_invalid_doc_type(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: Handbok
  category: HR
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="invalid doc_type"):
        build_base_metadata(tmp_path / "sample.md", manifest)


def test_build_base_metadata_raises_for_invalid_category(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: policy
  category: People
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="invalid category"):
        build_base_metadata(tmp_path / "sample.md", manifest)


def test_infer_country_from_section() -> None:
    assert infer_country_from_section("Leave Policy > Estonia > Annual Leave") == "Estonia"
    assert infer_country_from_section("Benefits > Portugal > Pension") == "Portugal"
    assert infer_country_from_section("Company Handbook") == "All"


def test_stable_chunk_id_is_deterministic() -> None:
    metadata = {
        "source_doc": "leave_policy",
        "file_type": "markdown",
        "section_path": "Leave Policy > Estonia > Annual Leave",
        "page_number": None,
        "row_number": None,
        "chunk_index": "1.0",
    }

    first = stable_chunk_id(metadata)
    second = stable_chunk_id(metadata)

    assert first == second


def test_ingest_corpus_skips_faq_log(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    (docs_dir / "sample.md").write_text(
        """
# Sample

## Estonia

Annual leave in Estonia is 28 calendar days per year, and employees can take it as soon as it is accrued.
""".strip()
    )
    (docs_dir / "hr_faq_log.csv").write_text(
        "question,ground_truth_answer,source_doc,category,country\n"
        '"Question?","Answer","hr_faq_log","FAQ","All"\n'
    )

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: handbook
  category: HR
  country: All
""".strip()
    )

    chunks = ingest_corpus(docs_dir, manifest_path=manifest_path)

    assert len(chunks) >= 1
    assert all(chunk.metadata["source_file"] != "hr_faq_log.csv" for chunk in chunks)
    assert any(chunk.metadata["country"] == "Estonia" for chunk in chunks)


def test_process_markdown_file_drops_heading_only_chunks(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    markdown_path = docs_dir / "sample.md"
    markdown_path.write_text(
        """
# Sample

## Empty Section

## Body Section
This section has enough text to clear the minimum chunk length and should remain in the corpus.
""".strip()
    )

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
sample.md:
  source_doc: sample_doc
  doc_type: handbook
  category: HR
  country: All
""".strip()
    )

    manifest = load_manifest(manifest_path)
    base_metadata = build_base_metadata(markdown_path, manifest)
    chunks = process_markdown_file(markdown_path, base_metadata)

    assert chunks
    assert all(len(chunk.text.strip()) >= 40 for chunk in chunks)
