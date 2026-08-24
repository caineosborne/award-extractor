"""Step 3.2 stage 3: run the creator response and revision loop."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from src.common.llm_io import extract_response_text
from src.common.model_call_budget import log_model_call_budget
from src.common.prompt_logging import log_llm_prompt, log_llm_response
from src.common.overtime_rules import apply_review_decisions, make_json_serializable
from src.prompts.step_3_2_review_ruleset import (
    build_creator_repair_messages,
    build_review_creator_messages,
)

from .schema import (
    DEFAULT_INTER_CALL_DELAY_SECONDS,
    MAX_CREATOR_REPAIR_ATTEMPTS,
    OvertimeInterpretationReviewError,
)
from .step_1_load_inputs import Step3ReviewInputs
from .step_2_run_reviewer import extract_json_object_from_text, overtime_rule_json_schema


def fallback_creator_response_markdown(
    *,
    validation_error: str,
    creator_output_text: str,
) -> str:
    """Build a manual-review record when structured creator output cannot be applied."""
    parsed_response: dict[str, Any] | None = None
    try:
        parsed_response = extract_json_object_from_text(creator_output_text)
    except Exception:
        parsed_response = None

    review_section = ""
    if parsed_response and isinstance(parsed_response.get("review_decisions"), list):
        review_section = json.dumps(
            make_json_serializable(parsed_response["review_decisions"]),
            indent=2,
            ensure_ascii=False,
        )

    return "\n".join(
        [
            "# Creator response",
            "",
            "The structured creator response could not be validated.",
            "",
            f"Validation error: {validation_error}",
            "",
            "Raw model output:",
            "```",
            creator_output_text.strip(),
            "```",
            "",
            "Parsed review decisions:",
            "```json",
            review_section,
            "```",
        ]
    ).strip()


def creator_rule_update_schema() -> dict[str, Any]:
    """Define the strict JSON schema for one creator update to an original rule."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": {"type": "string"},
            "decision": {
                "type": "string",
                "enum": ["keep", "modify", "remove"],
            },
            "reason": {"type": "string"},
            "updated_rule": {
                "anyOf": [
                    overtime_rule_json_schema(),
                    {"type": "null"},
                ]
            },
        },
        "required": ["rule_id", "decision", "reason", "updated_rule"],
    }


def creator_new_rule_review_schema() -> dict[str, Any]:
    """Define the strict JSON schema for one creator decision on a new evaluator rule."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": {"type": "string"},
            "decision": {
                "type": "string",
                "enum": ["accept", "modify", "reject"],
            },
            "reason": {"type": "string"},
            "updated_rule": {
                "anyOf": [
                    overtime_rule_json_schema(),
                    {"type": "null"},
                ]
            },
        },
        "required": ["rule_id", "decision", "reason", "updated_rule"],
    }


def creator_review_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema for creator revision output."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_record_markdown": {"type": "string"},
            "rule_updates": {
                "type": "array",
                "items": creator_rule_update_schema(),
            },
            "new_rule_reviews": {
                "type": "array",
                "items": creator_new_rule_review_schema(),
            },
        },
        "required": [
            "decision_record_markdown",
            "rule_updates",
            "new_rule_reviews",
        ],
    }


def request_creator_revision(
    *,
    creator_client: Any,
    creator_model: str,
    creator_max_output_tokens: int,
    creator_messages: list[dict[str, str]],
    original_rules,
    original_rendered_markdown: str,
    evaluator_feedback_data,
    status_callback: Callable[[str], None] | None = None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    """Run the creator revision loop and return the reviewed ruleset state."""
    if inter_call_delay_seconds > 0:
        if status_callback:
            status_callback(
                "Waiting "
                f"{inter_call_delay_seconds:.1f} seconds before creator update."
            )
        time.sleep(inter_call_delay_seconds)

    log_model_call_budget(
        status_callback,
        call_label="step_3_2_creator_revision",
        model=creator_model,
        payload=creator_messages,
        max_output_tokens=creator_max_output_tokens,
    )
    current_creator_messages = creator_messages
    creator_output_text = ""
    creator_response_data: dict[str, Any] = {}
    reviewed_rules_artifact: dict[str, Any] | None = None
    creator_response_markdown = ""
    revised_interpretation_markdown = ""
    last_validation_error = ""

    for attempt_number in range(MAX_CREATOR_REPAIR_ATTEMPTS + 1):
        log_llm_prompt("3.2 Creator Review", current_creator_messages)
        creator_response = creator_client.responses.create(
            model=creator_model,
            input=current_creator_messages,
            max_output_tokens=creator_max_output_tokens,
            reasoning={"effort": "medium"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "overtime_rule_review_revision",
                    "schema": creator_review_json_schema(),
                    "strict": True,
                }
            },
        )
        creator_output_text = extract_response_text(creator_response)
        log_llm_response(
            f"3.2 Creator Response - Attempt {attempt_number + 1}",
            creator_response,
            creator_output_text,
        )
        if not creator_output_text:
            last_validation_error = "Creator response did not include output text."
            if attempt_number >= MAX_CREATOR_REPAIR_ATTEMPTS:
                break
            if status_callback:
                status_callback(
                    "Creator response was empty; requesting one corrected response."
                )
            current_creator_messages = build_creator_repair_messages(
                current_creator_messages,
                validation_error=last_validation_error,
                prior_response_text="<empty response>",
            )
            continue

        try:
            creator_response_data = extract_json_object_from_text(creator_output_text)
            reviewed_rules_artifact = apply_review_decisions(
                original_rules=original_rules,
                evaluator_feedback=evaluator_feedback_data,
                creator_decision_data=creator_response_data,
            )
            creator_response_markdown = str(
                reviewed_rules_artifact["decision_record_markdown"]
            )
            revised_interpretation_markdown = str(
                reviewed_rules_artifact["rendered_markdown"]
            )
            creator_response_data = {
                **creator_response_data,
                "rendered_markdown": revised_interpretation_markdown,
            }
            last_validation_error = ""
            return (
                creator_response_data,
                reviewed_rules_artifact,
                creator_response_markdown,
                revised_interpretation_markdown,
                last_validation_error,
            )
        except ValueError as exc:
            last_validation_error = str(exc)

        if attempt_number >= MAX_CREATOR_REPAIR_ATTEMPTS:
            break

        if status_callback:
            status_callback(
                "Creator response failed validation; requesting one corrected response."
            )
        current_creator_messages = build_creator_repair_messages(
            current_creator_messages,
            validation_error=last_validation_error,
            prior_response_text=creator_output_text,
        )

    if reviewed_rules_artifact is None:
        if not creator_output_text:
            raise OvertimeInterpretationReviewError(
                last_validation_error or "Creator response did not include output text."
            )

        creator_response_markdown = fallback_creator_response_markdown(
            validation_error=last_validation_error or "Creator response could not be validated.",
            creator_output_text=creator_output_text,
        )
        revised_interpretation_markdown = original_rendered_markdown
        reviewed_rules_artifact = {
            "rules": list(original_rules),
            "review_decisions": [
                {
                    "rule_id": rule.rule_id,
                    "evaluator_recommendation": "keep",
                    "creator_decision": "keep",
                    "final_decision": "kept",
                    "reason": "Preserved original rules after creator validation failure.",
                }
                for rule in original_rules
            ],
        }
        creator_response_data = {
            "decision_record_markdown": creator_response_markdown,
            "rule_updates": [],
            "new_rule_reviews": [],
            "rendered_markdown": revised_interpretation_markdown,
            "validation_error": last_validation_error,
            "raw_creator_response": creator_output_text,
        }

    return (
        creator_response_data,
        reviewed_rules_artifact,
        creator_response_markdown,
        revised_interpretation_markdown,
        last_validation_error,
    )


def run_creator_review(
    *,
    inputs: Step3ReviewInputs,
    evaluator_feedback_data: dict[str, Any],
    evaluator_feedback_markdown: str,
    creator_client: Any,
    creator_model: str,
    creator_max_output_tokens: int,
    status_callback: Callable[[str], None] | None = None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    """Build creator messages and run the creator revision step."""
    creator_messages = build_review_creator_messages(
        interpretation_path=inputs.selected_interpretation_path,
        original_rules_artifact=inputs.original_rules_artifact,
        interpretation_markdown=inputs.interpretation_markdown,
        classification_path=inputs.selected_classification_path,
        payment_classification=inputs.classification_data,
        overtime_clause_classification_path=inputs.selected_overtime_clause_classification_path,
        overtime_clause_classification=inputs.overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        ruleset_key=inputs.selected_ruleset_key,
    )
    return request_creator_revision(
        creator_client=creator_client,
        creator_model=creator_model,
        creator_max_output_tokens=creator_max_output_tokens,
        creator_messages=creator_messages,
        original_rules=inputs.original_rules_artifact["rules"],
        original_rendered_markdown=inputs.interpretation_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        status_callback=status_callback,
        inter_call_delay_seconds=inter_call_delay_seconds,
    )
