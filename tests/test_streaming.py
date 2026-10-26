from __future__ import annotations

from types import SimpleNamespace

from api.streaming import MarkerGate, stream_agent


def test_marker_gate_releases_normal_text_once_it_cannot_be_the_marker() -> None:
    gate = MarkerGate()

    assert gate.feed("I") == ""
    assert gate.feed("n Estonia") == "In Estonia"
    assert gate.feed(" you get") == " you get"


def test_marker_gate_never_releases_the_marker() -> None:
    gate = MarkerGate()

    released = "".join(gate.feed(token) for token in ("INS", "UFFICIENT", "_CONTEXT", "."))

    assert released == ""


class FakeStreamingGraph:
    def stream(self, state, stream_mode):
        assert stream_mode == ["updates", "messages"]
        yield "updates", {"resolve_filters": {"resolved_filters": {}}}
        yield "updates", {"retrieve_documents": {"retrieved_chunks": []}}
        yield "messages", (SimpleNamespace(content="ignored"), {"langgraph_node": "some_other_node"})
        yield "updates", {"score_confidence": {"confidence_label": "low"}}
        yield "updates", {"answer_not_found": {"final_response": {"text": "Ask HR?", "answered": False}}}


def test_stream_agent_reports_statuses_and_merges_the_final_state() -> None:
    events = list(stream_agent(FakeStreamingGraph(), {"question": "Can I bring my dog?"}))

    statuses = [payload for event, payload in events if event == "status"]
    assert statuses == [
        {"stage": "searching", "label": "Searching HR documents"},
        {"stage": "reading", "label": "No matching sections found", "documents": []},
        {"stage": "not_found", "label": "Couldn't find this in the HR documents"},
    ]
    assert not [event for event, _ in events if event == "token"]
    event, final = events[-1]
    assert event == "done"
    assert final["question"] == "Can I bring my dog?"
    assert final["final_response"]["answered"] is False


class FakeChatGraph:
    def stream(self, state, stream_mode):
        yield "messages", (SimpleNamespace(content='{"kind": "chat"}'), {"langgraph_node": "understand_message"})
        yield "updates", {"understand_message": {"message_route": {"kind": "chat", "search_query": ""}}}
        yield "messages", (SimpleNamespace(content="Hi "), {"langgraph_node": "reply_in_chat"})
        yield "messages", (SimpleNamespace(content="Shishir!"), {"langgraph_node": "reply_in_chat"})
        yield "updates", {"reply_in_chat": {"final_response": {"text": "Hi Shishir!", "answered": True}}}


def test_stream_agent_streams_chat_replies_but_not_routing() -> None:
    events = list(stream_agent(FakeChatGraph(), {"question": "hi i'm shishir"}))

    assert [payload["text"] for event, payload in events if event == "token"] == ["Hi ", "Shishir!"]
    assert not [event for event, _ in events if event == "status"]
    assert events[-1][1]["final_response"]["text"] == "Hi Shishir!"
