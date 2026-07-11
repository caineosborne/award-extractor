"""Tests for LLM response audit logging."""

from src.common.prompt_logging import log_llm_error, log_llm_prompt, log_llm_response


class FakeResponse:
    """Represent a model response with a serialisable SDK-style payload."""

    def model_dump_json(self, indent: int) -> str:
        assert indent == 2
        return '{\n  "status": "incomplete",\n  "output": []\n}'


def test_log_llm_response_records_raw_payload_and_extracted_text(tmp_path):
    log_path = tmp_path / "award.log"

    log_llm_response(
        "3.2 Evaluator Response - Attempt 1",
        FakeResponse(),
        "",
        log_path=log_path,
    )

    log_text = log_path.read_text(encoding="utf-8")
    assert "3.2 Evaluator Response - Attempt 1" in log_text
    assert "<no text extracted>" in log_text
    assert '"status": "incomplete"' in log_text


def test_unconfigured_logging_does_not_create_a_fallback_log(monkeypatch):
    monkeypatch.setattr("src.common.prompt_logging._active_prompt_log_path", None)

    log_llm_prompt("Prompt", [])
    log_llm_response("Response", FakeResponse(), "")
    log_llm_error("Error", RuntimeError("request failed"))


def test_log_llm_error_records_the_error_type_and_message(tmp_path):
    log_path = tmp_path / "award.log"

    log_llm_error(
        "6.1 Calculator Rules Questionnaire Error",
        RuntimeError("request failed"),
        log_path,
    )

    log_text = log_path.read_text(encoding="utf-8")
    assert "6.1 Calculator Rules Questionnaire Error" in log_text
    assert "RuntimeError: request failed" in log_text
