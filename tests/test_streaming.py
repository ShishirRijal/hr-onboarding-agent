from __future__ import annotations

from types import SimpleNamespace

from api.streaming import stream_agent


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


class FakeCheckedAnswerGraph:
    def stream(self, state, stream_mode):
        yield "updates", {"score_confidence": {"confidence_label": "medium"}}
        yield "updates", {"read_neighbours": {"retrieved_chunks": [{}, {}]}}
        # A draft is never streamed: only checked answers reach the employee.
        yield "messages", (SimpleNamespace(content="Draft text"), {"langgraph_node": "generate_answer"})
        yield "updates", {"generate_answer": {"answer_declined": False}}
        check = {"answers_question": True, "unsupported_claims": [], "missing_details": ["Finance approves over €300"]}
        yield "updates", {"check_answer": {"answer_check": check}}
        yield "updates", {"revise_answer": {"answer_check": {**check, "revised": True}}}
        yield "updates", {"respond_to_user": {"final_response": {"text": "Your manager and Finance.", "answered": True}}}


def test_stream_agent_reports_the_answer_check_and_never_streams_drafts() -> None:
    events = list(stream_agent(FakeCheckedAnswerGraph(), {"question": "Who approves this?"}))

    assert [payload["stage"] for event, payload in events if event == "status"] == ["writing", "verifying", "revising"]
    assert not [event for event, _ in events if event == "token"]
    assert events[-1][1]["final_response"]["text"] == "Your manager and Finance."


class FakeCorrectedSearchGraph:
    def __init__(self, found: bool) -> None:
        self.found = found

    def stream(self, state, stream_mode):
        yield "updates", {"score_confidence": {"confidence_label": "medium"}}
        yield "updates", {"read_neighbours": {"retrieved_chunks": [{}, {}]}}
        yield "updates", {"grade_documents": {"document_grade": {"coverage": "partial"}}}
        if self.found:
            yield "updates", {"search_again": {"retrieved_chunks": [{}], "document_grade": {"coverage": "complete"}}}
        else:
            yield "updates", {"search_again": {"confidence_debug": {"no_relevant_sections": True}}}


def test_stream_agent_reports_the_second_search() -> None:
    state = {"retrieval_config": {"corrective_search": True}}
    found = [payload for event, payload in stream_agent(FakeCorrectedSearchGraph(True), state) if event == "status"]
    missing = [payload for event, payload in stream_agent(FakeCorrectedSearchGraph(False), state) if event == "status"]

    assert [status["stage"] for status in found] == ["grading", "searching_again", "writing"]
    assert found[-1]["label"] == "Writing an answer from 1 section"
    assert [status["stage"] for status in missing] == ["grading", "searching_again", "not_found"]
