from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class IngestedChunk:
    text: str
    metadata: dict[str, Any]
