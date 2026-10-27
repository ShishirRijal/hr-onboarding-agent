from __future__ import annotations

from agent.answer_check import check_answer, revision_feedback


class FakeReviewer:
    def __init__(self, decision) -> None:
        self.decision = decision
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.schema(**self.decision)


CHUNKS = [{"text": "Requests over €300 also need approval from Ott Rebane (Finance).", "metadata": {}}]


def test_check_answer_sends_question_sections_draft_and_conversation() -> None:
    reviewer = FakeReviewer(
        {"reasoning": "-", "verdict": "answered", "missing_details": ["Ott Rebane (Finance) approves over €300"]}
    )
    history = [{"question": "hi", "answer": "Hi Kertu!"}]

    check = check_answer("Who approves this?", CHUNKS, "Your manager.", history=history, llm=reviewer)

    assert check == {
        "answers_question": True,
        "unsupported_claims": [],
        "missing_details": ["Ott Rebane (Finance) approves over €300"],
        "revised": False,
    }
    prompt = reviewer.calls[0][1][1]
    assert "Employee: hi" in prompt
    assert "Question:\nWho approves this?" in prompt
    assert "Ott Rebane (Finance)" in prompt
    assert "Draft answer:\nYour manager." in prompt


def test_revision_feedback_lists_what_to_remove_and_add() -> None:
    feedback = revision_feedback(
        {
            "answers_question": True,
            "unsupported_claims": ["Keep your receipts."],
            "missing_details": ["Finance approves over €300"],
            "revised": False,
        }
    )

    assert "Remove or correct, because the sections don't support it: Keep your receipts." in feedback
    assert "Add, because the sections state it and it matters here: Finance approves over €300" in feedback


def test_a_draft_that_doesnt_answer_has_nothing_to_add() -> None:
    reviewer = FakeReviewer({"reasoning": "-", "verdict": "not_answered", "missing_details": ["contact HR"]})

    check = check_answer("Stock options on redundancy?", CHUNKS, "Case by case.", llm=reviewer)

    assert check["answers_question"] is False
    assert check["missing_details"] == []
