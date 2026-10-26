from __future__ import annotations

from retrieval.vocabulary import add_policy_terms


def test_everyday_words_get_the_policy_term() -> None:
    assert add_policy_terms("How many vacation days do I get?") == "How many vacation days do I get? (annual leave)"
    assert add_policy_terms("when is payday?") == "when is payday? (salary payment)"
    assert add_policy_terms("Can I get a refund for a taxi when I'm off sick?") == (
        "Can I get a refund for a taxi when I'm off sick? (sick leave, reimbursement)"
    )


def test_public_holidays_are_not_treated_as_annual_leave() -> None:
    assert add_policy_terms("Which public holidays does Estonia have?") == "Which public holidays does Estonia have?"
    assert add_policy_terms("How many holidays do I get?") == "How many holidays do I get? (annual leave)"


def test_queries_already_in_policy_words_are_unchanged() -> None:
    assert add_policy_terms("How much annual leave do I get?") == "How much annual leave do I get?"
    assert add_policy_terms("Is my laptop encrypted?") == "Is my laptop encrypted?"
