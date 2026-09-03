from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float = 0.0
    source: str = "unknown"
    ranks: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalFilters:
    source_doc: str | None = None
    source_file: str | None = None
    doc_type: str | None = None
    category: str | None = None
    country: str | None = None
    file_type: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "source_doc": self.source_doc,
                "source_file": self.source_file,
                "doc_type": self.doc_type,
                "category": self.category,
                "country": self.country,
                "file_type": self.file_type,
            }.items()
            if value is not None
        }

    def is_empty(self) -> bool:
        return not self.as_dict()

    def matches(self, metadata: dict[str, Any]) -> bool:
        for key, value in self.as_dict().items():
            if str(metadata.get(key)) != value:
                return False
        return True

    def to_qdrant_filter(self) -> Any | None:
        if self.is_empty():
            return None

        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in self.as_dict().items()
            ]
        )
