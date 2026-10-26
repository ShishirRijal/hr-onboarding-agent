from __future__ import annotations

import re

# Everyday words employees use that the policies never do, mapped to the policy's own
# term. Searching "vacation days" alone misses the annual leave sections entirely.
POLICY_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), term)
    for pattern, term in (
        (r"\bvacations?\b|\bdays? off\b|\btime off\b|\bpto\b|(?<!public )(?<!bank )(?<!national )\bholidays?\b",
         "annual leave"),
        (r"\bsick days?\b|\boff sick\b|\bcall(?:ing)? in sick\b|\bill\b", "sick leave"),
        (r"\bpay ?day\b|\bget paid\b|\bpay ?checks?\b|\bpay ?cheques?\b", "salary payment"),
        (r"\brefunds?\b|\bmoney back\b|\bpaid back\b|\bpay me back\b", "reimbursement"),
        (r"\bwork(?:ing)? from home\b|\bwfh\b", "remote work"),
        (r"\bmaternity\b|\bpaternity\b", "parental leave"),
    )
)


def add_policy_terms(query: str) -> str:
    """Appends the policy's own words for any everyday words in the query, so both keyword
    and semantic search can find the right sections."""
    terms = [term for pattern, term in POLICY_TERMS if pattern.search(query) and term not in query.lower()]
    return f"{query} ({', '.join(terms)})" if terms else query
