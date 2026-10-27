from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# OpenAI's list prices in US dollars per million tokens: input, cached input, output.
# From https://openai.com/api/pricing; update them here if OpenAI changes them.
MODEL_PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4o": (2.50, 1.25, 10.00),
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
}
# "gpt-4o-mini-2024-07-18" is priced as "gpt-4o-mini".
_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class ModelCall:
    """One call to a language model: which model, for which step, and the tokens it used."""

    model: str
    step: str | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float | None:
        """What the call cost at list prices; None for a model without a price."""
        prices = MODEL_PRICES.get(base_model(self.model))
        if prices is None:
            return None
        input_price, cached_price, output_price = prices
        uncached = self.input_tokens - self.cached_input_tokens
        return (uncached * input_price + self.cached_input_tokens * cached_price + self.output_tokens * output_price) / 1e6


def base_model(model: str) -> str:
    return _DATED.sub("", model)


class UsageTracker(BaseCallbackHandler):
    """Collects every model call in one run of the agent, with the graph step it ran in
    ("generate_answer", "check_answer", ...). Pass it in the run's callbacks."""

    def __init__(self, *, step: str | None = None) -> None:
        self.calls: list[ModelCall] = []
        # Calls made outside the graph (the evaluation judge) are recorded under this step.
        self._default_step = step
        self._steps: dict[UUID, str | None] = {}
        self._lock = threading.Lock()

    def on_chat_model_start(self, serialized: Any, messages: Any, *, run_id: UUID, metadata: dict | None = None, **kwargs: Any) -> None:
        self._steps[run_id] = (metadata or {}).get("langgraph_node") or self._default_step

    def on_llm_start(self, serialized: Any, prompts: Any, *, run_id: UUID, metadata: dict | None = None, **kwargs: Any) -> None:
        self._steps[run_id] = (metadata or {}).get("langgraph_node") or self._default_step

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        step = self._steps.pop(run_id, self._default_step)
        fallback_model = str((response.llm_output or {}).get("model_name") or "unknown")
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if not usage:
                    continue
                model = str((getattr(message, "response_metadata", None) or {}).get("model_name") or fallback_model)
                call = ModelCall(
                    model=model,
                    step=step,
                    input_tokens=int(usage.get("input_tokens", 0)),
                    cached_input_tokens=int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0),
                    output_tokens=int(usage.get("output_tokens", 0)),
                )
                with self._lock:
                    self.calls.append(call)

    @property
    def total_tokens(self) -> int:
        return sum(call.input_tokens + call.output_tokens for call in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(call.cost_usd or 0.0 for call in self.calls)


def describe_usage(calls: list[ModelCall]) -> str:
    """Calls, tokens and cost per model, for scripts to print when they finish."""
    if not calls:
        return "No model calls."
    lines = []
    for model in sorted({base_model(call.model) for call in calls}):
        mine = [call for call in calls if base_model(call.model) == model]
        tokens = sum(call.input_tokens + call.output_tokens for call in mine)
        cost = sum(call.cost_usd or 0.0 for call in mine)
        lines.append(f"{model:<14} {len(mine):>5} calls  {tokens:>10,} tokens  ${cost:.4f}")
    total = sum(call.cost_usd or 0.0 for call in calls)
    lines.append(f"{'Total':<14} {len(calls):>5} calls  {sum(c.input_tokens + c.output_tokens for c in calls):>10,} tokens  ${total:.4f}")
    return "\n".join(lines)
