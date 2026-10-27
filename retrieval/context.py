from __future__ import annotations

from typing import Any, Sequence

# How many pieces either side of a found piece are read with it. Sections are split into
# ~500-character pieces, so the condition that matters (an approver, the day a rule
# changes) is often in the next piece of the same section.
DEFAULT_NEIGHBOURS = 1
# Shorter matches between the end of one piece and the start of the next are coincidence
# (a full stop, a common word), not the splitter's overlap.
MIN_OVERLAP = 15


def expand_with_neighbours(
    index: Any,
    chunks: Sequence[dict[str, Any]],
    *,
    neighbours: int = DEFAULT_NEIGHBOURS,
) -> list[dict[str, Any]]:
    """Turns each found piece into a passage: the piece plus its neighbours in the same
    section, with the overlap between them removed. Pieces that end up next to each other
    become one passage. Each passage keeps the id and metadata of its best-ranked piece, so
    citing it still opens and highlights what search found."""
    siblings = _sections(index)
    if not siblings:
        return [dict(chunk) for chunk in chunks]

    # Section key -> the piece positions to read, and the best-ranked found piece per run.
    wanted: dict[tuple[Any, ...], set[int]] = {}
    found_at: dict[tuple[Any, ...], dict[int, int]] = {}
    passages: list[tuple[int, dict[str, Any]]] = []
    for rank, chunk in enumerate(chunks):
        key, position = _locate(chunk)
        section = siblings.get(key) if key else None
        if section is None or position not in section:
            passages.append((rank, dict(chunk)))
            continue
        span = range(position - neighbours, position + neighbours + 1)
        wanted.setdefault(key, set()).update(p for p in span if p in section)
        found_at.setdefault(key, {}).setdefault(position, rank)

    for key, positions in wanted.items():
        section = siblings[key]
        for run in _runs(sorted(positions)):
            ranks = {position: rank for position, rank in found_at[key].items() if position in run}
            best_position = min(ranks, key=ranks.get)
            best = next(chunk for chunk in chunks if _locate(chunk) == (key, best_position))
            passage = dict(best)
            passage["text"] = _join([section[position]["text"] for position in run])
            passage["metadata"] = {**(best.get("metadata") or {}), "passage_chunk_ids": [section[p]["chunk_id"] for p in run]}
            passages.append((ranks[best_position], passage))

    return [passage for _, passage in sorted(passages, key=lambda item: item[0])]


def passage_chunk_ids(chunk: dict[str, Any]) -> list[str]:
    """Every piece a passage was built from, so a later search doesn't add them again."""
    metadata = chunk.get("metadata") or {}
    return list(metadata.get("passage_chunk_ids") or [chunk.get("chunk_id")])


def _sections(index: Any) -> dict[tuple[Any, ...], dict[int, dict[str, Any]]]:
    chunks = getattr(index, "chunks", None)
    chunk_ids = getattr(index, "chunk_ids", None)
    if not chunks or not chunk_ids:
        return {}
    sections: dict[tuple[Any, ...], dict[int, dict[str, Any]]] = {}
    for chunk_id, chunk in zip(chunk_ids, chunks):
        key, position = _locate({"metadata": chunk.metadata})
        if key is not None:
            sections.setdefault(key, {})[position] = {"chunk_id": chunk_id, "text": chunk.text}
    return sections


def _locate(chunk: dict[str, Any]) -> tuple[tuple[Any, ...] | None, int]:
    """The section a piece belongs to and its position in it, from chunk_index "section.piece"."""
    metadata = chunk.get("metadata") or {}
    section, _, piece = str(metadata.get("chunk_index") or "").partition(".")
    if not section or not piece.isdigit():
        return None, -1
    return (metadata.get("source_file"), metadata.get("section_path"), section), int(piece)


def _runs(positions: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for position in positions:
        if runs and position == runs[-1][-1] + 1:
            runs[-1].append(position)
        else:
            runs.append([position])
    return runs


def _join(texts: list[str]) -> str:
    """Joins consecutive pieces, dropping the text each one repeats from the one before."""
    joined = texts[0].strip()
    for text in texts[1:]:
        text = text.strip()
        overlap = next(
            (
                size
                for size in range(min(len(joined), len(text)), MIN_OVERLAP - 1, -1)
                if joined.endswith(text[:size])
            ),
            0,
        )
        separator = "" if overlap else "\n"
        joined += separator + text[overlap:]
    return joined
