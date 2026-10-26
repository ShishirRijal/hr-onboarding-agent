from __future__ import annotations

from .answering import DEFAULT_ANSWER_MODEL, generate_grounded_answer
from .conversation import MESSAGE_CHAT, MESSAGE_HR, generate_chat_reply, route_message
from .escalation import (
    HR_CONTACT_EMAIL,
    HR_REQUEST_DECLINED_MESSAGE,
    HR_REQUEST_SENT_MESSAGE,
    NOT_FOUND_MESSAGE,
    build_hr_handoff,
)
from .retrieval_graph import build_retrieval_graph
from .state import (
    ConversationTurn,
    EmployeeContext,
    FinalResponse,
    HRHandoff,
    RetrievedChunkPayload,
    RetrievalConfig,
    RetrievalOverrides,
    RetrievalState,
)

__all__ = [
    "DEFAULT_ANSWER_MODEL",
    "ConversationTurn",
    "EmployeeContext",
    "FinalResponse",
    "HRHandoff",
    "HR_CONTACT_EMAIL",
    "HR_REQUEST_DECLINED_MESSAGE",
    "HR_REQUEST_SENT_MESSAGE",
    "MESSAGE_CHAT",
    "MESSAGE_HR",
    "NOT_FOUND_MESSAGE",
    "RetrievedChunkPayload",
    "RetrievalConfig",
    "RetrievalOverrides",
    "RetrievalState",
    "build_hr_handoff",
    "build_retrieval_graph",
    "generate_chat_reply",
    "generate_grounded_answer",
    "route_message",
]
