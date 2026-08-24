"""Step 3.2 stage 2: run the reviewer loop."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.model_call_budget import log_model_call_budget
from src.common.overtime_rules import ALLOWED_REVIEW_RECOMMENDATIONS, validate_review_feedback_artifact
from src.common.pipeline_runtime import build_openai_client, load_openai_environment
from src.common.prompt_logging import log_llm_prompt, log_llm_response
from src.prompts.step_3_2_review_ruleset import (
    build_evaluator_repair_messages,
    build_review_evaluator_messages,
)

from .schema import (
    DEFAULT_CREATOR_MAX_OUTPUT_TOKENS,
    DEFAULT_CREATOR_MODEL,
    DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS,
    EVALUATOR_MODEL,
    MAX_EVALUATOR_REPAIR_ATTEMPTS,
    OvertimeInterpretationReviewError,
)
from .step_1_load_inputs import Step3ReviewInputs


def load_client() -> OpenAI:
    """Load the OpenAI environment and return a client for step 3.2."""
    load_openai_environment(
        env_path=Path(__file__).resolve().parents[2] / ".env",
        error_type=OvertimeInterpretationReviewError,
    )
    return build_openai_client()


def resolve_review_models(
    *,
    evaluator_model: str | None,
    creator_model: str | None,
) -> tuple[str, str, int, int]:
    """Resolve model and token settings for step 3.2."""
    selected_evaluator_model = evaluator_model or os.getenv(
        "OVERTIME_INTERPRETATION_EVALUATOR_MODEL",
        EVALUATOR_MODEL,
    )
    selected_creator_model = creator_model or os.getenv(
        "OVERTIME_INTERPRETATION_REVIEW_CREATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )
    selected_evaluator_max_output_tokens = int(
        os.getenv(
            "OVERTIME_INTERPRETATION_EVALUATOR_MAX_OUTPUT_TOKENS",
            str(DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS),
        )
    )
    selected_creator_max_output_tokens = int(
        os.getenv(
            "OVERTIME_INTERPRETATION_REVIEW_CREATOR_MAX_OUTPUT_TOKENS",
            str(DEFAULT_CREATOR_MAX_OUTPUT_TOKENS),
        )
    )
    return (
        selected_evaluator_model,
        selected_creator_model,
        selected_evaluator_max_output_tokens,
        selected_creator_max_output_tokens,
    )


def extract_json_object_from_text(output_text: str) -> dict[str, Any]:
    """Parse a JSON object from raw model text, including fenced JSON output."""
    stripped_text = output_text.strip()
    if not stripped_text:
        raise ValueError("Model output was empty.")
    try:
        parsed_data = json.loads(stripped_text)
    except json.JSONDecodeError:
        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            stripped_text,
            flags=re.DOTALL,
        )
        if fenced_match is not None:
            parsed_data = json.loads(fenced_match.group(1))
        else:
            object_start = stripped_text.find("{")
            object_end = stripped_text.rfind("}")
            if object_start == -1 or object_end == -1 or object_end < object_start:
                raise
            parsed_data = json.loads(stripped_text[object_start : object_end + 1])

    if not isinstance(parsed_data, dict):
        raise ValueError("Model output was not a JSON object.")

    return parsed_data


def review_rule_schema() -> dict[str, Any]:
    """Define the strict JSON schema for one evaluator rule review."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": {"type": "string"},
            "recommendation": {
                "type": "string",
                "enum": list(ALLOWED_REVIEW_RECOMMENDATIONS),
            },
            "rationale": {"type": "string"},
        },
        "required": ["rule_id", "recommendation", "rationale"],
    }


def overtime_rule_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema for one overtime rule object."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": {"type": "string"},
            "section_heading": {"type": "string"},
            "employee_scope": {
                "type": "array",
                "items": {"type": "string"},
            },
            "clause_references": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rule_markdown": {"type": "string"},
            "rule_plain_text": {"type": "string"},
            "source_clause_numbers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_classifications": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "rule_id",
            "section_heading",
            "employee_scope",
            "clause_references",
            "rule_markdown",
            "rule_plain_text",
            "source_clause_numbers",
            "source_classifications",
        ],
    }


def evaluator_feedback_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema for evaluator feedback."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_markdown": {"type": "string"},
            "rule_reviews": {
                "type": "array",
                "items": review_rule_schema(),
            },
            "new_rules": {
                "type": "array",
                "items": overtime_rule_json_schema(),
            },
        },
        "required": ["summary_markdown", "rule_reviews", "new_rules"],
    }


def request_evaluator_feedback(
    *,
    evaluator_client: Any,
    evaluator_model: str,
    evaluator_max_output_tokens: int,
    evaluator_messages: list[dict[str, str]],
    original_rules,
    status_callback: Callable[[str], None] | None = None,
    ruleset_key: str,
) -> tuple[dict[str, Any], str]:
    """Run the evaluator review loop and return structured feedback."""
    current_evaluator_messages = evaluator_messages
    last_evaluator_validation_error = ""

    for attempt_number in range(MAX_EVALUATOR_REPAIR_ATTEMPTS + 1):
        log_model_call_budget(
            status_callback,
            call_label="step_3_2_evaluator_review",
            model=evaluator_model,
            payload=current_evaluator_messages,
            max_output_tokens=evaluator_max_output_tokens,
        )
        log_llm_prompt("3.2 Evaluator Review", current_evaluator_messages)
        evaluator_response = evaluator_client.responses.create(
            model=evaluator_model,
            input=current_evaluator_messages,
            max_output_tokens=evaluator_max_output_tokens,
            reasoning={"effort": "medium"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "overtime_rule_review_feedback",
                    "schema": evaluator_feedback_json_schema(),
                    "strict": True,
                }
            },
        )
        evaluator_output_text = extract_response_text(evaluator_response)
        log_llm_response(
            f"3.2 Evaluator Response - Attempt {attempt_number + 1}",
            evaluator_response,
            evaluator_output_text,
        )
        if not evaluator_output_text:
            last_evaluator_validation_error = "Evaluator response did not include output text."
            if attempt_number >= MAX_EVALUATOR_REPAIR_ATTEMPTS:
                raise OvertimeInterpretationReviewError(last_evaluator_validation_error)
            if status_callback:
                status_callback(
                    "Evaluator response was empty; requesting one corrected response."
                )
            current_evaluator_messages = build_evaluator_repair_messages(
                current_evaluator_messages,
                validation_error=last_evaluator_validation_error,
                prior_response_text="<empty response>",
                ruleset_key=ruleset_key,
            )
            continue

        try:
            evaluator_feedback_data = validate_review_feedback_artifact(
                extract_json_object_from_text(evaluator_output_text),
                original_rules,
            )
            evaluator_feedback_markdown = str(evaluator_feedback_data["summary_markdown"])
            return evaluator_feedback_data, evaluator_feedback_markdown
        except ValueError as error:
            last_evaluator_validation_error = str(error)
            if attempt_number >= MAX_EVALUATOR_REPAIR_ATTEMPTS:
                raise OvertimeInterpretationReviewError(
                    "Evaluator response could not be validated as structured JSON: "
                    f"{last_evaluator_validation_error}"
                ) from error

            if status_callback:
                status_callback(
                    "Evaluator response failed validation; requesting one corrected response."
                )
            current_evaluator_messages = build_evaluator_repair_messages(
                current_evaluator_messages,
                validation_error=last_evaluator_validation_error,
                prior_response_text=evaluator_output_text,
                ruleset_key=ruleset_key,
            )

    raise OvertimeInterpretationReviewError("Evaluator review loop did not produce output.")


def run_evaluator_review(
    *,
    inputs: Step3ReviewInputs,
    evaluator_client: Any,
    evaluator_model: str,
    evaluator_max_output_tokens: int,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], str]:
    """Build reviewer messages and run the evaluator review step."""
    evaluator_messages = build_review_evaluator_messages(
        interpretation_path=inputs.selected_interpretation_path,
        original_rules_artifact=inputs.original_rules_artifact,
        interpretation_markdown=inputs.interpretation_markdown,
        classification_path=inputs.selected_classification_path,
        payment_classification=inputs.classification_data,
        overtime_clause_classification_path=inputs.selected_overtime_clause_classification_path,
        overtime_clause_classification=inputs.overtime_clause_classification,
        ruleset_key=inputs.selected_ruleset_key,
    )
    return request_evaluator_feedback(
        evaluator_client=evaluator_client,
        evaluator_model=evaluator_model,
        evaluator_max_output_tokens=evaluator_max_output_tokens,
        evaluator_messages=evaluator_messages,
        original_rules=inputs.original_rules_artifact["rules"],
        status_callback=status_callback,
        ruleset_key=inputs.selected_ruleset_key,
    )
