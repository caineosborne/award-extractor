"""Step 3.1 stage 2: request one expert draft from the model."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
)
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET, overtime_ruleset_config
from src.common.pipeline_runtime import load_openai_environment
from src.prompts.step_3_1_generate_ruleset import build_interpretation_messages

from .schema import DEFAULT_MODEL


def load_environment(env_path: Path | str = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load and validate the OpenAI environment used by step 3.1."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 3.1 client."""
    load_environment()
    return OpenAI()


def resolve_models(
    *,
    model: str | None,
    comparison_model: str | None,
) -> tuple[str, str]:
    """Resolve the expert-drafting and comparison models for step 3.1."""
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    selected_comparison_model = comparison_model or os.getenv(
        "OVERTIME_INTERPRETATION_COMPARISON_MODEL",
        selected_model,
    )
    return selected_model, selected_comparison_model


def interpretation_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from one expert draft."""
    from src.common.overtime_rules import (
        ALLOWED_EMPLOYEE_COHORTS,
        ALLOWED_WORK_ARRANGEMENTS,
    )

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rules": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rule_id": {"type": "string"},
                        "section_heading": {"type": "string"},
                        "employee_scope": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "employee_cohort": {
                            "type": "string",
                            "enum": list(ALLOWED_EMPLOYEE_COHORTS),
                        },
                        "work_arrangement": {
                            "type": "string",
                            "enum": list(ALLOWED_WORK_ARRANGEMENTS),
                        },
                        "other_scope_notes": {"type": "string"},
                        "clause_references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "rule_markdown": {"type": "string"},
                        "rule_plain_text": {"type": "string"},
                        "source_clause_numbers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "source_classifications": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                    },
                    "required": [
                        "rule_id",
                        "section_heading",
                        "employee_scope",
                        "employee_cohort",
                        "work_arrangement",
                        "other_scope_notes",
                        "clause_references",
                        "rule_markdown",
                        "rule_plain_text",
                        "source_clause_numbers",
                        "source_classifications",
                    ],
                },
            }
        },
        "required": ["rules"],
    }


def request_structured_interpretation_run(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> str:
    """Run one expert interpretation pass and return the raw model output text."""
    config = overtime_ruleset_config(ruleset_key)
    try:
        response = client.responses.create(
            model=model,
            input=build_interpretation_messages(
                ruleset_key,
                str(source_path),
                overtime_creation_clauses,
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": config.interpretation_schema_name,
                    "schema": interpretation_response_json_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI interpretation request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError("OpenAI response did not include output text.")

    return output_text
