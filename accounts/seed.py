from __future__ import annotations

from datetime import date
from typing import Any

from .store import REMOTE_OFFICE, ROLE_EMPLOYEE, ROLE_HR, User, UserStore

# One shared password for every demo account. Demo only: never use seeded accounts outside
# local development.
DEMO_PASSWORD = "nordtech-demo"

# Fictional people for trying the app. The employees are new to NordTech, so none of them
# is in the org chart yet; their managers are, and so is the HR Business Partner.
DEMO_USERS: tuple[dict[str, Any], ...] = (
    {
        "email": "marju.ilves@nordtech.test",
        "name": "Marju Ilves",
        "role": ROLE_HR,
        "job_title": "HR Business Partner",
        "department": "HR",
        "office": "Tallinn",
        "country": "Estonia",
        "manager_name": "Eva Kallas",
        "start_date": date(2021, 2, 1),
        "pronouns": "she/her",
    },
    {
        "email": "kertu.vaher@nordtech.test",
        "name": "Kertu Vaher",
        "role": ROLE_EMPLOYEE,
        "job_title": "Junior Backend Engineer",
        "department": "Engineering",
        "office": "Tallinn",
        "country": "Estonia",
        "manager_name": "Priit Kask",
        "start_date": date(2026, 10, 19),
        "pronouns": "she/her",
    },
    {
        "email": "joonas.laaksonen@nordtech.test",
        "name": "Joonas Laaksonen",
        "role": ROLE_EMPLOYEE,
        "job_title": "Senior Account Executive",
        "department": "Sales",
        "office": "Tampere",
        "country": "Finland",
        "manager_name": "Jukka Hämäläinen",
        "start_date": date(2026, 10, 26),
        "pronouns": "he/him",
    },
    {
        "email": "mariana.lopes@nordtech.test",
        "name": "Mariana Lopes",
        "role": ROLE_EMPLOYEE,
        "job_title": "Product Designer",
        "department": "Design",
        "office": "Porto",
        "country": "Portugal",
        "manager_name": "Beatriz Almeida",
        "start_date": date(2025, 3, 3),
        "pronouns": "she/her",
    },
    {
        "email": "alex.rinne@nordtech.test",
        "name": "Alex Rinne",
        "role": ROLE_EMPLOYEE,
        "job_title": "Site Reliability Engineer",
        "department": "Engineering",
        "office": REMOTE_OFFICE,
        "country": "Finland",
        "manager_name": "Priit Kask",
        "start_date": date(2026, 9, 14),
        "pronouns": "they/them",
    },
    {
        "email": "duarte.mendes@nordtech.test",
        "name": "Duarte Mendes",
        "role": ROLE_EMPLOYEE,
        "job_title": "Marketing Lead",
        "department": "Marketing",
        "office": "Porto",
        "country": "Portugal",
        "manager_name": "Laura Silva",
        "start_date": date(2023, 5, 15),
        "pronouns": "he/him",
    },
)


def seed_demo_users(store: UserStore, *, password: str = DEMO_PASSWORD) -> list[User]:
    """Adds the demo accounts that don't exist yet. Returns the ones it added."""
    return [
        store.create_user(**account, password=password)
        for account in DEMO_USERS
        if store.get_by_email(account["email"]) is None
    ]
