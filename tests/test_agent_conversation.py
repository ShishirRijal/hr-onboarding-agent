from __future__ import annotations

from types import SimpleNamespace

from agent.conversation import generate_chat_reply, recent_history, route_message


class FakeRouterLLM:
    def __init__(self, decision) -> None:
        self.decision = decision
        self.calls: list[object] = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.schema(**self.decision)


class FakeChatLLM:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=" Hi Shishir! What can I help you with? ")


def test_route_message_returns_chat_without_a_search_query() -> None:
    llm = FakeRouterLLM({"kind": "chat", "search_query": "ignored"})

    assert route_message("hi i'm shishir", llm=llm) == {"kind": "chat", "search_query": ""}


def test_route_message_uses_the_rewritten_question_and_shows_the_conversation() -> None:
    llm = FakeRouterLLM({"kind": "hr", "search_query": "How much annual leave do employees in Finland get?"})
    history = [{"question": "How much leave do I get?", "answer": "28 calendar days."}]

    route = route_message("and in Finland?", history, llm=llm)

    assert route == {"kind": "hr", "search_query": "How much annual leave do employees in Finland get?"}
    prompt = llm.calls[0][1][1]
    assert "Employee: How much leave do I get?" in prompt
    assert "New message: and in Finland?" in prompt


def test_route_message_searches_a_first_question_exactly_as_asked() -> None:
    llm = FakeRouterLLM({"kind": "hr", "search_query": "On which day of the month is salary paid?"})

    assert route_message("When is payday?", llm=llm)["search_query"] == "When is payday?"


def test_route_message_falls_back_to_the_message_when_the_query_is_empty() -> None:
    llm = FakeRouterLLM({"kind": "hr", "search_query": " "})

    assert route_message("When is payday?", llm=llm)["search_query"] == "When is payday?"


def test_chat_reply_sees_the_conversation_and_the_employee() -> None:
    llm = FakeChatLLM()
    history = [{"question": "hi i'm shishir", "answer": "Hi Shishir!"}]

    reply = generate_chat_reply(
        "what's my name?", history=history, employee_context={"office_country": "Remote"}, llm=llm
    )

    assert reply == "Hi Shishir! What can I help you with?"
    messages = llm.calls[0]
    assert "chatting with an employee working remotely" in messages[0][1]
    assert messages[1:] == [("human", "hi i'm shishir"), ("ai", "Hi Shishir!"), ("human", "what's my name?")]


def test_recent_history_keeps_the_last_turns_and_shortens_long_answers() -> None:
    turns = [{"question": f"q{index}", "answer": "a" * 1000} for index in range(6)]

    history = recent_history(turns)

    assert [turn["question"] for turn in history] == ["q2", "q3", "q4", "q5"]
    assert all(len(turn["answer"]) == 600 for turn in history)
