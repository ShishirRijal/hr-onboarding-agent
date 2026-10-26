from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interactions import InteractionStore
from interactions.digest import DigestSettings, compose_hr_digest, send_hr_digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Email HR the questions employees sent them since the last digest. "
        "The API already does this daily at HR_DIGEST_TIME; use this to send now or from cron."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the email instead of sending it, and leave the questions unsent.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    store = InteractionStore()
    settings = DigestSettings.from_env()

    if args.dry_run:
        pending = store.pending_hr_requests()
        if not pending:
            print("No new questions for HR.")
            return
        message = compose_hr_digest(pending, settings, now=datetime.now(timezone.utc))
        print(f"To: {message['To']}\nSubject: {message['Subject']}\n")
        print(message.get_body(preferencelist=("plain",)).get_content())
        return

    try:
        count = send_hr_digest(store, settings)
    except OSError as exc:
        print(
            f"Error: couldn't send email through {settings.smtp_host}:{settings.smtp_port}. "
            "Check the SMTP settings in .env, or start Mailpit with `docker-compose up -d mailpit`.",
            file=sys.stderr,
        )
        print(f"Reason: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Emailed {count} question(s) to {settings.recipient}." if count else "No new questions for HR.")


if __name__ == "__main__":
    main()
