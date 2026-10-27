from __future__ import annotations

from typing import Any, Literal, Sequence

from pydantic import BaseModel

from agent.answering import _load_default_llm
from agent.state import ConversationTurn

# A stronger model than the one answering, and a different one, so it doesn't grade its own style.
DEFAULT_JUDGE_MODEL = "gpt-4.1"

CORRECTNESS_PROMPT = """You grade answers from a company's HR assistant against the answer HR expects.

- correct: the answer states the key facts of the expected answer and nothing that contradicts it. Wording can differ, and extra accurate detail is fine.
- partially_correct: some key facts are right, but one is missing, vague, or hedged.
- incorrect: a key fact is wrong or contradicts the expected answer, or the question isn't answered.

The reason is one short sentence naming the fact that is missing or wrong, or "Matches the expected answer." """

GROUNDING_PROMPT = """You check whether an HR assistant's answer is backed by the document sections it was given.

Look at each factual claim in the answer: numbers, rules, names, steps, deadlines. Ignore greetings, offers to help, and statements that something isn't covered.

- grounded: every factual claim is supported by the sections.
- partly_grounded: the main claim is supported, but at least one other claim isn't.
- not_grounded: the main claim isn't supported by the sections.

List each unsupported claim briefly. The reason is one short sentence."""


class CorrectnessVerdict(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect"]
    reason: str


class GroundingVerdict(BaseModel):
    verdict: Literal["grounded", "partly_grounded", "not_grounded"]
    unsupported_claims: list[str]
    reason: str


class Judge:
    def __init__(
        self, *, llm: Any | None = None, model: str = DEFAULT_JUDGE_MODEL, callbacks: list[Any] | None = None
    ) -> None:
        self.model = model
        client = llm or _load_default_llm(model=model)
        # Callbacks count the judge's tokens, which cost as much as the answers they grade.
        config = {"callbacks": callbacks} if callbacks else {}
        self._correctness = client.with_structured_output(CorrectnessVerdict).with_config(config)
        self._grounding = client.with_structured_output(GroundingVerdict).with_config(config)

    def correctness(
        self,
        question: str,
        expected: str,
        answer: str,
        history: Sequence[ConversationTurn] = (),
    ) -> CorrectnessVerdict:
        parts = []
        if history:
            conversation = "\n".join(f"Employee: {turn['question']}\nAssistant: {turn['answer']}" for turn in history)
            parts.append(f"Conversation so far:\n{conversation}")
        parts += [f"Question:\n{question}", f"Expected answer:\n{expected}", f"Assistant's answer:\n{answer}"]
        return self._correctness.invoke([("system", CORRECTNESS_PROMPT), ("human", "\n\n".join(parts))])

    def grounding(self, answer: str, sections: Sequence[str]) -> GroundingVerdict:
        numbered = "\n\n".join(f"[{index}] {text}" for index, text in enumerate(sections, start=1))
        prompt = f"Document sections:\n{numbered or '(none)'}\n\nAssistant's answer:\n{answer}"
        return self._grounding.invoke([("system", GROUNDING_PROMPT), ("human", prompt)])
