from __future__ import annotations

from qdrant_client.http.models import MatchAny, MatchValue

from retrieval.models import RetrievalFilters


def test_country_filter_keeps_company_wide_chunks() -> None:
    filters = RetrievalFilters(country="Estonia")

    assert filters.matches({"country": "Estonia"})
    assert filters.matches({"country": "All"})
    assert not filters.matches({"country": "Portugal"})


def test_explicit_all_country_filter_matches_only_company_wide_chunks() -> None:
    filters = RetrievalFilters(country="All")

    assert filters.matches({"country": "All"})
    assert not filters.matches({"country": "Estonia"})


def test_non_country_filters_still_match_exactly() -> None:
    filters = RetrievalFilters(country="Finland", source_doc="leave_policy")

    assert filters.matches({"country": "All", "source_doc": "leave_policy"})
    assert not filters.matches({"country": "All", "source_doc": "All"})


def test_qdrant_country_filter_matches_country_or_all() -> None:
    qdrant_filter = RetrievalFilters(country="Portugal", doc_type="policy").to_qdrant_filter()

    conditions = {condition.key: condition.match for condition in qdrant_filter.must}
    assert conditions["country"] == MatchAny(any=["Portugal", "All"])
    assert conditions["doc_type"] == MatchValue(value="policy")
