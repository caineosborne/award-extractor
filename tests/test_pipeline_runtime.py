from src.common import pipeline_runtime


def test_build_openai_client_uses_reliable_pipeline_defaults(monkeypatch):
    captured_arguments = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_arguments.update(kwargs)

    monkeypatch.setattr(pipeline_runtime, "OpenAI", FakeOpenAI)
    monkeypatch.delenv("OPENAI_MAX_RETRIES", raising=False)
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)

    pipeline_runtime.build_openai_client(api_key="test-key")

    assert captured_arguments == {
        "api_key": "test-key",
        "base_url": None,
        "max_retries": 5,
        "timeout": 600.0,
    }


def test_build_openai_client_allows_retry_settings_to_be_overridden(monkeypatch):
    captured_arguments = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_arguments.update(kwargs)

    monkeypatch.setattr(pipeline_runtime, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "8")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "900")

    pipeline_runtime.build_openai_client(
        api_key="test-key",
        base_url="https://example.test/v1",
    )

    assert captured_arguments == {
        "api_key": "test-key",
        "base_url": "https://example.test/v1",
        "max_retries": 8,
        "timeout": 900.0,
    }
