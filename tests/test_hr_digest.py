from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from interactions import InteractionStore
from interactions.digest import DigestSettings, compose_hr_digest, send_hr_digest

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path) -> InteractionStore:
    return InteractionStore(f"sqlite:///{tmp_path / 'interactions.db'}")


def _ask(store: InteractionStore, question: str, *, send: bool, name="Shishir Rijal", email="shishir@nordtech.test"):
    interaction_id = store.log(
        {
            "session_id": f"session-{question}",
            "question": question,
            "employee_context": {"employee_country": "Estonia", "office_location": "Tallinn"},
            "final_response": {"text": "Not in the HR documents. Ask HR?", "sources": [], "answered": False},
            "hr_handoff": {
                "reason": "answer_declined",
                "candidate_sources": [
                    {"section_path": "NordTech Solutions — Employee Handbook v2.1 > 6. Office Life"},
                    {"section_path": "NordTech Solutions — Employee Handbook v2.1 > 7. Remote Work Policy"},
                ],
            },
        }
    )
    store.record_hr_choice(interaction_id, ask_hr=send, name=name, email=email)
    return interaction_id


def test_digest_lists_each_question_with_who_to_reply_to(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _ask(store, "Can I bring my dog to the office?", send=True)
    _ask(store, "Is there bike storage in <Porto>?", send=True, name="Ana Costa", email="ana@nordtech.test")

    message = compose_hr_digest(store.pending_hr_requests(), DigestSettings(), now=NOW)

    assert message["Subject"] == "2 new questions for HR from the HR assistant (27 Oct 2026)"
    assert message["To"] == "hr@nordtech.test"
    assert message["Reply-To"] is None
    text = message.get_body(preferencelist=("plain",)).get_content()
    assert "1. Can I bring my dog to the office?" in text
    assert "From: Shishir Rijal <shishir@nordtech.test>" in text
    assert "Works in: Tallinn, Estonia" in text
    assert "The HR documents mention the topic but don't answer the question." in text
    assert "Documents checked: Employee Handbook v2.1" in text
    page = message.get_body(preferencelist=("html",)).get_content()
    assert "mailto:ana@nordtech.test" in page
    assert "&lt;Porto&gt;" in page and "<Porto>" not in page


def test_a_single_question_can_be_answered_by_replying(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _ask(store, "Can I bring my dog to the office?", send=True)

    message = compose_hr_digest(store.pending_hr_requests(), DigestSettings(), now=NOW)

    assert message["Subject"] == "1 new question for HR from the HR assistant (27 Oct 2026)"
    assert message["Reply-To"] == "shishir@nordtech.test"


def test_send_emails_only_questions_sent_to_hr_and_marks_them(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _ask(store, "Can I bring my dog to the office?", send=True)
    _ask(store, "Is there parking?", send=False)
    outbox = []

    assert send_hr_digest(store, DigestSettings(), send=outbox.append, now=NOW) == 1
    assert len(outbox) == 1
    assert "Is there parking?" not in outbox[0].get_body(preferencelist=("plain",)).get_content()
    # Already emailed, so the next run has nothing to send.
    assert send_hr_digest(store, DigestSettings(), send=outbox.append, now=NOW) == 0
    assert len(outbox) == 1


def test_failed_send_leaves_questions_for_next_time(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _ask(store, "Can I bring my dog to the office?", send=True)

    def broken_send(message):
        raise OSError("SMTP server unavailable")

    with pytest.raises(OSError):
        send_hr_digest(store, DigestSettings(), send=broken_send, now=NOW)
    assert len(store.pending_hr_requests()) == 1


def test_digest_links_each_question_to_the_hr_inbox(tmp_path: Path) -> None:
    store = _store(tmp_path)
    interaction_id = _ask(store, "Can I bring my dog to the office?", send=True)

    message = compose_hr_digest(
        store.pending_hr_requests(), DigestSettings(inbox_url="https://hr.nordtech.test/hr"), now=NOW
    )

    text = message.get_body(preferencelist=("plain",)).get_content()
    assert "HR inbox: https://hr.nordtech.test/hr" in text
    assert f"Answer it: https://hr.nordtech.test/hr/q/{interaction_id}" in text
    page = message.get_body(preferencelist=("html",)).get_content()
    assert f'href="https://hr.nordtech.test/hr/q/{interaction_id}"' in page
