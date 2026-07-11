"""LLM validation of generated calculator Python against its runtime contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from src.common.llm_io import extract_response_text
from src.common.pipeline_runtime import build_openai_client, load_openai_environment
from src.common.prompt_logging import configure_prompt_log, log_llm_error, log_llm_prompt, log_llm_response
from src.common.output_paths import write_text_output


DEFAULT_MODEL = "gpt-5.6-luna"


class CalculatorRulesetValidationError(RuntimeError):
    """Raised when calculator Python validation cannot be completed."""


def _response_schema() -> dict[str, Any]:
    finding = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "severity": {"type": "string", "enum": ["green", "amber", "red"]},
            "calculator_item": {"type": "string"},
            "category": {
                "type": "string",
                "enum": ["syntax", "contract", "internal_consistency", "runtime_behaviour"],
            },
            "finding": {"type": "string"},
            "recommendation": {"type": "string"},
        },
        "required": [
            "severity",
            "calculator_item",
            "category",
            "finding",
            "recommendation",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_status": {"type": "string", "enum": ["green", "amber", "red"]},
            "summary": {"type": "string"},
            "findings": {"type": "array", "items": finding},
        },
        "required": ["overall_status", "summary", "findings"],
    }


def _messages(award_code: str, calculator_python: str) -> list[dict[str, str]]:
    instructions = """
Validate only the supplied generated calculator Python. Do not compare it with an award,
enterprise agreement, PDF, parser, classifications, pseudocode, or reviewed ruleset.
Do not modify the calculator. Report findings only.

Assess whether the Python is valid and internally sensible for this calculator contract:
- Ordinary-hours limits and overtime rates must be numeric when live. Every calculator
  class attribute set to None must be reported as at least amber because the calculator
  has no live value for that field, even where None may be an intentional limitation.
- APPLY_SPAN_OVERTIME requires a numeric SPAN_OVERTIME_HOUR.
- TWO_TIER_OVERTIME requires an extended rate, numeric threshold and at least one day.
- WEEKEND_RULES uses worker type first (day/shift), then Saturday/Sunday. An overtime
  weekend entry uses is_overtime true. An ordinary weekend penalty entry uses
  is_overtime false with a numeric penalty_rate.
- PENALTIES entries use shift_based or time_based. Shift-based entries use start, end,
  or duration basis. Time windows use 24-hour values and may cross midnight only when
  end is lower than start. Rates are additional decimal loadings, not total pay rates.
- A penalty description and its configured basis/window should make common-sense sense.
  For example, an afternoon or evening penalty spanning 6:00 am to 10:00 pm is suspicious.
- GAP_PENALTY_HOURS and GAP_PENALTY_RATE must be numeric together or both absent.
- Public-holiday treatment is not supported as a first-class runtime input, so flag any
  purported automatic public-holiday calculation as red.

Use red for invalid or unsafe runtime behaviour, amber for a likely inconsistency or
known limitation, and green only for a confirmed coherent configuration. Be concise.
""".strip()
    payload = {
        "award_code": award_code,
        "calculator_python": calculator_python,
    }
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": json.dumps(payload, indent=2)},
    ]


def _markdown_report(report: dict[str, Any], award_code: str) -> str:
    lines = [
        f"# Calculator validation — {award_code}",
        "",
        f"**Overall status:** {str(report.get('overall_status', 'unknown')).upper()}",
        "",
        str(report.get("summary", "")).strip(),
        "",
        "## Findings",
        "",
    ]
    findings = report.get("findings", [])
    if not isinstance(findings, list) or not findings:
        lines.append("No findings were returned.")
        return "\n".join(lines) + "\n"

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        lines.extend(
            [
                f"### {str(finding.get('severity', 'unknown')).upper()} — {finding.get('calculator_item', '')}",
                str(finding.get("finding", "")).strip(),
                "",
                f"**Category:** {str(finding.get('category', '')).replace('_', ' ')}",
                f"**Recommendation:** {str(finding.get('recommendation', '')).strip()}",
                "",
            ]
        )
    return "\n".join(lines)


def _calculator_attributes_set_to_none(parsed_module: ast.Module) -> list[str]:
    """Return calculator class attributes that have no live configured value."""
    none_attributes: list[str] = []

    for node in parsed_module.body:
        if not isinstance(node, ast.ClassDef):
            continue

        for class_statement in node.body:
            if not isinstance(class_statement, ast.Assign):
                continue
            if not isinstance(class_statement.value, ast.Constant):
                continue
            if class_statement.value.value is not None:
                continue

            for target in class_statement.targets:
                if isinstance(target, ast.Name):
                    none_attributes.append(target.id)

    return none_attributes


def _add_none_value_findings(
    report: dict[str, Any],
    none_attributes: list[str],
) -> None:
    """Ensure every None calculator attribute is visible as an amber finding."""
    findings = report.get("findings")
    if not isinstance(findings, list):
        findings = []
        report["findings"] = findings

    existing_items = {
        str(finding.get("calculator_item") or "").strip()
        for finding in findings
        if isinstance(finding, dict)
    }

    for attribute_name in none_attributes:
        if attribute_name in existing_items:
            continue
        findings.append(
            {
                "severity": "amber",
                "calculator_item": attribute_name,
                "category": "contract",
                "finding": (
                    f"{attribute_name} is set to None, so the calculator has no live "
                    "value for this field."
                ),
                "recommendation": (
                    "Confirm that the missing value is intentional or enter a supported "
                    "numeric/configured value before relying on this field."
                ),
            }
        )

    if none_attributes and report.get("overall_status") == "green":
        report["overall_status"] = "amber"
        existing_summary = str(report.get("summary") or "").strip()
        report["summary"] = (
            existing_summary
            + " One or more calculator attributes are set to None and require review."
        ).strip()


def validate_calculator_python(
    *,
    award_code: str,
    calculator_python_path: Path,
    validation_json_path: Path,
    validation_markdown_path: Path,
    model: str = DEFAULT_MODEL,
    client: Any | None = None,
) -> dict[str, Any]:
    """Validate one calculator artifact and write read-only validation reports."""
    if not calculator_python_path.exists():
        raise CalculatorRulesetValidationError(
            f"Calculator Python was not found: {calculator_python_path}"
        )

    calculator_python = calculator_python_path.read_text(encoding="utf-8")
    try:
        parsed_module = ast.parse(calculator_python)
    except SyntaxError as exc:
        raise CalculatorRulesetValidationError(
            f"Calculator Python has invalid syntax: {exc}"
        ) from exc

    messages = _messages(award_code, calculator_python)
    log_llm_prompt(f"6.2 Calculator Validation - {award_code}", messages)
    if client is None:
        load_openai_environment(
            env_path=Path(__file__).resolve().parents[2] / ".env",
            error_type=CalculatorRulesetValidationError,
        )
    active_client = client or build_openai_client()

    try:
        response = active_client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "medium"},
            max_output_tokens=8000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "calculator_ruleset_validation",
                    "schema": _response_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        log_llm_error(f"6.2 Calculator Validation Error - {award_code}", exc)
        raise CalculatorRulesetValidationError(f"OpenAI calculator validation failed: {exc}") from exc

    output_text = extract_response_text(response)
    log_llm_response(f"6.2 Calculator Validation Response - {award_code}", response, output_text)
    if not output_text:
        raise CalculatorRulesetValidationError("Calculator validation returned no text.")

    try:
        report = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise CalculatorRulesetValidationError("Calculator validation returned invalid JSON.") from exc
    if not isinstance(report, dict):
        raise CalculatorRulesetValidationError("Calculator validation must return a JSON object.")

    _add_none_value_findings(
        report,
        _calculator_attributes_set_to_none(parsed_module),
    )

    write_text_output(validation_json_path, json.dumps(report, indent=2))
    write_text_output(validation_markdown_path, _markdown_report(report, award_code))
    return report
