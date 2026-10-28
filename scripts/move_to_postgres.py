"""Moves the app's data from the SQLite file to Postgres: chats, HR requests, feedback and
reviews, model calls, accounts and sign-in sessions.

Stop the API first, so nothing is written during the copy. The SQLite file is backed up to
data/backups/ and opened read-only, so it's never changed; the copy is refused if Postgres
already has rows. Afterwards, set INTERACTIONS_DATABASE_URL to the Postgres URL.

    PYTHONPATH=. poetry run python scripts/move_to_postgres.py \
        --to postgresql+psycopg://hr:hr-local@localhost:5433/hr_onboarding
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interactions.copy_database import CopyError, back_up_sqlite, copy_database

DEFAULT_SOURCE = "sqlite:///data/interactions.db"
BACKUP_DIR = Path("data/backups")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the SQLite database into an empty Postgres database.")
    parser.add_argument("--from", dest="source", default=DEFAULT_SOURCE, help=f"SQLite URL (default {DEFAULT_SOURCE}).")
    parser.add_argument("--to", dest="target", required=True, help="Postgres URL, postgresql+psycopg://...")
    args = parser.parse_args()

    if not args.target.startswith("postgresql"):
        raise SystemExit("--to should be a Postgres URL, postgresql+psycopg://user:password@host:port/database")
    backup = back_up_sqlite(args.source, BACKUP_DIR)
    print(f"Backed up {args.source} to {backup}")
    try:
        copied = copy_database(args.source, args.target)
    except CopyError as exc:
        raise SystemExit(f"Not copied: {exc}") from exc
    for table, rows in copied.items():
        print(f"{table:<14} {rows:>6} rows")
    print("Every row is in Postgres. Set INTERACTIONS_DATABASE_URL to the Postgres URL and restart the API.")


if __name__ == "__main__":
    main()
