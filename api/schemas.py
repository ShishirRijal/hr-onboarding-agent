from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from interactions.store import as_utc

# Times are stored in UTC, but SQLite returns them without a zone; marking them as UTC keeps
# browsers from reading them as local time.
UtcDatetime = Annotated[datetime, AfterValidator(as_utc)]


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    role: str
    job_title: str
    department: str
    office: str
    country: str
    manager_name: str | None = None
    start_date: date
    pronouns: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


class Source(BaseModel):
    chunk_id: str
    source_doc: str | None = None
    source_file: str | None = None
    section_path: str | None = None
    page_number: int | None = None
    row_number: int | None = None
    score: float = 0.0


class SourcePassage(BaseModel):
    chunk_id: str
    source_doc: str | None = None
    source_file: str | None = None
    section_path: str | None = None
    content: str
    highlight_start: int | None = None
    highlight_end: int | None = None


class ChatResponse(BaseModel):
    session_id: str
    interaction_id: str | None
    answer: str
    sources: list[Source]
    confidence_score: float
    confidence_label: str
    answered: bool
    escalation_status: str | None = None
    escalation_reason: str | None = None


class HRRequest(BaseModel):
    ask_hr: bool


class HRRequestResponse(BaseModel):
    interaction_id: str
    escalation_status: str
    message: str


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    updated_at: UtcDatetime
    unread_hr_replies: int


class SessionMessage(BaseModel):
    interaction_id: str
    created_at: UtcDatetime
    question: str
    answer: str
    sources: list[Source]
    confidence_score: float
    confidence_label: str
    answered: bool
    escalation_status: str | None = None
    escalation_reason: str | None = None
    hr_answer: str | None = None
    hr_answered_by: str | None = None
    hr_answered_at: UtcDatetime | None = None


class Asker(BaseModel):
    name: str
    email: str | None = None
    job_title: str | None = None
    department: str | None = None
    office: str | None = None
    country: str | None = None


class ConversationTurnOut(BaseModel):
    question: str
    answer: str


class HRQuestion(BaseModel):
    interaction_id: str
    question: str
    asked_at: UtcDatetime
    asker: Asker
    status: str
    reason: str
    hr_answer: str | None = None
    hr_answered_by: str | None = None
    hr_answered_at: UtcDatetime | None = None
    # Who the answer was added to the knowledge base for: a country, or "All".
    hr_answer_country: str | None = None


class HRQuestionDetail(HRQuestion):
    documents_checked: list[str]
    earlier_turns: list[ConversationTurnOut]


class HRAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    # "everyone": the answer is added to the knowledge base for all employees;
    # "country": only for employees in the asker's country.
    applies_to: Literal["everyone", "country"]


class TopicCount(BaseModel):
    topic: str
    count: int


class HROverview(BaseModel):
    open_questions: int
    answered_this_week: int
    common_topics: list[TopicCount]
    topics_since: UtcDatetime
