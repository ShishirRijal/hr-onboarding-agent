import pytest


@pytest.fixture(autouse=True)
def _default_retrieval_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    # The API loads .env, which would otherwise switch these on for every test when they're
    # on locally. load_dotenv never overrides a variable that's already set.
    monkeypatch.setenv("USE_COHERE_RERANK", "false")
    monkeypatch.setenv("CORRECTIVE_SEARCH", "false")
