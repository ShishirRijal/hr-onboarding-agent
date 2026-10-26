from __future__ import annotations

from types import SimpleNamespace

from agent.answering import generate_grounded_answer, is_insufficient_answer


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content="Employees in Estonia receive 28 calendar days of annual leave.")


def test_generate_grounded_answer_invokes_llm_with_source_context() -> None:
    llm = FakeLLM()
    chunks = [
        {
            "chunk_id": "chunk-1",
            "text": "Annual leave in Estonia is 28 calendar days.",
            "metadata": {
                "source_doc": "leave_policy",
                "source_file": "leave_absence_policy.md",
                "section_path": "Leave Policy > Estonia > Annual Leave",
            },
            "score": 0.91,
        }
    ]

    answer = generate_grounded_answer("How much annual leave do I get?", chunks, llm=llm)

    assert answer == "Employees in Estonia receive 28 calendar days of annual leave."
    assert llm.calls
    messages = llm.calls[0]
    assert messages[0][0] == "system"
    assert "Answer only from the provided HR knowledge base excerpts" in messages[0][1]
    assert messages[1][0] == "human"
    assert "How much annual leave do I get?" in messages[1][1]
    assert "leave_absence_policy.md" in messages[1][1]
    assert "Annual leave in Estonia is 28 calendar days." in messages[1][1]


def test_generate_grounded_answer_returns_fallback_without_chunks() -> None:
    answer = generate_grounded_answer("Can I work abroad for six months?", [], llm=FakeLLM())

    assert "could not find enough information" in answer


def test_is_insufficient_answer_detects_marker() -> None:
    assert is_insufficient_answer("INSUFFICIENT_CONTEXT")
    assert is_insufficient_answer("INSUFFICIENT_CONTEXT.")
    assert not is_insufficient_answer("Employees in Estonia get 28 calendar days.")
