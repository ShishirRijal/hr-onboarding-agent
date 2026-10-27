from __future__ import annotations

from agent.document_grading import grade_documents


class FakeGrader:
    def __init__(self, grade) -> None:
        self.grade = grade
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.schema(**self.grade)


CHUNKS = [
    {"chunk_id": "sick", "text": "NordTech pays sick leave from day 2 for 9 days.", "metadata": {}},
    {"chunk_id": "payday", "text": "Payday is the 25th.", "metadata": {}},
]


def test_grade_maps_section_numbers_to_ids_and_keeps_the_search_for_whats_missing() -> None:
    grader = FakeGrader({"relevant": [1, 1, 7], "coverage": "partial", "missing": "sick pay after day 9 Finland"})
    history = [{"question": "hi", "answer": "Hi Joonas!"}]

    grade = grade_documents("Do I get paid when sick?", CHUNKS, history=history, llm=grader)

    assert grade == {
        "relevant_chunk_ids": ["sick"],
        "coverage": "partial",
        "missing": "sick pay after day 9 Finland",
        "searched_again": False,
    }
    prompt = grader.calls[0][1][1]
    assert "Employee: hi" in prompt
    assert "[2] Source" in prompt


def test_complete_coverage_needs_at_least_one_relevant_section() -> None:
    grade = grade_documents("When do raises happen?", CHUNKS, llm=FakeGrader({"relevant": [], "coverage": "complete"}))

    assert grade["coverage"] == "none"
    assert grade["missing"] == "When do raises happen?"


def test_nothing_found_is_graded_without_a_model_call() -> None:
    grade = grade_documents("Can I bring my dog?", [], llm=None)

    assert grade["coverage"] == "none"
    assert grade["relevant_chunk_ids"] == []
