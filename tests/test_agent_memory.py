from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent import build_retrieval_graph
from agent.answering import conversation_text, generate_grounded_answer
from agent.memory import (
    MAX_ANSWER_CHARS,
    MAX_CARRIED_SOURCES,
    MAX_RECENT_TURNS,
    RECENT_TURNS,
    carried_sources,
    split_history,
    summarise_conversation,
)
from interactions import InteractionStore
from retrieval import RetrievalEngine, RetrievedChunk
from tests.test_agent_retrieval_graph import FakeRetriever, FakeStateGraph, approve_answer, keep_every_section


def _turns(count: int, *, kind: str = "hr") -> list[dict[str, object]]:
    return [{"question": f"q{index}", "answer": f"a{index}", "kind": kind, "sources": []} for index in range(count)]


def test_a_short_chat_is_kept_in_full_without_citation_numbers() -> None:
    turns = [{"question": "Leave?", "answer": "You get 28 days [1]. Ask your lead first[2]."}]

    to_fold, recent = split_history(turns)

    assert to_fold == []
    assert recent == [{"question": "Leave?", "answer": "You get 28 days. Ask your lead first."}]


def test_very_long_answers_are_cut() -> None:
    _, recent = split_history([{"question": "Steps?", "answer": "a" * (MAX_ANSWER_CHARS + 500)}])

    assert len(recent[0]["answer"]) == MAX_ANSWER_CHARS


def test_older_turns_are_folded_once_the_chat_is_long() -> None:
    turns = _turns(MAX_RECENT_TURNS + 1)

    to_fold, recent = split_history(turns)

    assert [turn["question"] for turn in to_fold] == [f"q{index}" for index in range(MAX_RECENT_TURNS + 1 - RECENT_TURNS)]
    assert [turn["question"] for turn in recent] == [f"q{index}" for index in range(5, 9)]


def test_small_talk_doesnt_fill_the_memory() -> None:
    turns = _turns(MAX_RECENT_TURNS) + _turns(3, kind="chat")

    to_fold, recent = split_history(turns)

    assert to_fold == []
    assert len(recent) == MAX_RECENT_TURNS + 3


def test_turns_already_in_the_summary_are_left_out() -> None:
    turns = _turns(9)

    to_fold, recent = split_history(turns, {"summary": "Asked about leave.", "turns_covered": 5})

    assert to_fold == []
    assert [turn["question"] for turn in recent] == ["q5", "q6", "q7", "q8"]


def test_a_lot_of_text_is_folded_even_in_a_few_turns() -> None:
    turns = [{"question": f"q{index}", "answer": "a" * 2_400, "kind": "hr"} for index in range(5)]

    to_fold, recent = split_history(turns)

    assert [turn["question"] for turn in to_fold] == ["q0"]
    assert len(recent) == RECENT_TURNS


def test_follow_ups_read_the_sections_the_last_answer_cited() -> None:
    history = [
        {"question": "Leave?", "answer": "28 days.", "kind": "hr", "sources": ["c1", "c2", "c1", "c3", "c4"]},
        {"question": "thanks!", "answer": "You're welcome!", "kind": "chat", "sources": []},
    ]

    assert carried_sources(history) == ["c1", "c2", "c3"][:MAX_CARRIED_SOURCES]
    assert carried_sources(history[:1] + [{"question": "Dog?", "answer": "Not covered.", "kind": "hr"}]) == []
    assert carried_sources([]) == []


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=f" {self.content} ")


def test_the_summary_is_rewritten_with_the_new_turns() -> None:
    llm = FakeLLM("- Going part-time (60%) from January.")

    summary = summarise_conversation(
        "- Asked about annual leave: 28 days.",
        [{"question": "I'm going part-time from January", "answer": "Noted."}],
        llm=llm,
    )

    assert summary == "- Going part-time (60%) from January."
    human = llm.calls[0][1][1]
    assert "- Asked about annual leave: 28 days." in human
    assert "Employee: I'm going part-time from January\nAssistant: Noted." in human


def test_the_answer_model_sees_the_summary_before_the_latest_turns_and_doesnt_greet() -> None:
    llm = FakeLLM("Yes [1].")
    chunk = {"chunk_id": "c1", "text": "Parental leave is 160 days.", "metadata": {"source_doc": "leave_policy"}}

    generate_grounded_answer(
        "how long is it?",
        [chunk],
        history=[{"question": "and parental leave?", "answer": "Up to 160 days."}],
        summary="- Partner is due in March.",
        employee_context={"employee_name": "Kertu Vaher"},
        llm=llm,
    )

    messages = llm.calls[0]
    assert messages[1] == ("system", "Summary of earlier in this chat:\n- Partner is due in March.")
    assert messages[2:4] == [("human", "and parental leave?"), ("ai", "Up to 160 days.")]
    assert "Hi Kertu" not in messages[-1][1]


def test_conversation_text_puts_the_summary_first() -> None:
    history = [{"question": "q", "answer": "a"}]

    assert conversation_text(history) == "Conversation so far:\nEmployee: q\nAssistant: a"
    assert conversation_text(history, "- s") == "Summary of earlier in this chat:\n- s\n\nLatest turns:\nEmployee: q\nAssistant: a"
    assert conversation_text([]) == ""


def _index(*chunks: tuple[str, str]) -> SimpleNamespace:
    return SimpleNamespace(
        chunk_ids=[chunk_id for chunk_id, _ in chunks],
        chunks=[SimpleNamespace(text=text, metadata={"source_doc": "leave_policy"}) for _, text in chunks],
    )


def _graph(*, router, summariser=None, answer_calls=None, index=None, retriever=None):
    def answer_generator(question, chunks, **context):
        if answer_calls is not None:
            answer_calls.append({"question": question, "chunks": chunks, **context})
        return f"{chunks[0]['text']} [1]"

    engine = RetrievalEngine(
        client=SimpleNamespace(),
        collection_name="nordtech_hr",
        embedding_model=SimpleNamespace(),
        bm25_index=index or SimpleNamespace(),
    )
    return build_retrieval_graph(
        engine,
        retriever=retriever or FakeRetriever(),
        answer_generator=answer_generator,
        message_router=router,
        conversation_summariser=summariser or (lambda summary, turns: "unused"),
        answer_checker=approve_answer,
        document_grader=keep_every_section,
        context_expander=lambda index, chunks: list(chunks),
        state_graph_cls=FakeStateGraph,
        start_token="__start__",
        end_token="__end__",
    )


def test_a_long_chat_is_summarised_and_every_model_gets_the_summary() -> None:
    folded: list[tuple[str, list[dict[str, object]]]] = []
    routes: list[dict[str, object]] = []
    answer_calls: list[dict[str, object]] = []

    def router(question, history, **context):
        routes.append({"history": history, **context})
        return {"kind": "hr", "search_query": question}

    graph = _graph(
        router=router,
        summariser=lambda summary, turns: folded.append((summary, turns)) or "- Asked q0 to q4.",
        answer_calls=answer_calls,
    )

    result = graph.invoke({"question": "q9", "history": _turns(9), "employee_context": {}})

    assert graph.visited[0] == "remember_conversation"
    assert [turn["question"] for turn in folded[0][1]] == ["q0", "q1", "q2", "q3", "q4"]
    assert folded[0][0] == ""
    assert result["memory"] == {"summary": "- Asked q0 to q4.", "turns_covered": 5}
    assert routes[0]["summary"] == "- Asked q0 to q4."
    assert [turn["question"] for turn in routes[0]["history"]] == ["q5", "q6", "q7", "q8"]
    assert answer_calls[0]["summary"] == "- Asked q0 to q4."


def test_a_short_chat_isnt_summarised() -> None:
    summarised: list[object] = []
    graph = _graph(
        router=lambda question, history, **_: {"kind": "hr", "search_query": question},
        summariser=lambda summary, turns: summarised.append(turns) or "x",
    )

    result = graph.invoke(
        {"question": "q3", "history": _turns(3), "memory": {"summary": "- s", "turns_covered": 0}, "employee_context": {}}
    )

    assert summarised == []
    assert result["memory"] == {"summary": "- s", "turns_covered": 0}


def _leave_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="new",
        text="Sick leave in Finland is paid from day 2.",
        metadata={"source_doc": "leave_policy"},
        score=0.9,
        source="reranked",
        scores={"dense": 0.9, "rerank": 0.9},
    )


def test_a_follow_up_also_reads_what_the_last_answer_cited() -> None:
    index = _index(("earlier", "Step 3: send the form to Finance."), ("other", "Unrelated."))
    answer_calls: list[dict[str, object]] = []
    graph = _graph(
        router=lambda question, history, **_: {"kind": "hr", "search_query": question, "follows_up": True},
        answer_calls=answer_calls,
        index=index,
        retriever=FakeRetriever([_leave_chunk()]),
    )
    history = [{"question": "How do I claim?", "answer": "Three steps [1].", "kind": "hr", "sources": ["earlier", "gone"]}]

    graph.invoke({"question": "what was step 3?", "history": history, "employee_context": {}})

    chunks = answer_calls[0]["chunks"]
    assert [chunk["chunk_id"] for chunk in chunks] == ["new", "earlier"]
    assert chunks[1]["text"] == "Step 3: send the form to Finance."
    assert chunks[1]["source"] == "earlier_answer"


def test_a_new_topic_doesnt_read_the_last_answers_sections() -> None:
    answer_calls: list[dict[str, object]] = []
    graph = _graph(
        router=lambda question, history, **_: {"kind": "hr", "search_query": question, "follows_up": False},
        answer_calls=answer_calls,
        index=_index(("earlier", "Step 3.")),
        retriever=FakeRetriever([_leave_chunk()]),
    )
    history = [{"question": "How do I claim?", "answer": "Three steps.", "kind": "hr", "sources": ["earlier"]}]

    graph.invoke({"question": "who is the CTO?", "history": history, "employee_context": {}})

    assert [chunk["chunk_id"] for chunk in answer_calls[0]["chunks"]] == ["new"]


def test_the_chats_latest_summary_is_saved_with_the_question(tmp_path: Path) -> None:
    store = InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")
    base = {"question": "q", "employee_context": {}, "final_response": {"text": "a", "sources": [], "answered": True}}

    store.log({**base, "session_id": "s-1"})
    assert store.chat_memory("s-1") is None

    store.log({**base, "session_id": "s-1", "memory": {"summary": "- first", "turns_covered": 5}})
    store.log({**base, "session_id": "s-1", "memory": {"summary": "- second", "turns_covered": 9}})
    store.log({**base, "session_id": "s-2", "memory": {"summary": "", "turns_covered": 0}})

    assert store.chat_memory("s-1") == {"summary": "- second", "turns_covered": 9}
    assert store.chat_memory("s-2") is None
