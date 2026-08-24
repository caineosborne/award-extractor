"""Tests for the read-only calculator Python validation."""

import json

from src.step_6_2_validate_calculator_ruleset.run import (
    validate_calculator_python,
)


class FakeResponse:
    """Provide one structured response without calling OpenAI."""

    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeResponses:
    """Record the validation request."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    """Provide the Responses API used by validation."""

    def __init__(self, response: FakeResponse) -> None:
        self.responses = FakeResponses(response)


def test_validation_uses_only_calculator_python_and_writes_read_only_reports(tmp_path):
    calculator_python_path = tmp_path / "rules.py"
    calculator_python_path.write_text("class ExampleRules:\n    RATE = 1.5\n", encoding="utf-8")

    response_data = {
        "overall_status": "green",
        "summary": "The calculator is internally coherent.",
        "findings": [
            {
                "severity": "green",
                "calculator_item": "STANDARD_OVERTIME_RATE",
                "category": "contract",
                "finding": "The calculator uses 150%.",
                "recommendation": "No change needed.",
            }
        ],
    }
    client = FakeClient(FakeResponse(json.dumps(response_data)))
    validation_json_path = tmp_path / "validation.json"
    validation_markdown_path = tmp_path / "validation.md"

    report = validate_calculator_python(
        award_code="ExampleEA",
        calculator_python_path=calculator_python_path,
        validation_json_path=validation_json_path,
        validation_markdown_path=validation_markdown_path,
        client=client,
    )

    assert report == response_data
    request_text = client.responses.calls[0]["input"][1]["content"]
    assert '"calculator_python": "class ExampleRules' in request_text
    assert "reviewed_rulesets" not in request_text
    assert client.responses.calls[0]["reasoning"] == {"effort": "medium"}
    assert json.loads(validation_json_path.read_text(encoding="utf-8")) == response_data
    assert "**Overall status:** GREEN" in validation_markdown_path.read_text(encoding="utf-8")


def test_validation_always_flags_none_calculator_attributes(tmp_path):
    calculator_python_path = tmp_path / "rules.py"
    calculator_python_path.write_text(
        "class ExampleRules:\n    ORDINARY_HOURS_LIMIT_WEEKLY = None\n",
        encoding="utf-8",
    )
    response_data = {
        "overall_status": "green",
        "summary": "No model concerns.",
        "findings": [],
    }
    client = FakeClient(FakeResponse(json.dumps(response_data)))

    report = validate_calculator_python(
        award_code="ExampleEA",
        calculator_python_path=calculator_python_path,
        validation_json_path=tmp_path / "validation.json",
        validation_markdown_path=tmp_path / "validation.md",
        client=client,
    )

    assert report["overall_status"] == "amber"
    assert report["findings"][0]["calculator_item"] == "ORDINARY_HOURS_LIMIT_WEEKLY"
    assert "set to None" in report["findings"][0]["finding"]
