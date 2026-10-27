import pytest


@pytest.fixture(autouse=True)
def _default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # The API loads .env, which would otherwise switch these on for every test when they're
    # on locally. load_dotenv never overrides a variable that's already set.
    monkeypatch.setenv("USE_COHERE_RERANK", "false")
    monkeypatch.setenv("CORRECTIVE_SEARCH", "false")
    # Empty means no monthly limit; tests that need one set it.
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "")
    # Tests never send traces, whatever keys .env has.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
