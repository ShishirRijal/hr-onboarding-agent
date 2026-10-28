from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from accounts import UserStore
from agent.usage import ModelCall
from interactions import InteractionStore
from interactions.copy_database import CopyError, back_up_sqlite, copy_database

# Set to an empty Postgres database (CI does) to also copy into real Postgres.
POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


def _fill(url: str) -> dict[str, str]:
    users = UserStore(url)
    user = users.create_user(
        email="kertu.vaher@nordtech.test",
        name="Kertu Vaher",
        password="secret-pass",
        role="employee",
        job_title="Junior Backend Engineer",
        department="Engineering",
        office="Tallinn",
        country="Estonia",
        start_date=date(2026, 10, 19),
    )
    users.start_session(user.id)
    store = InteractionStore(url)
    interaction_id = store.log(
        {
            "session_id": "s-1",
            "user_id": user.id,
            "question": "How much leave do I get?",
            "employee_context": user.employee_context(),
            "final_response": {"text": "28 days [1].", "sources": [{"chunk_id": "c1"}], "answered": True},
            "memory": {"summary": "- Expecting a baby in March.", "turns_covered": 5},
        }
    )
    store.record_feedback(interaction_id, rating="up", comment=None)
    store.record_model_calls(
        [ModelCall("gpt-4o-mini", "generate_answer", 1200, 0, 80), ModelCall("gpt-4.1", "check_answer", 1500, 0, 60)],
        source="chat",
        interaction_id=interaction_id,
        at=datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc),
    )
    return {"user_id": user.id, "interaction_id": interaction_id}


def _check_copied(target_url: str, ids: dict[str, str]) -> None:
    store = InteractionStore(target_url)
    copied = store.get(ids["interaction_id"])
    assert copied.question == "How much leave do I get?"
    assert copied.sources == [{"chunk_id": "c1"}]
    assert copied.feedback == "up"
    assert store.chat_memory("s-1") == {"summary": "- Expecting a baby in March.", "turns_covered": 5}
    calls = store.interaction_model_calls(ids["interaction_id"])
    assert sorted(call.model for call in calls) == ["gpt-4.1", "gpt-4o-mini"]
    users = UserStore(target_url)
    assert users.authenticate("kertu.vaher@nordtech.test", "secret-pass").id == ids["user_id"]
    # New rows still get their own ids after the copied ones.
    store.record_model_calls([ModelCall("gpt-4o-mini", "understand_message", 10, 0, 5)], source="chat")
    assert len(store.model_calls_since(datetime(2026, 1, 1, tzinfo=timezone.utc))) == 3


def test_every_table_is_copied_and_the_source_is_left_alone(tmp_path: Path) -> None:
    source = f"sqlite:///{tmp_path / 'interactions.db'}"
    ids = _fill(source)
    before = (tmp_path / "interactions.db").read_bytes()

    copied = copy_database(source, f"sqlite:///{tmp_path / 'copy.db'}")

    assert copied == {"users": 1, "auth_sessions": 1, "interactions": 1, "model_calls": 2}
    assert (tmp_path / "interactions.db").read_bytes() == before
    _check_copied(f"sqlite:///{tmp_path / 'copy.db'}", ids)


def test_a_target_with_data_is_refused(tmp_path: Path) -> None:
    source = f"sqlite:///{tmp_path / 'interactions.db'}"
    target = f"sqlite:///{tmp_path / 'copy.db'}"
    _fill(source)
    copy_database(source, target)

    with pytest.raises(CopyError, match="already has rows"):
        copy_database(source, target)


def test_a_missing_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CopyError, match="No database"):
        copy_database(f"sqlite:///{tmp_path / 'missing.db'}", f"sqlite:///{tmp_path / 'copy.db'}")


def test_columns_added_since_the_source_was_made_are_left_empty(tmp_path: Path) -> None:
    source = tmp_path / "old.db"
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE model_calls (id INTEGER PRIMARY KEY, at DATETIME, source VARCHAR(16), model VARCHAR(64),"
            " input_tokens INTEGER, cached_input_tokens INTEGER, output_tokens INTEGER)"
        )
        connection.execute("INSERT INTO model_calls VALUES (7, '2026-10-28 09:30:00', 'chat', 'gpt-4o-mini', 10, 0, 5)")

    copied = copy_database(f"sqlite:///{source}", f"sqlite:///{tmp_path / 'copy.db'}")

    assert copied["model_calls"] == 1 and copied["interactions"] == 0
    (call,) = InteractionStore(f"sqlite:///{tmp_path / 'copy.db'}").model_calls_since(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert (call.id, call.step, call.cost_usd) == (7, None, None)


def test_the_backup_is_a_full_copy(tmp_path: Path) -> None:
    source = f"sqlite:///{tmp_path / 'interactions.db'}"
    ids = _fill(source)

    backup = back_up_sqlite(source, tmp_path / "backups")

    assert backup.name.startswith("interactions-") and backup.name.endswith("-before-postgres.db")
    assert InteractionStore(f"sqlite:///{backup}").get(ids["interaction_id"]) is not None


@pytest.fixture
def postgres_database():
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL isn't set")
    # A fresh database per test, dropped afterwards.
    name = f"copy_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {name}"))
    yield POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
    admin.dispose()


def test_copying_into_postgres(tmp_path: Path, postgres_database: str) -> None:
    source = f"sqlite:///{tmp_path / 'interactions.db'}"
    ids = _fill(source)

    copied = copy_database(source, postgres_database)

    assert copied == {"users": 1, "auth_sessions": 1, "interactions": 1, "model_calls": 2}
    _check_copied(postgres_database, ids)
