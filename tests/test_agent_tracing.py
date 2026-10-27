from __future__ import annotations

from agent import tracing


def test_names_emails_and_personal_fields_are_masked_everywhere() -> None:
    tracing.set_masked_names(["Joonas Laaksonen", "Alex Rinne"])
    data = {
        "question": "Hi, I'm Joonas Laaksonen (joonas.laaksonen@nordtech.test). Does ALEX get the same?",
        "messages": [("human", "The employee is Joonas, based in Tampere, Finland.")],
        "employee_context": {"employee_name": "Joonas Laaksonen", "role": "Senior Account Executive", "employee_country": "Finland"},
        "count": 3,
    }

    masked = tracing.mask(data=data)

    assert masked["question"] == "Hi, I'm [name] ([email]). Does [name] get the same?"
    assert masked["messages"] == [["human", "The employee is [name], based in Tampere, Finland."]]
    assert masked["employee_context"] == {"employee_name": "[redacted]", "role": "[redacted]", "employee_country": "Finland"}
    assert masked["count"] == 3


def test_words_inside_other_words_are_left_alone() -> None:
    tracing.set_masked_names(["Alex Rinne"])

    assert tracing.mask(data="Alexander asked about Alex.") == "Alexander asked about [name]."


def test_tracing_stays_off_without_keys(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")

    assert tracing.start_tracing(["Joonas Laaksonen"]) is False
    assert tracing.tracing_callbacks() == []


def test_trace_metadata_uses_the_account_id_not_the_name() -> None:
    assert tracing.trace_metadata(session_id="s-1", user_id="user-1", tags=["chat"]) == {
        "langfuse_tags": ["chat"],
        "langfuse_session_id": "s-1",
        "langfuse_user_id": "user-1",
    }
