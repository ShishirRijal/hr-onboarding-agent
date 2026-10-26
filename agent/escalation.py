from __future__ import annotations

from .state import AnswerSource, ConfidenceDebug, HRHandoff, RetrievalState

HR_CONTACT_EMAIL = "hr@nordtech.test"
NOT_FOUND_MESSAGE = (
    "I couldn't find an answer to this in NordTech's HR documents. "
    "Do you want me to ask the HR team about it?"
)
def hr_request_sent_message(email: str) -> str:
    return (
        "Your question goes to the HR team in their end-of-day summary, "
        f"and they'll reply to {email}. If it's urgent, email {HR_CONTACT_EMAIL}."
    )
HR_REQUEST_DECLINED_MESSAGE = "Okay, I won't send it to HR."


def build_hr_handoff(state: RetrievalState, candidate_sources: list[AnswerSource]) -> HRHandoff:
    """Everything HR needs to pick up the question, if the employee chooses to send it."""
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})

    return {
        "reason": _not_found_reason(state.get("confidence_debug", {})),
        "contact": HR_CONTACT_EMAIL,
        "question": str(state.get("question", "")).strip(),
        "employee_context": state.get("employee_context", {}),
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "confidence_label": str(state.get("confidence_label", "low")),
        "draft_answer": str(generated_answer.get("text", "")).strip(),
        "candidate_sources": candidate_sources,
    }


def _not_found_reason(confidence_debug: ConfidenceDebug) -> str:
    if not confidence_debug.get("retrieved_count"):
        return "no_documents_found"
    if confidence_debug.get("answer_declined"):
        return "answer_declined"
    if not confidence_debug.get("has_sources"):
        return "no_sources"
    return "low_confidence"
