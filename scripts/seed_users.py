from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from accounts import DEMO_PASSWORD, DEMO_USERS, UserStore, seed_demo_users


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add the demo accounts to the database (INTERACTIONS_DATABASE_URL). The API already "
        "does this on startup when there are no accounts; this also adds any that are missing."
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    parse_args()
    store = UserStore()
    added = {user.email for user in seed_demo_users(store)}

    print(f"Added {len(added)} demo account(s). All use the password {DEMO_PASSWORD!r} (demo only).\n")
    for account in DEMO_USERS:
        status = "added" if account["email"] in added else "already there"
        print(f"{account['role']:<9} {account['email']:<32} {account['name']:<18} {status}")


if __name__ == "__main__":
    main()
