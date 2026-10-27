from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from agent.usage import ModelCall, UsageTracker


def _result(model: str, *, input_tokens: int, output_tokens: int, cached: int = 0) -> LLMResult:
    message = AIMessage(
        content="",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cached},
        },
        response_metadata={"model_name": model},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_tracker_records_each_call_with_its_graph_step() -> None:
    tracker = UsageTracker()
    first, second = uuid4(), uuid4()
    tracker.on_chat_model_start({}, [], run_id=first, metadata={"langgraph_node": "generate_answer"})
    tracker.on_chat_model_start({}, [], run_id=second, metadata={"langgraph_node": "check_answer"})
    tracker.on_llm_end(_result("gpt-4.1-2025-04-14", input_tokens=2000, output_tokens=100), run_id=second)
    tracker.on_llm_end(_result("gpt-4o-mini-2024-07-18", input_tokens=1500, output_tokens=200), run_id=first)

    assert [(call.model, call.step) for call in tracker.calls] == [
        ("gpt-4.1-2025-04-14", "check_answer"),
        ("gpt-4o-mini-2024-07-18", "generate_answer"),
    ]
    assert tracker.total_tokens == 3800
    # 2000 × $2 + 100 × $8, and 1500 × $0.15 + 200 × $0.60, per million tokens.
    assert round(tracker.total_cost_usd, 6) == round(0.0048 + 0.000345, 6)


def test_calls_outside_the_graph_use_the_trackers_step() -> None:
    tracker = UsageTracker(step="evaluation_judge")
    run_id = uuid4()
    tracker.on_chat_model_start({}, [], run_id=run_id)
    tracker.on_llm_end(_result("gpt-4.1", input_tokens=10, output_tokens=10), run_id=run_id)

    assert tracker.calls[0].step == "evaluation_judge"


def test_cached_input_is_charged_at_the_cached_price_and_unknown_models_have_no_cost() -> None:
    cached = ModelCall(model="gpt-4.1", step=None, input_tokens=1_000_000, cached_input_tokens=600_000, output_tokens=0)
    unknown = ModelCall(model="some-new-model", step=None, input_tokens=100, cached_input_tokens=0, output_tokens=100)

    assert cached.cost_usd == 400_000 * 2.00 / 1e6 + 600_000 * 0.50 / 1e6
    assert unknown.cost_usd is None


def test_a_call_without_usage_is_skipped() -> None:
    tracker = UsageTracker()
    run_id = uuid4()
    tracker.on_chat_model_start({}, [], run_id=run_id)
    tracker.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="hi"))]]), run_id=run_id)

    assert tracker.calls == []
