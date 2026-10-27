from __future__ import annotations

from agent.citations import has_citations, number_citations, strip_citations


def _chunk(chunk_id: str, source_file: str, section: str) -> dict:
    return {"chunk_id": chunk_id, "metadata": {"source_file": source_file, "section_path": section}, "score": 0.5}


CHUNKS = [
    _chunk("leave-1", "leave_absence_policy.md", "3. Finland"),
    _chunk("it-7", "it_policy.md", "7. Equipment Ordering"),
    _chunk("leave-2", "leave_absence_policy.md", "3. Finland"),
]


def test_citations_are_numbered_in_the_order_the_answer_first_uses_them() -> None:
    text, sources = number_citations("Monitors go through IT [2]. Sick pay is from day 1 [1].", CHUNKS)

    assert text == "Monitors go through IT[1]. Sick pay is from day 1[2]."
    assert [source["chunk_id"] for source in sources] == ["it-7", "leave-1"]


def test_a_source_keeps_its_number_every_time_it_is_cited() -> None:
    # Sections 1 and 3 are two passages from the same section of the same document.
    text, sources = number_citations("Day one [1]. Kela from day 10 [3]. Both [1, 3]. Again [1][3].", CHUNKS)

    assert text == "Day one[1]. Kela from day 10[1]. Both[1]. Again[1]."
    assert [source["chunk_id"] for source in sources] == ["leave-1"]


def test_citations_to_sections_that_were_not_given_are_dropped() -> None:
    text, sources = number_citations("Monitors go through IT [9] and [2].", CHUNKS)

    assert text == "Monitors go through IT and[1]."
    assert [source["chunk_id"] for source in sources] == ["it-7"]


def test_markdown_links_are_not_citations() -> None:
    text, sources = number_citations("Open the [portal](https://hr.nordtech.test) [1].", CHUNKS)

    assert text == "Open the [portal](https://hr.nordtech.test)[1]."
    assert len(sources) == 1


def test_an_answer_without_citations_is_left_as_it_is() -> None:
    assert number_citations("You get 25 days.", CHUNKS) == ("You get 25 days.", [])
    assert not has_citations("You get 25 days.")


def test_strip_citations_removes_the_numbers() -> None:
    assert strip_citations("You get 25 days [1]. Kela pays[2][3].") == "You get 25 days. Kela pays."
