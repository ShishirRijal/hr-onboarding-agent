from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///data/interactions.db"
# escalation_status: None when answered; "offered" when the docs had no answer and the
# employee was asked about HR; then "requested" or "declined" once they chose, or
# "dismissed" when they asked something else without choosing. A requested question
# becomes "answered" once HR replies to it from the HR inbox.
HR_OFFERED = "offered"
HR_REQUESTED = "requested"
HR_DECLINED = "declined"
HR_DISMISSED = "dismissed"
HR_ANSWERED = "answered"


class Base(DeclarativeBase):
    pass


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # The signed-in user who asked. A chat belongs to the user whose questions are in it.
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    answered: Mapped[bool] = mapped_column(Boolean, index=True)
    escalation_status: Mapped[str | None] = mapped_column(String(16), index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who to reply to: only stored when the employee asks for the question to go to HR,
    # so declined and dismissed questions stay anonymous.
    employee_name: Mapped[str | None] = mapped_column(String(120))
    employee_email: Mapped[str | None] = mapped_column(String(254))
    # When the question went out in an HR digest email; None until then.
    hr_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    escalation_reason: Mapped[str | None] = mapped_column(String(64))
    # HR's reply from the HR inbox, shown to the employee in their chat.
    hr_answer: Mapped[str | None] = mapped_column(Text)
    hr_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    hr_answered_by: Mapped[str | None] = mapped_column(String(120))
    hr_answered_by_id: Mapped[str | None] = mapped_column(String(36))
    # Who the answer was added to the knowledge base for: one country, or "All".
    hr_answer_country: Mapped[str | None] = mapped_column(String(32))
    hr_answer_chunk_id: Mapped[str | None] = mapped_column(String(36))
    # When the employee opened the chat after HR replied; None while the reply is unread.
    hr_answer_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence_score: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(16))
    employee_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    hr_handoff: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    debug: Mapped[dict[str, Any]] = mapped_column(JSON)


@dataclass(slots=True)
class ChatSession:
    """One of a user's chats, as listed in the sidebar."""

    session_id: str
    title: str
    updated_at: datetime
    unread_hr_replies: int


class InteractionStore:
    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or database_url_from_env()
        ensure_sqlite_directory(url)
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        add_missing_columns(self._engine, Interaction.__table__)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def log(self, state: Mapping[str, Any]) -> str:
        response = state.get("final_response", {}) or {}
        handoff = state.get("hr_handoff")
        answered = bool(response.get("answered", True))
        interaction = Interaction(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            session_id=state.get("session_id"),
            user_id=state.get("user_id"),
            question=str(state.get("question", "")).strip(),
            answer=str(response.get("text", "")),
            answered=answered,
            escalation_status=None if answered else HR_OFFERED,
            escalated=False,
            escalated_at=None,
            escalation_reason=handoff.get("reason") if handoff else None,
            confidence_score=float(state.get("confidence_score", 0.0)),
            confidence_label=str(state.get("confidence_label", "low")),
            employee_context=dict(state.get("employee_context", {}) or {}),
            sources=list(response.get("sources", []) or []),
            hr_handoff=dict(handoff) if handoff else None,
            debug={
                "message_route": state.get("message_route", {}),
                "retrieval": state.get("retrieval_debug", {}),
                "confidence": state.get("confidence_debug", {}),
            },
        )

        with self._sessions.begin() as session:
            if interaction.session_id:
                # Moving on without answering an HR offer counts as a no.
                session.execute(
                    update(Interaction)
                    .where(Interaction.session_id == interaction.session_id)
                    .where(Interaction.escalation_status == HR_OFFERED)
                    .values(escalation_status=HR_DISMISSED)
                )
            session.add(interaction)
        return interaction.id

    def get(self, interaction_id: str) -> Interaction | None:
        with self._sessions() as session:
            return session.get(Interaction, interaction_id)

    def record_hr_choice(
        self,
        interaction_id: str,
        *,
        ask_hr: bool,
        name: str | None = None,
        email: str | None = None,
    ) -> Interaction | None:
        with self._sessions.begin() as session:
            interaction = session.get(Interaction, interaction_id)
            if interaction is None:
                return None
            if interaction.answered:
                raise ValueError("Only unanswered questions can be sent to HR.")
            interaction.escalation_status = HR_REQUESTED if ask_hr else HR_DECLINED
            interaction.escalated = ask_hr
            interaction.escalated_at = datetime.now(timezone.utc) if ask_hr else None
            interaction.employee_name = name if ask_hr else None
            interaction.employee_email = email if ask_hr else None
            return interaction

    def list_session(self, session_id: str) -> list[Interaction]:
        with self._sessions() as session:
            query = (
                select(Interaction)
                .where(Interaction.session_id == session_id)
                .order_by(Interaction.created_at)
            )
            return list(session.scalars(query))

    def session_owners(self, session_id: str) -> set[str | None]:
        """Who asked the questions in a chat: empty for a new chat, otherwise one user."""
        with self._sessions() as session:
            query = select(Interaction.user_id).where(Interaction.session_id == session_id).distinct()
            return set(session.scalars(query))

    def list_user_sessions(self, user_id: str) -> list[ChatSession]:
        """The user's chats, most recently active first."""
        with self._sessions() as session:
            query = (
                select(Interaction)
                .where(Interaction.user_id == user_id)
                .where(Interaction.session_id.is_not(None))
                .order_by(Interaction.created_at)
            )
            chats: dict[str, ChatSession] = {}
            for interaction in session.scalars(query):
                chat = chats.get(interaction.session_id)
                if chat is None:
                    # The first question names the chat.
                    chat = chats[interaction.session_id] = ChatSession(
                        session_id=interaction.session_id,
                        title=interaction.question[:80],
                        updated_at=as_utc(interaction.created_at),
                        unread_hr_replies=0,
                    )
                # An HR reply counts as activity, so its chat moves back to the top.
                chat.updated_at = max(chat.updated_at, as_utc(interaction.hr_answered_at or interaction.created_at))
                if interaction.hr_answered_at is not None and interaction.hr_answer_read_at is None:
                    chat.unread_hr_replies += 1
        return sorted(chats.values(), key=lambda chat: chat.updated_at, reverse=True)

    def mark_hr_answers_read(self, session_id: str, *, at: datetime | None = None) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(Interaction)
                .where(Interaction.session_id == session_id)
                .where(Interaction.hr_answered_at.is_not(None))
                .where(Interaction.hr_answer_read_at.is_(None))
                .values(hr_answer_read_at=at or datetime.now(timezone.utc))
            )

    def hr_questions(self, status: str = HR_REQUESTED) -> list[Interaction]:
        """Questions sent to HR: open ones oldest first, answered ones newest first."""
        with self._sessions() as session:
            query = select(Interaction).where(Interaction.escalation_status == status)
            if status == HR_ANSWERED:
                query = query.order_by(Interaction.hr_answered_at.desc())
            else:
                query = query.order_by(Interaction.escalated_at)
            return list(session.scalars(query))

    def record_hr_answer(
        self,
        interaction_id: str,
        *,
        answer: str,
        answered_by: str,
        answered_by_id: str,
        country: str,
        chunk_id: str | None,
        at: datetime | None = None,
    ) -> Interaction | None:
        with self._sessions.begin() as session:
            interaction = session.get(Interaction, interaction_id)
            if interaction is None:
                return None
            if interaction.escalation_status != HR_REQUESTED:
                raise ValueError("Only open questions sent to HR can be answered.")
            interaction.escalation_status = HR_ANSWERED
            interaction.hr_answer = answer
            interaction.hr_answered_at = at or datetime.now(timezone.utc)
            interaction.hr_answered_by = answered_by
            interaction.hr_answered_by_id = answered_by_id
            interaction.hr_answer_country = country
            interaction.hr_answer_chunk_id = chunk_id
            return interaction

    def count_hr_answered_since(self, since: datetime) -> int:
        with self._sessions() as session:
            query = select(func.count()).select_from(Interaction).where(Interaction.hr_answered_at >= since)
            return int(session.scalar(query) or 0)

    def unanswered_since(self, since: datetime) -> list[Interaction]:
        """Questions the documents couldn't answer, whatever the employee chose to do next."""
        with self._sessions() as session:
            query = (
                select(Interaction)
                .where(Interaction.answered.is_(False))
                .where(Interaction.created_at >= since)
                .order_by(Interaction.created_at)
            )
            return list(session.scalars(query))

    def pending_hr_requests(self) -> list[Interaction]:
        """Questions the employee sent to HR that haven't gone out in a digest yet. Ones HR
        already answered in the inbox are left out."""
        with self._sessions() as session:
            query = (
                select(Interaction)
                .where(Interaction.escalation_status == HR_REQUESTED)
                .where(Interaction.hr_notified_at.is_(None))
                .order_by(Interaction.escalated_at)
            )
            return list(session.scalars(query))

    def mark_hr_notified(self, interaction_ids: list[str], *, at: datetime | None = None) -> None:
        if not interaction_ids:
            return
        with self._sessions.begin() as session:
            session.execute(
                update(Interaction)
                .where(Interaction.id.in_(interaction_ids))
                .values(hr_notified_at=at or datetime.now(timezone.utc))
            )

    def list_escalations(self, *, since: datetime | None = None) -> list[Interaction]:
        with self._sessions() as session:
            query = select(Interaction).where(Interaction.escalated.is_(True))
            if since is not None:
                query = query.where(Interaction.created_at >= since)
            return list(session.scalars(query.order_by(Interaction.created_at)))


def database_url_from_env() -> str:
    return os.getenv("INTERACTIONS_DATABASE_URL", DEFAULT_DATABASE_URL)


def as_utc(moment: datetime) -> datetime:
    # SQLite hands datetimes back without a timezone; they are all stored in UTC.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def add_missing_columns(engine: Any, table: Table) -> None:
    # create_all only creates missing tables; add columns introduced after a database was created.
    existing = {column["name"] for column in inspect(engine).get_columns(table.name)}
    with engine.begin() as connection:
        for column in table.columns:
            if column.name not in existing:
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}'))


def ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != f"{prefix}:memory:":
        Path(database_url[len(prefix):]).parent.mkdir(parents=True, exist_ok=True)
