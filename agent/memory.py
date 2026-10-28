from __future__ import annotations

from typing import Any, Sequence

from .answering import DEFAULT_ANSWER_MODEL, _load_default_llm
from .citations import strip_citations
from .state import ChatMemory, ConversationTurn

KIND_CHAT = "chat"
# The latest turns are given to the models in full. Once more than MAX_RECENT_TURNS
# questions (small talk not counted) or MAX_RECENT_CHARS of text haven't been summarised,
# all but the last RECENT_TURNS are folded into the chat's summary. So the summary is
# rewritten every few turns, not on every message.
RECENT_TURNS = 4
MAX_RECENT_TURNS = 8
MAX_RECENT_CHARS = 10_000
# A very long answer is cut before it's given to the models; most answers are far shorter.
MAX_ANSWER_CHARS = 2_500
# Sections a follow-up reads again from the answer before it ("and what about step 3?").
MAX_CARRIED_SOURCES = 3

EMPTY_MEMORY: ChatMemory = {"summary": "", "turns_covered": 0}

SUMMARY_PROMPT = """You keep the memory of a chat between an employee and NordTech Solutions' HR onboarding assistant, so the assistant can follow up on anything said earlier. You get the summary so far, which may be empty, and the next turns of the chat. Write the updated summary.

Keep:
- what the employee said about themselves and their situation: plans, dates, family, team, and which country or office they asked about
- each question they asked and the key facts of the answer: numbers, rules, deadlines, approvers and contacts, in a few words each
- questions the assistant couldn't answer, and whether the employee asked for them to go to HR

Leave out greetings, thanks and other small talk. Never add anything that wasn't said in the chat.
Write short bullet points, oldest first, at most 150 words in all."""


def split_history(
    turns: Sequence[ConversationTurn],
    memory: ChatMemory | None = None,
) -> tuple[list[ConversationTurn], list[ConversationTurn]]:
    """The turns to fold into the summary now (often none), and the turns to keep in full."""
    covered = min(max((memory or EMPTY_MEMORY)["turns_covered"], 0), len(turns))
    unsummarised = [shorten(turn) for turn in turns[covered:]]
    questions = sum(1 for turn in unsummarised if turn.get("kind") != KIND_CHAT)
    size = sum(len(turn["question"]) + len(turn["answer"]) for turn in unsummarised)
    if questions <= MAX_RECENT_TURNS and size <= MAX_RECENT_CHARS:
        return [], unsummarised
    return unsummarised[:-RECENT_TURNS], unsummarised[-RECENT_TURNS:]


def shorten(turn: ConversationTurn) -> ConversationTurn:
    """A turn as the models see it: the answer without its citation numbers, which point to
    another search's passages, and cut if it's very long."""
    return {**turn, "answer": strip_citations(turn["answer"])[:MAX_ANSWER_CHARS]}


def carried_sources(history: Sequence[ConversationTurn]) -> list[str]:
    """The sections the latest answer cited, for a follow-up to read again."""
    for turn in reversed(history):
        if turn.get("kind") == KIND_CHAT:
            continue
        return list(dict.fromkeys(turn.get("sources") or []))[:MAX_CARRIED_SOURCES]
    return []


def summarise_conversation(
    summary: str,
    turns: Sequence[ConversationTurn],
    *,
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    """The chat's summary with these turns folded in."""
    client = llm or _load_default_llm(model=model)
    conversation = "\n".join(f"Employee: {turn['question']}\nAssistant: {turn['answer']}" for turn in turns)
    response = client.invoke(
        [
            ("system", SUMMARY_PROMPT),
            ("human", f"Summary so far:\n{summary or '(empty)'}\n\nNext turns:\n{conversation}"),
        ]
    )
    return str(getattr(response, "content", response)).strip()

