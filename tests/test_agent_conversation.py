from __future__ import annotations

from types import SimpleNamespace

from agent.conversation import generate_chat_reply, route_message


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

    assert route_message("hi i'm shishir", llm=llm) == {"kind": "chat", "search_query": "", "follows_up": False}


def test_route_message_uses_the_rewritten_question_and_shows_the_conversation() -> None:
    llm = FakeRouterLLM({"kind": "hr", "search_query": "How much annual leave do employees in Finland get?"})
    history = [{"question": "How much leave do I get?", "answer": "28 calendar days."}]

    route = route_message("and in Finland?", history, llm=llm)

    assert route == {
        "kind": "hr",
        "search_query": "How much annual leave do employees in Finland get?",
        "follows_up": False,
    }
    prompt = llm.calls[0][1][1]
    assert "Employee: How much leave do I get?" in prompt
    assert "New message: and in Finland?" in prompt


def test_route_message_marks_follow_ups_and_shows_the_chats_summary() -> None:
    llm = FakeRouterLLM({"kind": "hr", "search_query": "What is step 3 of claiming expenses?", "follows_up": True})
    history = [{"question": "How do I claim expenses?", "answer": "Three steps."}]

    route = route_message("what was step 3?", history, summary="- Joined in October.", llm=llm)

    assert route["follows_up"] is True
    assert "Summary of earlier in this chat:\n- Joined in October." in llm.calls[0][1][1]
    # A first message has nothing to follow up on.
    assert route_message("what was step 3?", llm=llm)["follows_up"] is False


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

