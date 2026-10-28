from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from evaluation.cases import EvalCase, EvalTurn, load_conversation_cases, load_faq_cases
from evaluation.runner import format_markdown, judge_results, latest_summary, run_cases, save_report, summarize

FAQ_CSV = """question,ground_truth_answer,source_doc,category,country
How much leave in Finland?,25 working days.,leave_policy,Leave,Finland
Can I bring my dog?,,NONE,Escalation,All
"""


class FakeGraph:
    """Answers from a script keyed by message, and records the state it was given."""

    def __init__(self, replies):
        self.replies = replies
        self.states = []

    def invoke(self, state, config=None):
        self.states.append(state)
        reply = self.replies[state["question"]]
        if isinstance(reply, Exception):
            raise reply
        return reply


def _answer(text, sources=("leave_policy",), country="Estonia"):
    return {
        "message_route": {"kind": "hr", "search_query": "rewritten"},
        "resolved_filters": {"country": country},
        "retrieved_chunks": [{"text": "Employees in Estonia get 28 calendar days."}],
        "final_response": {"text": text, "answered": True, "sources": [{"source_doc": s} for s in sources]},
    }


def _chat(text):
    return {"message_route": {"kind": "chat", "search_query": ""}, "final_response": {"text": text, "answered": True}}


def _not_found(country="Estonia"):
    return {
        "message_route": {"kind": "hr", "search_query": "q"},
        "resolved_filters": {"country": country},
        "final_response": {"text": "Not covered. Ask HR?", "answered": False, "sources": []},
    }


class FakeJudge:
    def __init__(self, correctness="correct", grounding="grounded"):
        self.correctness_calls = []
        self.correctness_verdict = correctness
        self.grounding_verdict = grounding

    def correctness(self, question, expected, answer, history=()):
        self.correctness_calls.append({"question": question, "history": list(history)})
        return SimpleNamespace(verdict=self.correctness_verdict, reason="Says 30 days, expected 28.")

    def grounding(self, answer, sections):
        return SimpleNamespace(verdict=self.grounding_verdict, reason="ok", unsupported_claims=[])


def test_faq_rows_become_single_question_cases(tmp_path: Path) -> None:
    path = tmp_path / "faq.csv"
    path.write_text(FAQ_CSV, encoding="utf-8")

    answerable, unanswerable = load_faq_cases(path)

    assert answerable.office == "tampere"
    assert answerable.turns[0].expect == "answer"
    assert answerable.turns[0].sources == ("leave_policy",)
    assert answerable.turns[0].country == "Finland"
    assert unanswerable.office == "tallinn"
    assert unanswerable.turns[0].expect == "not_found"
    assert unanswerable.turns[0].country is None


def test_the_shipped_conversations_load() -> None:
    cases = load_conversation_cases()

    assert cases
    assert all(turn.expect in {"answer", "not_found", "chat"} for case in cases for turn in case.turns)


def test_conversations_carry_what_was_cited_and_the_chats_summary_forward() -> None:
    first = _answer("28 days [1].")
    first["final_response"]["sources"] = [{"source_doc": "leave_policy", "chunk_id": "c1"}]
    first["memory"] = {"summary": "- Asked about leave.", "turns_covered": 1}
    graph = FakeGraph({"hi": _chat("Hi!"), "leave?": first, "and carry-over?": _answer("5 days [1].")})
    turns = [EvalTurn("hi", "chat"), EvalTurn("leave?", "answer"), EvalTurn("and carry-over?", "answer")]

    run_cases(graph, [EvalCase(id="memory", office="tallinn", turns=turns)])

    assert "memory" not in graph.states[1]
    assert graph.states[2]["memory"] == {"summary": "- Asked about leave.", "turns_covered": 1}
    assert [(turn["kind"], turn["sources"]) for turn in graph.states[2]["history"]] == [("chat", []), ("hr", ["c1"])]


def test_conversations_carry_history_forward_and_checks_run() -> None:
    graph = FakeGraph(
        {
            "how much vacation?": _answer("You get 28 calendar days."),
            "and in Finland?": _answer("Finland gets 25 working days.", country="Estonia"),
        }
    )
    case = EvalCase(
        id="leave",
        office="tallinn",
        turns=[
            EvalTurn("how much vacation?", "answer", "28 calendar days.", ("leave_policy",), "Estonia"),
            EvalTurn("and in Finland?", "answer", "25 working days.", ("leave_policy",), "Finland"),
        ],
    )

    first, second = run_cases(graph, [case])

    assert graph.states[1]["history"] == [
        {"question": "how much vacation?", "answer": "You get 28 calendar days.", "kind": "hr", "sources": []}
    ]
    assert graph.states[0]["employee_context"]["office_location"] == "Tallinn"
    assert first.behaviour_ok and first.sources_ok and first.country_ok
    assert second.country_ok is False
    assert "Searched Estonia, not the expected country." in second.problems()


def test_wrong_behaviour_and_errors_are_reported_not_raised() -> None:
    graph = FakeGraph({"hi": _not_found(), "dog?": _answer("Dogs are welcome."), "boom": RuntimeError("down")})
    case = EvalCase(
        id="mixed",
        office="tallinn",
        turns=[EvalTurn("hi", "chat"), EvalTurn("dog?", "not_found"), EvalTurn("boom", "answer", "x")],
    )

    greeting, dog, broken = run_cases(graph, [case])

    assert greeting.problems() == ["Expected a chat reply, got an offer to ask HR."]
    assert dog.problems() == ["Expected an offer to ask HR, got an answer."]
    assert broken.outcome == "error"
    assert broken.problems()[0] == "Error: RuntimeError: down"


def test_judge_grades_answers_with_their_conversation() -> None:
    graph = FakeGraph({"q1": _chat("Hi!"), "q2": _answer("30 days."), "dog?": _answer("Dogs are fine.")})
    case = EvalCase(
        id="judged",
        office="tallinn",
        turns=[EvalTurn("q1", "chat"), EvalTurn("q2", "answer", "28 days."), EvalTurn("dog?", "not_found")],
    )
    results = run_cases(graph, [case])
    judge = FakeJudge(correctness="incorrect", grounding="grounded")

    judge_results(results, judge, workers=2)

    chat, answer, wrongly_answered = results
    assert chat.correctness is None and chat.grounding is None
    assert answer.correctness == "incorrect"
    assert judge.correctness_calls[0]["history"] == [{"question": "q1", "answer": "Hi!"}]
    # Answers that should have gone to HR are still checked against their sources.
    assert wrongly_answered.correctness is None
    assert wrongly_answered.grounding == "grounded"
    assert not answer.passed


def test_summary_report_and_comparison_with_the_last_run(tmp_path: Path) -> None:
    graph = FakeGraph({"q": _answer("28 days."), "hi": _chat("Hello!")})
    case = EvalCase(id="c", office="tallinn", turns=[EvalTurn("q", "answer", "28 days.", ("it_guide",)), EvalTurn("hi", "chat")])
    results = run_cases(graph, [case])

    summary = summarize(results)
    assert summary["behaviour"] == {"passed": 2, "total": 2, "rate": 1.0}
    assert summary["sources"] == {"passed": 0, "total": 1, "rate": 0.0}
    assert summary["passed"]["passed"] == 1

    first_json, _ = save_report(results, summary, {"cases": "test"}, tmp_path)
    second_json, markdown_path = save_report(results, summary, {"cases": "test"}, tmp_path / "later")
    assert json.loads(first_json.read_text())["summary"]["turns"] == 2
    assert latest_summary(tmp_path, before=None)["turns"] == 2
    markdown = markdown_path.read_text()
    assert "## Failures (1)" in markdown
    assert "Cited ['leave_policy'], not the expected document." in markdown
    assert "## Failures" in format_markdown([results[1]], summarize([results[1]]), {})
