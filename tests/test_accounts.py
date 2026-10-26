from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from accounts import DEMO_PASSWORD, DEMO_USERS, UserStore, hash_password, seed_demo_users, verify_password
from api.main import create_app

ACCOUNT = {
    "email": "kertu.vaher@nordtech.test",
    "name": "Kertu Vaher",
    "role": "employee",
    "job_title": "Junior Backend Engineer",
    "department": "Engineering",
    "office": "Tallinn",
    "country": "Estonia",
    "start_date": date(2026, 10, 19),
}


def _store(tmp_path: Path) -> UserStore:
    return UserStore(f"sqlite:///{tmp_path / 'users.db'}")


def test_passwords_are_salted_scrypt_hashes() -> None:
    first = hash_password("nordtech-demo")
    second = hash_password("nordtech-demo")

    assert first.startswith("scrypt$")
    assert "nordtech-demo" not in first
    assert first != second
    assert verify_password("nordtech-demo", first)
    assert not verify_password("nordtech-demo!", first)
    assert not verify_password("nordtech-demo", "not a hash")


def test_sign_in_matches_email_case_insensitively_and_checks_the_password(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_user(**ACCOUNT, password="secret")

    assert store.authenticate("Kertu.Vaher@NordTech.test", "secret").name == "Kertu Vaher"
    assert store.authenticate("kertu.vaher@nordtech.test", "wrong") is None
    assert store.authenticate("nobody@nordtech.test", "secret") is None


def test_sessions_expire_and_can_be_ended(tmp_path: Path) -> None:
    store = _store(tmp_path)
    user = store.create_user(**ACCOUNT, password="secret")
    now = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)
    token = store.start_session(user.id, now=now)

    assert store.user_for_session(token, now=now + timedelta(days=6)).id == user.id
    assert store.user_for_session(token, now=now + timedelta(days=8)) is None
    store.end_session(token)
    assert store.user_for_session(token, now=now) is None


def test_employee_context_comes_from_the_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    remote = store.create_user(
        **{**ACCOUNT, "email": "alex.rinne@nordtech.test", "office": "Remote", "country": "Finland"},
        password="secret",
    )

    context = remote.employee_context()
    # Remote work doesn't change the country whose rules apply.
    assert context["employee_country"] == "Finland"
    assert context["office_location"] == "Remote"
    assert context["role"] == "Junior Backend Engineer"
    assert context["date_of_joining"] == "2026-10-19"


def test_demo_accounts_cover_both_roles_and_a_mix_of_people() -> None:
    assert sum(account["role"] == "hr" for account in DEMO_USERS) == 1
    assert sum(account["role"] == "employee" for account in DEMO_USERS) == 5
    assert all(account["email"].endswith("@nordtech.test") for account in DEMO_USERS)
    assert {"Tallinn", "Tampere", "Porto", "Remote"} <= {account["office"] for account in DEMO_USERS}
    assert {"she/her", "he/him", "they/them"} <= {account["pronouns"] for account in DEMO_USERS}
    assert any(account["start_date"] >= date(2026, 10, 1) for account in DEMO_USERS)


def test_seeding_adds_the_demo_accounts_once(tmp_path: Path) -> None:
    store = _store(tmp_path)

    added = seed_demo_users(store)
    again = seed_demo_users(store)

    assert len(added) == len(DEMO_USERS)
    assert again == []
    assert store.count() == len(DEMO_USERS)
    assert store.authenticate("marju.ilves@nordtech.test", DEMO_PASSWORD).role == "hr"


def test_the_api_seeds_demo_accounts_into_an_empty_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERACTIONS_DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    app = create_app(graph=object(), store=object(), passages=object())

    with TestClient(app) as client:
        response = client.post("/auth/sign-in", json={"email": "alex.rinne@nordtech.test", "password": DEMO_PASSWORD})

    assert response.status_code == 200
    assert response.json()["pronouns"] == "they/them"
