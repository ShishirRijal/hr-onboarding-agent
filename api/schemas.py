from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EmployeeContextIn(BaseModel):
    employee_country: str | None = None
    office_country: str | None = None
    office_location: str | None = None
    department: str | None = None
    role: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)
    employee_context: EmployeeContextIn | None = None


class Source(BaseModel):
    chunk_id: str
    source_doc: str | None = None
    source_file: str | None = None
    section_path: str | None = None
    page_number: int | None = None
    row_number: int | None = None
    score: float = 0.0


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


class SessionMessage(BaseModel):
    interaction_id: str
    created_at: datetime
    question: str
    answer: str
    sources: list[Source]
    confidence_score: float
    confidence_label: str
    answered: bool
    escalation_status: str | None = None
    escalation_reason: str | None = None
