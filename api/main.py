from __future__ import annotations

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from accounts import ROLE_HR, SESSION_LIFETIME, User, UserStore, seed_demo_users
from agent.escalation import HR_REQUEST_DECLINED_MESSAGE, hr_request_sent_message
from interactions import HR_ANSWERED, HR_OFFERED, HR_REQUESTED, Interaction
from interactions.digest import DEFAULT_DIGEST_TIMEZONE, DigestSettings, schedule_daily_digest
from interactions.inbox import common_topics, documents_checked, reason_text
from retrieval.settings import SHARED_COUNTRY

from .schemas import (
    Asker,
    ChatRequest,
    ChatResponse,
    ChatSessionSummary,
    ConversationTurnOut,
    HRAnswerRequest,
    HROverview,
    HRQuestion,
    HRQuestionDetail,
    HRRequest,
    HRRequestResponse,
    SessionMessage,
    SignInRequest,
    SourcePassage,
    TopicCount,
    UserProfile,
)
from .streaming import sse, stream_agent

logger = logging.getLogger(__name__)

DEFAULT_WEB_ORIGINS = "http://localhost:3000"
DEFAULT_CORPUS_DIR = "corpus"
SESSION_COOKIE = "nordtech_hr_session"
# How far back the HR overview looks for common unanswered topics.
TOPIC_WINDOW = timedelta(days=30)
UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable."
SOURCE_GONE_MESSAGE = (
    "This source is no longer in the HR documents. Ask the question again to get current sources."
)
SIGN_IN_REQUIRED = "Sign in to continue."
WRONG_CREDENTIALS = "That email and password don't match an account."
HR_ONLY = "Only the HR team can open this."
CHAT_NOT_FOUND = "Chat not found."
QUESTION_NOT_FOUND = "Question not found."
ALREADY_ANSWERED = "This question has already been answered."
COUNTRY_UNKNOWN = "The employee's country isn't known, so the answer can only be added for everyone."
KNOWLEDGE_UNAVAILABLE = "The answer couldn't be added to the knowledge base, so it wasn't sent. Try again."


def current_user(request: Request) -> User:
    """The signed-in user, from the session cookie. Every route but health and sign-in needs one."""
    token = request.cookies.get(SESSION_COOKIE)
    user = request.app.state.users.user_for_session(token) if token else None
    if user is None:
        # An expired or revoked cookie is cleared, so the browser stops sending it.
        headers = {"set-cookie": f'{SESSION_COOKIE}=""; Max-Age=0; Path=/; HttpOnly; SameSite=lax'} if token else None
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED, headers=headers)
    return user


def hr_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != ROLE_HR:
        raise HTTPException(status_code=403, detail=HR_ONLY)
    return user


CurrentUser = Annotated[User, Depends(current_user)]
HRUser = Annotated[User, Depends(hr_user)]


def create_app(
    *,
    graph: Any | None = None,
    store: Any | None = None,
    passages: Any | None = None,
    knowledge: Any | None = None,
    users: UserStore | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        digest_scheduler = None
        if graph is None or store is None or passages is None:
            app.state.graph, app.state.store, app.state.passages, app.state.knowledge = _build_agent()
            # Questions employees sent to HR go out in one email at the end of the day.
            digest_scheduler = schedule_daily_digest(app.state.store, DigestSettings.from_env())
        else:
            app.state.graph, app.state.store, app.state.passages = graph, store, passages
            app.state.knowledge = knowledge
        app.state.users = users if users is not None else _build_users()
        # The embedding model is not safe to call from several threads at once, so requests
        # run the graph, and add HR answers to the knowledge base, one at a time.
        app.state.graph_lock = threading.Lock()
        yield
        if digest_scheduler is not None:
            digest_scheduler.shutdown(wait=False)

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

    @app.post("/auth/sign-in", response_model=UserProfile)
    def sign_in(request: SignInRequest, http_request: Request, response: Response) -> UserProfile:
        users_store = http_request.app.state.users
        user = users_store.authenticate(request.email, request.password)
        if user is None:
            raise HTTPException(status_code=401, detail=WRONG_CREDENTIALS)
        # HttpOnly keeps the token away from page scripts; the web app proxies /api to this
        # API, so the cookie is first-party and SameSite=Lax is enough.
        response.set_cookie(
            SESSION_COOKIE,
            users_store.start_session(user.id),
            max_age=int(SESSION_LIFETIME.total_seconds()),
            httponly=True,
            samesite="lax",
            secure=_env_flag("SESSION_COOKIE_SECURE"),
        )
        return _profile(user)

    @app.post("/auth/sign-out", status_code=204, dependencies=[Depends(current_user)])
    def sign_out(http_request: Request) -> Response:
        # Deleting the session row revokes the cookie, even if the browser keeps a copy.
        http_request.app.state.users.end_session(http_request.cookies[SESSION_COOKIE])
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax")
        return response

    @app.get("/auth/me", response_model=UserProfile)
    def me(user: CurrentUser) -> UserProfile:
        return _profile(user)

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest, http_request: Request, user: CurrentUser) -> ChatResponse:
        session_id, state = _initial_state(request, user, http_request.app.state.store)
        try:
            with http_request.app.state.graph_lock:
                result = http_request.app.state.graph.invoke(state)
        except Exception as exc:
            logger.exception("Agent failed to answer.")
            raise HTTPException(status_code=503, detail=UNAVAILABLE_MESSAGE) from exc
        return _chat_response(session_id, result)

    @app.post("/chat/stream")
    def chat_stream(request: ChatRequest, http_request: Request, user: CurrentUser) -> StreamingResponse:
        app_state = http_request.app.state
        session_id, state = _initial_state(request, user, app_state.store)

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
    def hr_request(
        interaction_id: str, request: HRRequest, http_request: Request, user: CurrentUser
    ) -> HRRequestResponse:
        store = http_request.app.state.store
        asked = store.get(interaction_id)
        if asked is None or asked.user_id != user.id:
            raise HTTPException(status_code=404, detail=QUESTION_NOT_FOUND)
        try:
            interaction = store.record_hr_choice(
                interaction_id, ask_hr=request.ask_hr, name=user.name, email=user.email
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="This question was already answered.") from exc
        if interaction is None:
            raise HTTPException(status_code=404, detail=QUESTION_NOT_FOUND)
        return HRRequestResponse(
            interaction_id=interaction.id,
            escalation_status=interaction.escalation_status,
            message=hr_request_sent_message(user.email) if request.ask_hr else HR_REQUEST_DECLINED_MESSAGE,
        )

    @app.get("/sessions", response_model=list[ChatSessionSummary])
    def sessions(http_request: Request, user: CurrentUser) -> list[ChatSessionSummary]:
        return [
            ChatSessionSummary(
                session_id=chat.session_id,
                title=chat.title,
                updated_at=chat.updated_at,
                unread_hr_replies=chat.unread_hr_replies,
            )
            for chat in http_request.app.state.store.list_user_sessions(user.id)
        ]

    @app.get("/sessions/{session_id}/messages", response_model=list[SessionMessage])
    def session_messages(session_id: str, http_request: Request, user: CurrentUser) -> list[SessionMessage]:
        store = http_request.app.state.store
        if not _owns_session(store, session_id, user):
            raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND)
        messages = [
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
                hr_answer=interaction.hr_answer,
                hr_answered_by=interaction.hr_answered_by,
                hr_answered_at=interaction.hr_answered_at,
            )
            for interaction in store.list_session(session_id)
        ]
        # Opening the chat shows HR's replies, so they no longer count as unread.
        if any(message.hr_answered_at for message in messages):
            store.mark_hr_answers_read(session_id)
        return messages

    @app.get("/sources/{chunk_id}", response_model=SourcePassage, dependencies=[Depends(current_user)])
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

    @app.get("/hr/overview", response_model=HROverview, dependencies=[Depends(hr_user)])
    def hr_overview(http_request: Request) -> HROverview:
        store = http_request.app.state.store
        now = datetime.now(timezone.utc)
        topics_since = now - TOPIC_WINDOW
        return HROverview(
            open_questions=len(store.hr_questions(HR_REQUESTED)),
            answered_this_week=store.count_hr_answered_since(_week_start(now)),
            common_topics=[
                TopicCount(topic=topic, count=count)
                for topic, count in common_topics(store.unanswered_since(topics_since))
            ],
            topics_since=topics_since,
        )

    @app.get("/hr/questions", response_model=list[HRQuestion], dependencies=[Depends(hr_user)])
    def hr_questions(
        http_request: Request, status: Literal["requested", "answered"] = HR_REQUESTED
    ) -> list[HRQuestion]:
        app_state = http_request.app.state
        return [_hr_question(interaction, app_state.users) for interaction in app_state.store.hr_questions(status)]

    @app.get("/hr/questions/{interaction_id}", response_model=HRQuestionDetail, dependencies=[Depends(hr_user)])
    def hr_question(interaction_id: str, http_request: Request) -> HRQuestionDetail:
        app_state = http_request.app.state
        return _hr_question_detail(_sent_to_hr(app_state.store, interaction_id), app_state.store, app_state.users)

    @app.post("/hr/questions/{interaction_id}/answer", response_model=HRQuestionDetail)
    def answer_hr_question(
        interaction_id: str, request: HRAnswerRequest, http_request: Request, user: HRUser
    ) -> HRQuestionDetail:
        app_state = http_request.app.state
        answer = request.answer.strip()
        if not answer:
            raise HTTPException(status_code=422, detail="Write an answer before sending it.")

        # Held throughout: embedding the answer needs it, and it stops two people answering
        # the same question at once.
        with app_state.graph_lock:
            interaction = _sent_to_hr(app_state.store, interaction_id)
            if interaction.escalation_status != HR_REQUESTED:
                raise HTTPException(status_code=409, detail=ALREADY_ANSWERED)
            country = SHARED_COUNTRY if request.applies_to == "everyone" else _asker_country(interaction, app_state.users)
            if country is None:
                raise HTTPException(status_code=422, detail=COUNTRY_UNKNOWN)
            # Indexed first: if the knowledge base can't take it, nothing is sent and HR can retry.
            try:
                chunk_id = app_state.knowledge.add_hr_answer(
                    interaction_id=interaction.id, question=interaction.question, answer=answer, country=country
                )
            except Exception as exc:
                logger.exception("Couldn't add an HR answer to the knowledge base.")
                raise HTTPException(status_code=503, detail=KNOWLEDGE_UNAVAILABLE) from exc
            answered = app_state.store.record_hr_answer(
                interaction.id,
                answer=answer,
                answered_by=user.name,
                answered_by_id=user.id,
                country=country,
                chunk_id=chunk_id,
            )
        return _hr_question_detail(answered, app_state.store, app_state.users)

    return app


def _profile(user: User) -> UserProfile:
    return UserProfile.model_validate(user, from_attributes=True)


def _owns_session(store: Any, session_id: str, user: User) -> bool:
    # A chat with no questions yet is new, and becomes the user's with their first question.
    owners = store.session_owners(session_id)
    return not owners or owners == {user.id}


def _initial_state(request: ChatRequest, user: User, store: Any) -> tuple[str, dict[str, Any]]:
    session_id = request.session_id or str(uuid.uuid4())
    if request.session_id and not _owns_session(store, session_id, user):
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND)
    # Earlier turns let the agent follow the conversation: names, follow-ups, "what about…".
    # Where HR has since answered, their answer is the one to follow up on.
    history = (
        [{"question": item.question, "answer": item.hr_answer or item.answer} for item in store.list_session(session_id)]
        if request.session_id
        else []
    )
    return session_id, {
        "session_id": session_id,
        "user_id": user.id,
        "question": request.message,
        # Who is asking comes from their account, never from the browser.
        "employee_context": user.employee_context(),
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


def _sent_to_hr(store: Any, interaction_id: str) -> Interaction:
    interaction = store.get(interaction_id)
    if interaction is None or interaction.escalation_status not in (HR_REQUESTED, HR_ANSWERED):
        raise HTTPException(status_code=404, detail=QUESTION_NOT_FOUND)
    return interaction


def _asker(interaction: Interaction, users: UserStore) -> Asker:
    user = users.get(interaction.user_id)
    if user is None:
        return Asker(name=interaction.employee_name or "An employee", email=interaction.employee_email)
    return Asker(
        name=user.name,
        email=user.email,
        job_title=user.job_title,
        department=user.department,
        office=user.office,
        country=user.country,
    )


def _asker_country(interaction: Interaction, users: UserStore) -> str | None:
    user = users.get(interaction.user_id)
    if user is not None:
        return user.country
    context = interaction.employee_context or {}
    country = context.get("employee_country") or context.get("office_country")
    return country if country and country != "Remote" else None


def _hr_question(interaction: Interaction, users: UserStore) -> HRQuestion:
    return HRQuestion(
        interaction_id=interaction.id,
        question=interaction.question,
        asked_at=interaction.escalated_at or interaction.created_at,
        asker=_asker(interaction, users),
        status=interaction.escalation_status or HR_REQUESTED,
        reason=reason_text(interaction.escalation_reason),
        hr_answer=interaction.hr_answer,
        hr_answered_by=interaction.hr_answered_by,
        hr_answered_at=interaction.hr_answered_at,
        hr_answer_country=interaction.hr_answer_country,
    )


def _hr_question_detail(interaction: Interaction, store: Any, users: UserStore) -> HRQuestionDetail:
    earlier: list[ConversationTurnOut] = []
    if interaction.session_id:
        for turn in store.list_session(interaction.session_id):
            if turn.id == interaction.id:
                break
            earlier.append(ConversationTurnOut(question=turn.question, answer=turn.hr_answer or turn.answer))
    return HRQuestionDetail(
        **_hr_question(interaction, users).model_dump(),
        documents_checked=documents_checked(interaction.hr_handoff or {}),
        earlier_turns=earlier,
    )


def _week_start(now: datetime) -> datetime:
    """Monday 00:00 of this week in HR's time zone, in UTC."""
    local = now.astimezone(ZoneInfo(os.getenv("HR_DIGEST_TIMEZONE", DEFAULT_DIGEST_TIMEZONE)))
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def _build_agent() -> tuple[Any, Any, Any, Any]:
    from qdrant_client import QdrantClient

    from agent import build_retrieval_graph
    from interactions import InteractionStore
    from retrieval import DEFAULT_COLLECTION_NAME, build_retrieval_engine
    from retrieval.hr_answers import KnowledgeBase
    from retrieval.passages import PassageLibrary

    load_dotenv()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
    engine = build_retrieval_engine(
        client,
        collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION_NAME),
    )
    store = InteractionStore()
    passages = PassageLibrary(engine.bm25_index.chunks, Path(os.getenv("CORPUS_DIR", DEFAULT_CORPUS_DIR)))
    graph = build_retrieval_graph(engine, interaction_logger=store.log)
    return graph, store, passages, KnowledgeBase(engine, passages)


def _build_users() -> UserStore:
    load_dotenv()
    users = UserStore()
    # A new database gets the demo accounts, so there is always someone to sign in as.
    if users.count() == 0:
        added = seed_demo_users(users)
        logger.info("Added %d demo accounts; see the README for how to sign in.", len(added))
    return users


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


app = create_app()
