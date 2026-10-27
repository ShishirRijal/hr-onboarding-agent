from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .store import USAGE_CHAT, ModelUsage

# "gpt-4o-mini-2024-07-18" is counted as "gpt-4o-mini".
_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class UsageTotals:
    calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # Calls to a model without a known price, left out of the cost.
    unpriced_calls: int = 0
    # Employees' questions the calls were for.
    questions: set[str] = field(default_factory=set)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, call: ModelUsage) -> None:
        self.calls += 1
        self.input_tokens += call.input_tokens
        self.cached_input_tokens += call.cached_input_tokens
        self.output_tokens += call.output_tokens
        if call.cost_usd is None:
            self.unpriced_calls += 1
        else:
            self.cost_usd += call.cost_usd
        if call.source == USAGE_CHAT and call.interaction_id:
            self.questions.add(call.interaction_id)


def model_name(call: ModelUsage) -> str:
    return _DATED.sub("", call.model)


def totals(calls: Iterable[ModelUsage]) -> UsageTotals:
    result = UsageTotals()
    for call in calls:
        result.add(call)
    return result


def breakdown(calls: Iterable[ModelUsage], key: Callable[[ModelUsage], str]) -> list[tuple[str, UsageTotals]]:
    """Totals per model, step or source, most expensive first."""
    groups: dict[str, UsageTotals] = {}
    for call in calls:
        groups.setdefault(key(call), UsageTotals()).add(call)
    return sorted(groups.items(), key=lambda item: (item[1].cost_usd, item[1].total_tokens), reverse=True)
