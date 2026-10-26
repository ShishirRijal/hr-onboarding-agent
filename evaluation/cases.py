from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

EXPECT_ANSWER = "answer"
EXPECT_NOT_FOUND = "not_found"
EXPECT_CHAT = "chat"
EXPECTATIONS = (EXPECT_ANSWER, EXPECT_NOT_FOUND, EXPECT_CHAT)

DEFAULT_FAQ_PATH = Path("corpus/hr_faq_log.csv")
DEFAULT_CONVERSATIONS_PATH = Path(__file__).with_name("conversations.yaml")

# The offices an employee can pick in the web app, with the context the app sends.
OFFICES: dict[str, dict[str, str]] = {
    "tallinn": {"employee_country": "Estonia", "office_country": "Estonia", "office_location": "Tallinn"},
    "tampere": {"employee_country": "Finland", "office_country": "Finland", "office_location": "Tampere"},
    "porto": {"employee_country": "Portugal", "office_country": "Portugal", "office_location": "Porto"},
    "remote": {"office_country": "Remote"},
}
COUNTRY_OFFICES = {"Estonia": "tallinn", "Finland": "tampere", "Portugal": "porto"}
# FAQ rows that apply everywhere are asked from the app's default office.
DEFAULT_OFFICE = "tallinn"


@dataclass(slots=True)
class EvalTurn:
    message: str
    expect: str
    # What a correct answer says, for the judge; empty when there is nothing to grade.
    answer: str = ""
    # Any one of these documents among the cited sources counts as a correct citation.
    sources: tuple[str, ...] = ()
    # The country the search should be filtered to.
    country: str | None = None
    # Words the reply must contain, checked without the judge.
    mentions: tuple[str, ...] = ()


@dataclass(slots=True)
class EvalCase:
    id: str
    office: str
    turns: list[EvalTurn] = field(default_factory=list)
    kind: str = "conversation"

    @property
    def employee_context(self) -> dict[str, str]:
        return dict(OFFICES[self.office])


def load_faq_cases(path: Path = DEFAULT_FAQ_PATH) -> list[EvalCase]:
    """One single-question case per row of the HR FAQ log."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    cases: list[EvalCase] = []
    for number, row in enumerate(rows, start=1):
        source_doc = (row.get("source_doc") or "").strip()
        country = (row.get("country") or "").strip()
        answerable = source_doc.lower() not in {"", "none", "n/a"}
        turn = EvalTurn(
            message=(row.get("question") or "").strip(),
            expect=EXPECT_ANSWER if answerable else EXPECT_NOT_FOUND,
            answer=(row.get("ground_truth_answer") or "").strip() if answerable else "",
            sources=(source_doc,) if answerable else (),
            country=country if country in COUNTRY_OFFICES else None,
        )
        office = COUNTRY_OFFICES.get(country, DEFAULT_OFFICE)
        cases.append(EvalCase(id=f"faq-{number:02d}", office=office, turns=[turn], kind="faq"))
    return cases


def load_conversation_cases(path: Path = DEFAULT_CONVERSATIONS_PATH) -> list[EvalCase]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [_conversation_case(entry) for entry in loaded]


def _conversation_case(entry: dict[str, Any]) -> EvalCase:
    case_id = entry["id"]
    office = entry.get("office", DEFAULT_OFFICE)
    if office not in OFFICES:
        raise ValueError(f"Conversation {case_id!r} uses unknown office {office!r}; use one of {sorted(OFFICES)}.")

    turns: list[EvalTurn] = []
    for turn in entry.get("turns", []):
        expect = turn.get("expect")
        if expect not in EXPECTATIONS:
            raise ValueError(f"Conversation {case_id!r} has a turn with expect={expect!r}; use one of {EXPECTATIONS}.")
        turns.append(
            EvalTurn(
                message=str(turn["message"]),
                expect=expect,
                answer=str(turn.get("answer", "")),
                sources=tuple(turn.get("sources", ())),
                country=turn.get("country"),
                mentions=tuple(turn.get("mentions", ())),
            )
        )
    return EvalCase(id=case_id, office=office, turns=turns)
