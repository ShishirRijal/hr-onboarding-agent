from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///data/interactions.db"


class Base(DeclarativeBase):
    pass


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    escalated: Mapped[bool] = mapped_column(Boolean, index=True)
    escalation_reason: Mapped[str | None] = mapped_column(String(64))
    confidence_score: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(16))
    employee_context: Mapped[dict[str, Any]] = mapped_column(JSON)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    escalation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    debug: Mapped[dict[str, Any]] = mapped_column(JSON)


class InteractionStore:
    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or os.getenv("INTERACTIONS_DATABASE_URL", DEFAULT_DATABASE_URL)
        _ensure_sqlite_directory(url)
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def log(self, state: Mapping[str, Any]) -> str:
        response = state.get("final_response", {}) or {}
        escalation = state.get("escalation")
        interaction = Interaction(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            session_id=state.get("session_id"),
            question=str(state.get("question", "")).strip(),
            answer=str(response.get("text", "")),
            escalated=bool(response.get("escalated", False)),
            escalation_reason=escalation.get("reason") if escalation else None,
            confidence_score=float(state.get("confidence_score", 0.0)),
            confidence_label=str(state.get("confidence_label", "low")),
            employee_context=dict(state.get("employee_context", {}) or {}),
            sources=list(response.get("sources", []) or []),
            escalation=dict(escalation) if escalation else None,
            debug={
                "retrieval": state.get("retrieval_debug", {}),
                "confidence": state.get("confidence_debug", {}),
            },
        )

        with self._sessions.begin() as session:
            session.add(interaction)
        return interaction.id

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


def _ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != f"{prefix}:memory:":
        Path(database_url[len(prefix):]).parent.mkdir(parents=True, exist_ok=True)
