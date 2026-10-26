from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, create_engine, inspect, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///data/interactions.db"
# escalation_status: None when answered; "offered" when the docs had no answer and the
# employee was asked about HR; then "requested" or "declined" once they chose, or
# "dismissed" when they asked something else without choosing.
HR_OFFERED = "offered"
HR_REQUESTED = "requested"
HR_DECLINED = "declined"
HR_DISMISSED = "dismissed"


class Base(DeclarativeBase):
    pass


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    answered: Mapped[bool] = mapped_column(Boolean, index=True)
    escalation_status: Mapped[str | None] = mapped_column(String(16), index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[str | None] = mapped_column(String(64))
    confidence_score: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(16))
    employee_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    hr_handoff: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    debug: Mapped[dict[str, Any]] = mapped_column(JSON)


class InteractionStore:
    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or os.getenv("INTERACTIONS_DATABASE_URL", DEFAULT_DATABASE_URL)
        _ensure_sqlite_directory(url)
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        _add_missing_columns(self._engine)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def log(self, state: Mapping[str, Any]) -> str:
        response = state.get("final_response", {}) or {}
        handoff = state.get("hr_handoff")
        answered = bool(response.get("answered", True))
        interaction = Interaction(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            session_id=state.get("session_id"),
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

    def record_hr_choice(self, interaction_id: str, *, ask_hr: bool) -> Interaction | None:
        with self._sessions.begin() as session:
            interaction = session.get(Interaction, interaction_id)
            if interaction is None:
                return None
            if interaction.answered:
                raise ValueError("Only unanswered questions can be sent to HR.")
            interaction.escalation_status = HR_REQUESTED if ask_hr else HR_DECLINED
            interaction.escalated = ask_hr
            interaction.escalated_at = datetime.now(timezone.utc) if ask_hr else None
            return interaction

    def list_session(self, session_id: str) -> list[Interaction]:
        with self._sessions() as session:
            query = (
                select(Interaction)
                .where(Interaction.session_id == session_id)
                .order_by(Interaction.created_at)
            )
            return list(session.scalars(query))

    def list_escalations(self, *, since: datetime | None = None) -> list[Interaction]:
        with self._sessions() as session:
            query = select(Interaction).where(Interaction.escalated.is_(True))
            if since is not None:
                query = query.where(Interaction.created_at >= since)
            return list(session.scalars(query.order_by(Interaction.created_at)))


def _add_missing_columns(engine: Any) -> None:
    # create_all only creates missing tables; add columns introduced after a database was created.
    existing = {column["name"] for column in inspect(engine).get_columns(Interaction.__tablename__)}
    with engine.begin() as connection:
        for column in Interaction.__table__.columns:
            if column.name not in existing:
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE {Interaction.__tablename__} ADD COLUMN "{column.name}" {column_type}')
                )


def _ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != f"{prefix}:memory:":
        Path(database_url[len(prefix):]).parent.mkdir(parents=True, exist_ok=True)
