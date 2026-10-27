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


class FeedbackRequest(BaseModel):
    # None takes a rating back.
    rating: Literal["up", "down"] | None
    # What was wrong, with a thumbs down.
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    interaction_id: str
    feedback: str | None
    feedback_comment: str | None


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
    feedback: str | None = None
    feedback_comment: str | None = None


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


# Matches interactions.store.REVIEW_FILTERS.
ReviewFilter = Literal["all", "unhelpful", "helpful", "not_answered", "reviewed"]


class ReviewItem(BaseModel):
    """A logged question in the answer review. Anonymous: only the asker's country is shown."""

    interaction_id: str
    asked_at: UtcDatetime
    question: str
    answer: str
    answered: bool
    # Greetings and thanks, answered without the documents.
    small_talk: bool
    country: str | None = None
    escalation_status: str | None = None
    feedback: str | None = None
    feedback_comment: str | None = None
    review_verdict: str | None = None
    reviewed_by: str | None = None
    reviewed_at: UtcDatetime | None = None


class ReviewPage(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewDetail(ReviewItem):
    sources: list[Source]
    confidence_label: str
    # Why the assistant couldn't answer, for questions it didn't.
    reason: str | None = None
    # HR's reply from the inbox, when the employee sent the question to HR.
    hr_answer: str | None = None
    review_answer: str | None = None
    earlier_turns: list[ConversationTurnOut]


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "corrected"]
    # The answer HR would have given, with "corrected".
    answer: str | None = Field(default=None, max_length=5000)


class TopicCount(BaseModel):
    topic: str
    count: int


class HROverview(BaseModel):
    open_questions: int
    answered_this_week: int
    # Answers employees marked unhelpful that HR hasn't reviewed yet.
    unhelpful_to_review: int
    common_topics: list[TopicCount]
    topics_since: UtcDatetime
