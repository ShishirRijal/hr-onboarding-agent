from __future__ import annotations

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent.escalation import HR_REQUEST_DECLINED_MESSAGE, HR_REQUEST_SENT_MESSAGE
from interactions import HR_OFFERED

from .schemas import ChatRequest, ChatResponse, HRRequest, HRRequestResponse, SessionMessage, SourcePassage
from .streaming import sse, stream_agent

logger = logging.getLogger(__name__)

DEFAULT_WEB_ORIGINS = "http://localhost:3000"
DEFAULT_CORPUS_DIR = "corpus"
UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable."
SOURCE_GONE_MESSAGE = (
    "This source is no longer in the HR documents. Ask the question again to get current sources."
)


def create_app(*, graph: Any | None = None, store: Any | None = None, passages: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if graph is None or store is None or passages is None:
            app.state.graph, app.state.store, app.state.passages = _build_agent()
        else:
            app.state.graph, app.state.store, app.state.passages = graph, store, passages
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
        session_id, state = _initial_state(request, http_request.app.state.store)
        try:
            with http_request.app.state.graph_lock:
                result = http_request.app.state.graph.invoke(state)
        except Exception as exc:
            logger.exception("Agent failed to answer.")
            raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from exc
        return _chat_response(session_id, result)

    @app.post("/chat/stream")
    def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
        app_state = http_request.app.state
        session_id, state = _initial_state(request, app_state.store)

        def events() -> Iterator[str]:
            yield sse("session", {"session_id": session_id})
            try:
                with app_state.graph_lock:
                    for event, payload in stream_agent(app_state.graph, state):
                        if event == "done":
                            payload = _chat_response(session_id, payload).model_dump()
                        yield sse(event, payload)
            except Exception:
                logger.exception("Agent failed to answer.")
                yield sse("error", {"detail": UNAVAILABLE_MESSAGE})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            # no-transform stops compressing proxies (including Next's gzip) from buffering the stream.
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.post("/interactions/{interaction_id}/hr-request", response_model=HRRequestResponse)
    def hr_request(interaction_id: str, request: HRRequest, http_request: Request) -> HRRequestResponse:
        try:
            interaction = http_request.app.state.store.record_hr_choice(interaction_id, ask_hr=request.ask_hr)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="This question was already answered.") from exc
        if interaction is None:
            raise HTTPException(status_code=404, detail="Question not found.")
        return HRRequestResponse(
            interaction_id=interaction.id,
            escalation_status=interaction.escalation_status,
            message=HR_REQUEST_SENT_MESSAGE if request.ask_hr else HR_REQUEST_DECLINED_MESSAGE,
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
                answered=bool(interaction.answered),
                escalation_status=interaction.escalation_status,
                escalation_reason=interaction.escalation_reason,
            )
            for interaction in http_request.app.state.store.list_session(session_id)
        ]

    @app.get("/sources/{chunk_id}", response_model=SourcePassage)
    def source_passage(chunk_id: str, http_request: Request) -> SourcePassage:
        passage = http_request.app.state.passages.passage(chunk_id)
        if passage is None:
            raise HTTPException(status_code=404, detail=SOURCE_GONE_MESSAGE)
        return SourcePassage(
            chunk_id=passage.chunk_id,
            source_doc=passage.source_doc,
            source_file=passage.source_file,
            section_path=passage.section_path,
            content=passage.content,
            highlight_start=passage.highlight_start,
            highlight_end=passage.highlight_end,
        )

    return app


def _initial_state(request: ChatRequest, store: Any) -> tuple[str, dict[str, Any]]:
    session_id = request.session_id or str(uuid.uuid4())
    employee_context = request.employee_context.model_dump(exclude_none=True) if request.employee_context else {}
    # Earlier turns let the agent follow the conversation: names, follow-ups, "what about…".
    history = (
        [{"question": item.question, "answer": item.answer} for item in store.list_session(session_id)]
        if request.session_id
        else []
    )
    return session_id, {
        "session_id": session_id,
        "question": request.message,
        "employee_context": employee_context,
        "history": history,
        "retrieval_config": {"apply_reranker": _env_flag("USE_COHERE_RERANK")},
    }


def _chat_response(session_id: str, result: dict[str, Any]) -> ChatResponse:
    response = result.get("final_response", {})
    handoff = result.get("hr_handoff")
    answered = bool(response.get("answered", False))
    return ChatResponse(
        session_id=session_id,
        interaction_id=result.get("interaction_id"),
        answer=response.get("text", ""),
        sources=response.get("sources", []),
        confidence_score=result.get("confidence_score", 0.0),
        confidence_label=result.get("confidence_label", "low"),
        answered=answered,
        escalation_status=None if answered else HR_OFFERED,
        escalation_reason=handoff.get("reason") if handoff else None,
    )


def _build_agent() -> tuple[Any, Any, Any]:
    from qdrant_client import QdrantClient

    from agent import build_retrieval_graph
    from interactions import InteractionStore
    from retrieval import DEFAULT_COLLECTION_NAME, build_retrieval_engine
    from retrieval.passages import PassageLibrary

    load_dotenv()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
    engine = build_retrieval_engine(
        client,
        collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION_NAME),
    )
    store = InteractionStore()
    passages = PassageLibrary(engine.bm25_index.chunks, Path(os.getenv("CORPUS_DIR", DEFAULT_CORPUS_DIR)))
    return build_retrieval_graph(engine, interaction_logger=store.log), store, passages


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


app = create_app()
