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
