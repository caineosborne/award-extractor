"""Shared logic for step 3.2 ruleset review."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    resolve_overtime_clause_classification_path,
)
from src.common.llm_io import extract_response_text
from src.common.model_call_budget import log_model_call_budget
from src.common.overtime_rules import (
    ALLOWED_REVIEW_RECOMMENDATIONS,
    OVERTIME_RULE_REVIEW_SCHEMA_VERSION,
    OVERTIME_RULE_SCHEMA_VERSION,
    OvertimeRule,
    apply_review_decisions,
    clause_coverage_warnings,
    decision_output_path_for_markdown,
    json_output_path_for_markdown,
    load_rules_artifact,
    make_json_serializable,
    prepend_validation_warnings,
    rules_from_markdown_fallback,
    render_rules_markdown,
    rule_to_dict,
    validate_review_feedback_artifact,
    write_rules_artifact,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.common.pipeline_io import load_json_object, load_text_file as load_text_document
from src.common.pipeline_runtime import (
    load_openai_environment as require_openai_environment,
)
from src.step_2_2_classify_overtime_clauses.core import load_classification
from src.prompts.step_3_2_review_ruleset import (
    build_creator_repair_messages,
    build_evaluator_repair_messages,
)


DEFAULT_INTERPRETATION_PATH = PROJECT_ROOT / "data" / "processed" / "MA000018" / "MA000018_overtime_interpretation.md"
EVALUATOR_MODEL = "gpt-5-mini"
DEFAULT_CREATOR_MODEL = "gpt-5-mini"
DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS = 8000
DEFAULT_CREATOR_MAX_OUTPUT_TOKENS = 8000
DEFAULT_INTER_CALL_DELAY_SECONDS = 15.0
MAX_CREATOR_REPAIR_ATTEMPTS = 2
MAX_EVALUATOR_REPAIR_ATTEMPTS = 2
REVIEW_RULESET_CHOICES = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
)
CREATOR_RESPONSE_PATTERN = re.compile(
    r"<creator_response>\s*(?P<creator_response>.*?)\s*</creator_response>\s*"
    r"<revised_interpretation>\s*(?P<revised_interpretation>.*?)\s*</revised_interpretation>",
    re.DOTALL,
)


class OvertimeInterpretationReviewError(RuntimeError):
    """Base exception for overtime interpretation review failures."""


@dataclass(frozen=True)
class OvertimeInterpretationReviewArtifacts:
    """Store the output paths and text produced by the step-3.2 review workflow."""

    evaluator_feedback_path: Path
    evaluator_feedback_json_path: Path
    creator_response_path: Path
    creator_response_json_path: Path
    revised_interpretation_path: Path
    revised_interpretation_json_path: Path
    evaluator_feedback_markdown: str
    creator_response_markdown: str
    revised_interpretation_markdown: str


def extract_chat_response_text(response: Any) -> str:
    """Extract plain text from a chat-completions style response object."""
    choices = getattr(response, "choices", None)
    if not choices:
        return ""

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for content_item in content:
            if isinstance(content_item, Mapping):
                text = content_item.get("text")
            else:
                text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        return "\n".join(text_parts)

    return ""


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


def load_openai_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load the OpenAI environment used for step 3.2 model calls."""
    require_openai_environment(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def build_openai_client() -> OpenAI:
    """Build the direct OpenAI client used by the step 3.2 models."""
    return OpenAI()


def load_text_file(path: Path | str, description: str) -> str:
    """Load a required text artifact for the review workflow."""
    return load_text_document(
        path,
        description,
        error_type=OvertimeInterpretationReviewError,
    )


def load_json_file(path: Path | str, description: str) -> dict[str, Any]:
    """Load a required JSON artifact for the review workflow."""
    return load_json_object(
        path,
        description,
        error_type=OvertimeInterpretationReviewError,
    )


def load_review_source_artifacts(
    interpretation_path: Path | str,
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> tuple[Path, Path, Path, str, dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Load and validate all source artifacts needed for the step-3.2 review."""
    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    try:
        inferred_ruleset_key = infer_overtime_ruleset_key_from_path(selected_interpretation_path)
    except ValueError:
        inferred_ruleset_key = OVERTIME_CREATION_RULESET
    selected_overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        selected_classification_path,
        overtime_clause_classification_path,
        selected_interpretation_path,
    )
    selected_rules_json_path = json_output_path_for_markdown(selected_interpretation_path)

    if selected_rules_json_path.exists():
        original_rules_artifact = load_rules_artifact(
            selected_rules_json_path,
            expected_schema_version=OVERTIME_RULE_SCHEMA_VERSION,
        )
        interpretation_markdown = str(original_rules_artifact["rendered_markdown"])
    else:
        interpretation_markdown = load_text_file(
            selected_interpretation_path,
            "Overtime interpretation markdown",
        )
        original_rules_artifact = {
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "source_classification_file": str(selected_classification_path),
            "source_clause_classification_file": str(
                selected_overtime_clause_classification_path
            ),
            "rendered_markdown": interpretation_markdown,
            "rules": rules_from_markdown_fallback(
                interpretation_markdown,
                source_path=selected_interpretation_path,
            ),
        }

    classification_data = load_classification(selected_classification_path)
    classified_clauses = classification_data.get("classified_clauses")
    if not classified_clauses:
        raise OvertimeInterpretationReviewError(
            f"No classified clauses found in: {selected_classification_path}"
        )

    overtime_clause_classification = load_json_file(
        selected_overtime_clause_classification_path,
        "Step 2.2 overtime clause classification JSON",
    )

    return (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        inferred_ruleset_key,
        original_rules_artifact,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    )


def selected_review_models(
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
        evaluator_response = evaluator_client.responses.create(
            model=evaluator_model,
            input=current_evaluator_messages,
            max_output_tokens=evaluator_max_output_tokens,
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
        creator_response = creator_client.responses.create(
            model=creator_model,
            input=current_creator_messages,
            max_output_tokens=creator_max_output_tokens,
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

        reviewed_rules_artifact = apply_review_decisions(
            original_rules=original_rules,
            evaluator_feedback=evaluator_feedback_data,
            creator_decision_data={},
        )
        creator_response_markdown = fallback_creator_response_markdown(
            validation_error=last_validation_error or "Creator response could not be validated.",
            creator_output_text=creator_output_text,
        )
        revised_interpretation_markdown = original_rendered_markdown

    return (
        creator_response_data,
        reviewed_rules_artifact,
        creator_response_markdown,
        revised_interpretation_markdown,
        last_validation_error,
    )


def validation_output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default manual review output path for one interpretation file."""
    path = Path(interpretation_path)
    return path.with_name(f"{path.stem}_validation.json")


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
