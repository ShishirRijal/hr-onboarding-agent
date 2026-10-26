from __future__ import annotations

import html
import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

from .inbox import documents_checked, reason_text, workplace
from .store import Interaction, InteractionStore

logger = logging.getLogger(__name__)

DEFAULT_DIGEST_TO = "hr@nordtech.test"
DEFAULT_DIGEST_FROM = "hr-assistant@nordtech.test"
DEFAULT_DIGEST_TIME = "18:00"
DEFAULT_DIGEST_TIMEZONE = "Europe/Tallinn"
DEFAULT_HR_INBOX_URL = "http://localhost:3000/hr"


@dataclass(slots=True)
class DigestSettings:
    recipient: str = DEFAULT_DIGEST_TO
    sender: str = DEFAULT_DIGEST_FROM
    # Where HR answers the questions: the HR inbox in the web app.
    inbox_url: str = DEFAULT_HR_INBOX_URL
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    # "HH:MM" in `timezone`, or empty to turn the daily email off.
    send_at: str = DEFAULT_DIGEST_TIME
    timezone: str = DEFAULT_DIGEST_TIMEZONE

    @classmethod
    def from_env(cls) -> DigestSettings:
        return cls(
            recipient=os.getenv("HR_DIGEST_TO", DEFAULT_DIGEST_TO),
            sender=os.getenv("HR_DIGEST_FROM", DEFAULT_DIGEST_FROM),
            inbox_url=os.getenv("HR_INBOX_URL", DEFAULT_HR_INBOX_URL).rstrip("/"),
            smtp_host=os.getenv("SMTP_HOST", "localhost"),
            smtp_port=int(os.getenv("SMTP_PORT", "1025")),
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_starttls=os.getenv("SMTP_STARTTLS", "").strip().lower() in {"1", "true", "yes"},
            send_at=os.getenv("HR_DIGEST_TIME", DEFAULT_DIGEST_TIME).strip(),
            timezone=os.getenv("HR_DIGEST_TIMEZONE", DEFAULT_DIGEST_TIMEZONE),
        )


def smtp_sender(settings: DigestSettings) -> Callable[[EmailMessage], None]:
    def send(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)

    return send


def send_hr_digest(
    store: InteractionStore,
    settings: DigestSettings,
    *,
    send: Callable[[EmailMessage], None] | None = None,
    now: datetime | None = None,
) -> int:
    """Emails HR every question sent to them since the last digest. Returns how many went out.

    Nothing is sent when there is nothing new. Questions are marked only after the email
    is accepted, so a failed send is retried next time instead of being lost.
    """
    pending = store.pending_hr_requests()
    if not pending:
        logger.info("HR digest: no new questions for HR.")
        return 0

    sent_at = now or datetime.now(timezone.utc)
    message = compose_hr_digest(pending, settings, now=sent_at)
    (send or smtp_sender(settings))(message)
    store.mark_hr_notified([interaction.id for interaction in pending], at=sent_at)
    logger.info("HR digest: emailed %d question(s) to %s.", len(pending), settings.recipient)
    return len(pending)


def compose_hr_digest(
    interactions: Sequence[Interaction],
    settings: DigestSettings,
    *,
    now: datetime,
) -> EmailMessage:
    local_zone = ZoneInfo(settings.timezone)
    count = len(interactions)
    noun = "question" if count == 1 else "questions"
    local_now = now.astimezone(local_zone)
    day = f"{local_now.day} {local_now:%b %Y}"

    message = EmailMessage()
    message["Subject"] = f"{count} new {noun} for HR from the HR assistant ({day})"
    message["From"] = settings.sender
    message["To"] = settings.recipient
    # With a single question, replying goes straight to the employee.
    if count == 1 and interactions[0].employee_email:
        message["Reply-To"] = interactions[0].employee_email

    items = [_digest_item(interaction, local_zone, settings.inbox_url) for interaction in interactions]
    intro = (
        f"{count} employee {noun} came in through the HR assistant that the HR documents couldn't "
        "answer. The employees asked for them to be sent to you. Answer them in the HR inbox: the "
        "employee sees your answer in their chat, and the assistant can use it for similar questions."
    )
    message.set_content(_plain_text(intro, items, settings.inbox_url))
    message.add_alternative(_html(intro, items, settings.inbox_url), subtype="html")
    return message


def _digest_item(interaction: Interaction, local_zone: ZoneInfo, inbox_url: str) -> dict[str, Any]:
    asked_at = interaction.escalated_at or interaction.created_at
    if asked_at.tzinfo is None:
        asked_at = asked_at.replace(tzinfo=timezone.utc)
    return {
        "name": interaction.employee_name or "An employee",
        "email": interaction.employee_email,
        "workplace": workplace(interaction.employee_context or {}),
        "asked_at": _short_time(asked_at.astimezone(local_zone)),
        "question": interaction.question,
        "reason": reason_text(interaction.escalation_reason),
        "documents": documents_checked(interaction.hr_handoff or {}),
        "answer_url": f"{inbox_url}/q/{interaction.id}",
    }


def _short_time(moment: datetime) -> str:
    return f"{moment.day} {moment:%b, %H:%M}"


def _plain_text(intro: str, items: list[dict[str, Any]], inbox_url: str) -> str:
    blocks = [intro, f"HR inbox: {inbox_url}"]
    for number, item in enumerate(items, start=1):
        contact = f"{item['name']} <{item['email']}>" if item["email"] else item["name"]
        lines = [
            f"{number}. {item['question']}",
            f"   From: {contact}",
            f"   Works in: {item['workplace']}",
            f"   Asked: {item['asked_at']}",
            f"   Why it came to you: {item['reason']}",
        ]
        if item["documents"]:
            lines.append(f"   Documents checked: {', '.join(item['documents'])}")
        lines.append(f"   Answer it: {item['answer_url']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def _html(intro: str, items: list[dict[str, Any]], inbox_url: str) -> str:
    def row(label: str, value: str) -> str:
        return (
            f'<tr><td style="color:#6b707a;padding:2px 12px 2px 0;vertical-align:top;white-space:nowrap">{label}</td>'
            f'<td style="padding:2px 0">{value}</td></tr>'
        )

    cards = []
    for item in items:
        name = html.escape(item["name"])
        if item["email"]:
            email = html.escape(item["email"])
            link = f'<a href="mailto:{email}?subject=Your%20HR%20question" style="color:#2b8659">{email}</a>'
            contact = f"{name} &lt;{link}&gt;"
        else:
            contact = name
        rows = [
            row("From", contact),
            row("Works in", html.escape(item["workplace"])),
            row("Asked", html.escape(item["asked_at"])),
            row("Why it came to you", html.escape(item["reason"])),
        ]
        if item["documents"]:
            rows.append(row("Documents checked", html.escape(", ".join(item["documents"]))))
        cards.append(
            '<div style="border:1px solid #e3e6e9;border-radius:12px;padding:16px;margin:0 0 12px">'
            f'<p style="margin:0 0 10px;font-size:16px;font-weight:600">{html.escape(item["question"])}</p>'
            f'<table style="font-size:14px;border-collapse:collapse">{"".join(rows)}</table>'
            f'<p style="margin:12px 0 0;font-size:14px"><a href="{html.escape(item["answer_url"])}" '
            'style="color:#2b8659;font-weight:600">Answer in the HR inbox</a></p>'
            "</div>"
        )

    return (
        '<div style="font-family:Inter,Arial,sans-serif;color:#2f313f;max-width:640px">'
        f'<p style="font-size:15px;line-height:1.5">{html.escape(intro)}</p>'
        f'<p style="margin:0 0 16px"><a href="{html.escape(inbox_url)}" style="display:inline-block;'
        'background:#2b8659;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;'
        'padding:10px 18px;border-radius:9999px">Open the HR inbox</a></p>'
        f'{"".join(cards)}'
        "</div>"
    )


def schedule_daily_digest(store: InteractionStore, settings: DigestSettings) -> Any | None:
    """Sends the digest every day at `settings.send_at`. Returns the running scheduler, or None
    when the daily email is turned off."""
    if not settings.send_at:
        logger.info("HR digest: daily email is off (HR_DIGEST_TIME is empty).")
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour, minute = (int(part) for part in settings.send_at.split(":"))
    zone = ZoneInfo(settings.timezone)

    def run() -> None:
        try:
            send_hr_digest(store, settings)
        except Exception:
            logger.exception("HR digest: sending failed; the questions will go out next time.")

    scheduler = BackgroundScheduler(timezone=zone)
    scheduler.add_job(run, CronTrigger(hour=hour, minute=minute, timezone=zone), id="hr_digest")
    scheduler.start()
    logger.info("HR digest: emailing %s daily at %s (%s).", settings.recipient, settings.send_at, settings.timezone)
    return scheduler
