from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from agent.citations import has_citations, strip_citations
from agent.conversation import MESSAGE_CHAT

from .cases import EXPECT_ANSWER, EXPECT_CHAT, EXPECT_NOT_FOUND, EvalCase, EvalTurn
from .judge import Judge

DEFAULT_REPORT_DIR = Path("data/evaluations")
OUTCOME_ERROR = "error"


@dataclass(slots=True)
class TurnResult:
    case_id: str
    case_kind: str
    turn: int
    message: str
    expect: str
    expected_answer: str
    outcome: str
    answer: str
    search_query: str | None
    searched_country: str | None
    cited_sources: list[str]
    # Text of the sections the answer was written from, for the grounding check.
    sections: list[str]
    seconds: float
    # Checks that need no model: None when a check doesn't apply to this turn.
    behaviour_ok: bool = False
    sources_ok: bool | None = None
    country_ok: bool | None = None
    mentions_ok: bool | None = None
    # Whether an answer marks where its facts come from, with [1], [2], ...; not part of passing.
    cites: bool | None = None
    correctness: str | None = None
    correctness_reason: str | None = None
    grounding: str | None = None
    grounding_reason: str | None = None
    unsupported_claims: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        checks = (self.sources_ok, self.country_ok, self.mentions_ok)
        return (
            self.behaviour_ok
            and all(check is not False for check in checks)
            and self.correctness in (None, "correct")
            and self.grounding in (None, "grounded")
        )

    def problems(self) -> list[str]:
        problems: list[str] = []
        if self.error:
            problems.append(f"Error: {self.error}")
        elif not self.behaviour_ok:
            problems.append(f"Expected {_describe(self.expect)}, got {_describe(self.outcome)}.")
        if self.sources_ok is False:
            problems.append(f"Cited {self.cited_sources or 'no sources'}, not the expected document.")
        if self.country_ok is False:
            problems.append(f"Searched {self.searched_country or 'all countries'}, not the expected country.")
        if self.mentions_ok is False:
            problems.append("Reply is missing a word it should mention.")
        if self.correctness and self.correctness != "correct":
            problems.append(f"Answer {self.correctness.replace('_', ' ')}: {self.correctness_reason}")
        if self.grounding and self.grounding != "grounded":
            claims = "; ".join(self.unsupported_claims)
            problems.append(f"Answer {self.grounding.replace('_', ' ')}: {claims or self.grounding_reason}")
        return problems


def run_cases(
    graph: Any,
    cases: Sequence[EvalCase],
    *,
    on_turn: Callable[[TurnResult], None] | None = None,
    retrieval_config: dict[str, Any] | None = None,
    callbacks: list[Any] | None = None,
) -> list[TurnResult]:
    """Plays every case through the agent, one turn at a time, carrying the conversation
    forward the way the API does. `callbacks` go to every run, to count the tokens used."""
    results: list[TurnResult] = []
    for case in cases:
        history: list[dict[str, str]] = []
        for index, turn in enumerate(case.turns, start=1):
            result = _run_turn(
                graph, case, index, turn, history, retrieval_config or {"apply_reranker": False}, callbacks
            )
            results.append(result)
            history.append({"question": turn.message, "answer": result.answer})
            if on_turn:
                on_turn(result)
    return results


def _run_turn(
    graph: Any,
    case: EvalCase,
    index: int,
    turn: EvalTurn,
    history: list[dict[str, str]],
    retrieval_config: dict[str, Any],
    callbacks: list[Any] | None = None,
) -> TurnResult:
    started = time.perf_counter()
    state = {
        "question": turn.message,
        "employee_context": case.employee_context,
        "history": list(history),
        "retrieval_config": dict(retrieval_config),
    }
    try:
        final = graph.invoke(state, config={"callbacks": callbacks} if callbacks else None)
        error = None
    except Exception as exc:  # A failing turn is reported, not fatal to the run.
        final, error = {}, f"{type(exc).__name__}: {exc}"

    response = final.get("final_response", {}) or {}
    route = final.get("message_route", {}) or {}
    if error:
        outcome = OUTCOME_ERROR
    elif route.get("kind") == MESSAGE_CHAT:
        outcome = EXPECT_CHAT
    else:
        outcome = EXPECT_ANSWER if response.get("answered") else EXPECT_NOT_FOUND

    result = TurnResult(
        case_id=case.id,
        case_kind=case.kind,
        turn=index,
        message=turn.message,
        expect=turn.expect,
        expected_answer=turn.answer,
        outcome=outcome,
        answer=str(response.get("text", "")),
        search_query=route.get("search_query") or None,
        searched_country=(final.get("resolved_filters", {}) or {}).get("country"),
        cited_sources=[str(source.get("source_doc", "")) for source in response.get("sources", []) or []],
        sections=[str(chunk.get("text", "")) for chunk in final.get("retrieved_chunks", []) or []],
        seconds=round(time.perf_counter() - started, 2),
        error=error,
    )
    _check(result, turn)
    return result


def _check(result: TurnResult, turn: EvalTurn) -> None:
    result.behaviour_ok = result.outcome == turn.expect
    if turn.expect == EXPECT_ANSWER and result.outcome == EXPECT_ANSWER and turn.sources:
        result.sources_ok = any(source in result.cited_sources for source in turn.sources)
    if turn.country and result.outcome in (EXPECT_ANSWER, EXPECT_NOT_FOUND):
        result.country_ok = result.searched_country == turn.country
    if result.outcome == EXPECT_ANSWER:
        result.cites = has_citations(result.answer)
    if turn.mentions:
        reply = result.answer.lower()
        result.mentions_ok = all(word.lower() in reply for word in turn.mentions)


def judge_results(
    results: Sequence[TurnResult],
    judge: Judge,
    *,
    workers: int = 8,
    histories: dict[tuple[str, int], list[dict[str, str]]] | None = None,
) -> None:
    """Grades answers from the documents: correctness where an expected answer exists, and
    grounding for every answer, including ones that should have gone to HR."""
    histories = histories or _histories(results)

    def grade(result: TurnResult) -> None:
        if result.outcome != EXPECT_ANSWER:
            return
        if result.expect == EXPECT_ANSWER and result.expected_answer:
            verdict = judge.correctness(
                result.message,
                result.expected_answer,
                strip_citations(result.answer),
                histories.get((result.case_id, result.turn), []),
            )
            result.correctness, result.correctness_reason = verdict.verdict, verdict.reason
        verdict = judge.grounding(strip_citations(result.answer), result.sections)
        result.grounding, result.grounding_reason = verdict.verdict, verdict.reason
        result.unsupported_claims = list(verdict.unsupported_claims)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(grade, results))


def _histories(results: Sequence[TurnResult]) -> dict[tuple[str, int], list[dict[str, str]]]:
    histories: dict[tuple[str, int], list[dict[str, str]]] = {}
    running: dict[str, list[dict[str, str]]] = {}
    for result in results:
        earlier = running.setdefault(result.case_id, [])
        histories[(result.case_id, result.turn)] = list(earlier)
        earlier.append({"question": result.message, "answer": strip_citations(result.answer)})
    return histories


def summarize(results: Sequence[TurnResult]) -> dict[str, Any]:
    def rate(values: list[bool]) -> dict[str, Any]:
        return {"passed": sum(values), "total": len(values), "rate": round(sum(values) / len(values), 3) if values else None}

    def counts(values: list[str]) -> dict[str, int]:
        return {value: values.count(value) for value in sorted(set(values))}

    by_expectation = {
        expect: rate([result.behaviour_ok for result in results if result.expect == expect])
        for expect in (EXPECT_ANSWER, EXPECT_NOT_FOUND, EXPECT_CHAT)
    }
    return {
        "turns": len(results),
        "passed": rate([result.passed for result in results]),
        "behaviour": rate([result.behaviour_ok for result in results]),
        "behaviour_by_expectation": by_expectation,
        "correctness": counts([result.correctness for result in results if result.correctness]),
        "grounding": counts([result.grounding for result in results if result.grounding]),
        "sources": rate([result.sources_ok for result in results if result.sources_ok is not None]),
        "country": rate([result.country_ok for result in results if result.country_ok is not None]),
        "mentions": rate([result.mentions_ok for result in results if result.mentions_ok is not None]),
        "cites": rate([result.cites for result in results if result.cites is not None]),
        "errors": sum(result.outcome == OUTCOME_ERROR for result in results),
        "median_seconds": statistics.median(result.seconds for result in results) if results else None,
    }


def save_report(
    results: Sequence[TurnResult],
    summary: dict[str, Any],
    meta: dict[str, Any],
    directory: Path = DEFAULT_REPORT_DIR,
) -> tuple[Path, Path]:
    """Writes the run as JSON (for comparing runs) and Markdown (for reading)."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = directory / f"answers-{stamp}.json"
    markdown_path = directory / f"answers-{stamp}.md"
    json_path.write_text(
        json.dumps({"meta": meta, "summary": summary, "results": [asdict(result) for result in results]}, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(format_markdown(results, summary, meta), encoding="utf-8")
    return json_path, markdown_path


def latest_summary(directory: Path = DEFAULT_REPORT_DIR, *, before: Path | None = None) -> dict[str, Any] | None:
    """The summary of the most recent earlier run, to show what changed."""
    runs = sorted(path for path in directory.glob("answers-*.json") if path != before)
    if not runs:
        return None
    return json.loads(runs[-1].read_text(encoding="utf-8")).get("summary")


def format_summary(summary: dict[str, Any], previous: dict[str, Any] | None = None) -> str:
    def line(label: str, key: str) -> str:
        current = summary[key]
        text = f"{label:<22} {current['passed']}/{current['total']}"
        if previous and previous.get(key) and previous[key].get("total"):
            text += f"   (last run {previous[key]['passed']}/{previous[key]['total']})"
        return text

    by_expectation = summary["behaviour_by_expectation"]
    lines = [
        line("Turns fully passing", "passed"),
        line("Right behaviour", "behaviour"),
        *(
            f"  {name:<20} {by_expectation[key]['passed']}/{by_expectation[key]['total']}"
            for key, name in ((EXPECT_ANSWER, "answered"), (EXPECT_NOT_FOUND, "offered HR"), (EXPECT_CHAT, "chatted"))
            if by_expectation[key]["total"]
        ),
        f"{'Correctness':<22} {_format_counts(summary['correctness'])}",
        f"{'Grounding':<22} {_format_counts(summary['grounding'])}",
        line("Cited right document", "sources"),
        line("Searched right country", "country"),
    ]
    if summary.get("cites", {}).get("total"):
        lines.append(line("Answers with citations", "cites"))
    if summary["mentions"]["total"]:
        lines.append(line("Mentions", "mentions"))
    if summary["errors"]:
        lines.append(f"{'Errors':<22} {summary['errors']}")
    lines.append(f"{'Median time per turn':<22} {summary['median_seconds']}s")
    return "\n".join(lines)


def format_markdown(results: Sequence[TurnResult], summary: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        "# Answer evaluation",
        "",
        f"Run {meta.get('started_at', '')} · answer model {meta.get('answer_model', '?')} · "
        f"judge {meta.get('judge_model') or 'off'} · cases {meta.get('cases', '?')}",
        "",
        "```",
        format_summary(summary),
        "```",
        "",
    ]
    failures = [result for result in results if not result.passed]
    lines.append(f"## Failures ({len(failures)})" if failures else "## Failures\n\nNone.")
    for result in failures:
        lines += [
            "",
            f"### {result.case_id} · turn {result.turn}",
            "",
            f"**Asked:** {result.message}",
            "",
            *(f"- {problem}" for problem in result.problems()),
        ]
        if result.search_query and result.search_query != result.message:
            lines.append(f"- Searched as: {result.search_query}")
        if result.expected_answer:
            lines += ["", f"**Expected:** {result.expected_answer}"]
        lines += ["", f"**Got:** {result.answer}"]
    return "\n".join(lines) + "\n"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "not graded"
    return ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in counts.items())


def _describe(outcome: str) -> str:
    return {
        EXPECT_ANSWER: "an answer",
        EXPECT_NOT_FOUND: "an offer to ask HR",
        EXPECT_CHAT: "a chat reply",
        OUTCOME_ERROR: "an error",
    }.get(outcome, outcome)
