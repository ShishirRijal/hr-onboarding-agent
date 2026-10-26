from __future__ import annotations

from .state import ConfidenceDebug, HREscalation, RetrievalState

HR_CONTACT_EMAIL = "hr@nordtech.ee"
ESCALATION_MESSAGE = (
    "I can't answer this reliably from the HR knowledge base, so I've logged your question for "
    f"the HR team. You can also contact them directly at {HR_CONTACT_EMAIL}."
)


def build_hr_escalation(state: RetrievalState) -> HREscalation:
    generated_answer = state.get("generated_answer", {"text": "", "sources": []})

    return {
        "reason": _escalation_reason(state.get("confidence_debug", {})),
        "contact": HR_CONTACT_EMAIL,
        "question": str(state.get("question", "")).strip(),
        "employee_context": state.get("employee_context", {}),
        "confidence_score": float(state.get("confidence_score", 0.0)),
        "confidence_label": str(state.get("confidence_label", "low")),
        "draft_answer": str(generated_answer.get("text", "")).strip(),
        "candidate_sources": list(generated_answer.get("sources", [])),
    }


def _escalation_reason(confidence_debug: ConfidenceDebug) -> str:
    if not confidence_debug.get("retrieved_count"):
        return "no_documents_found"
    if confidence_debug.get("answer_declined"):
        return "answer_declined"
    if not confidence_debug.get("has_answer"):
        return "no_answer_generated"
    if not confidence_debug.get("has_sources"):
        return "no_sources"
    return "low_confidence"
