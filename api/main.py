from __future__ import annotations

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .schemas import ChatRequest, ChatResponse, SessionMessage

logger = logging.getLogger(__name__)

DEFAULT_WEB_ORIGINS = "http://localhost:3000"


def create_app(*, graph: Any | None = None, store: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if graph is None or store is None:
            app.state.graph, app.state.store = _build_agent()
        else:
            app.state.graph, app.state.store = graph, store
        # The embedding model is not safe to call from several threads at once,
        # so requests run the graph one at a time.
        app.state.graph_lock = threading.Lock()
        yield

    app = FastAPI(title="NordTech HR Onboarding Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("WEB_ORIGINS", DEFAULT_WEB_ORIGINS).split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
        session_id = request.session_id or str(uuid.uuid4())
        employee_context = (
            request.employee_context.model_dump(exclude_none=True) if request.employee_context else {}
        )
        state = {
            "session_id": session_id,
            "question": request.message,
            "employee_context": employee_context,
            "retrieval_config": {"apply_reranker": _env_flag("USE_COHERE_RERANK")},
        }

        try:
            with http_request.app.state.graph_lock:
                result = http_request.app.state.graph.invoke(state)
        except Exception as exc:
            logger.exception("Agent failed to answer.")
            raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable.") from exc

        response = result.get("final_response", {})
        escalation = result.get("escalation")
        return ChatResponse(
            session_id=session_id,
            interaction_id=result.get("interaction_id"),
            answer=response.get("text", ""),
            sources=response.get("sources", []),
            confidence_score=result.get("confidence_score", 0.0),
            confidence_label=result.get("confidence_label", "low"),
            escalated=response.get("escalated", False),
            escalation_reason=escalation.get("reason") if escalation else None,
        )

    @app.get("/sessions/{session_id}/messages", response_model=list[SessionMessage])
    def session_messages(session_id: str, http_request: Request) -> list[SessionMessage]:
        return [
            SessionMessage(
                interaction_id=interaction.id,
                created_at=interaction.created_at,
                question=interaction.question,
                answer=interaction.answer,
                sources=interaction.sources,
                confidence_score=interaction.confidence_score,
                confidence_label=interaction.confidence_label,
                escalated=interaction.escalated,
                escalation_reason=interaction.escalation_reason,
            )
            for interaction in http_request.app.state.store.list_session(session_id)
        ]

    return app


def _build_agent() -> tuple[Any, Any]:
    from qdrant_client import QdrantClient

    from agent import build_retrieval_graph
    from interactions import InteractionStore
    from retrieval import DEFAULT_COLLECTION_NAME, build_retrieval_engine

    load_dotenv()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
    engine = build_retrieval_engine(
        client,
        collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION_NAME),
    )
    store = InteractionStore()
    return build_retrieval_graph(engine, interaction_logger=store.log), store


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


app = create_app()
