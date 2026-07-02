"""LLM helpers for step 3.2 ruleset review."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.model_call_budget import log_model_call_budget
from src.common.overtime_rules import (
    OVERTIME_RULE_REVIEW_SCHEMA_VERSION,
    OVERTIME_RULE_SCHEMA_VERSION,
    apply_review_decisions,
    load_rules_artifact,
    make_json_serializable,
    prepend_validation_warnings,
    rules_from_markdown_fallback,
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

from .core import (
    DEFAULT_CREATOR_MAX_OUTPUT_TOKENS,
    DEFAULT_CREATOR_MODEL,
    DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS,
    DEFAULT_INTER_CALL_DELAY_SECONDS,
    EVALUATOR_MODEL,
    MAX_CREATOR_REPAIR_ATTEMPTS,
    MAX_EVALUATOR_REPAIR_ATTEMPTS,
    OvertimeInterpretationReviewError,
    build_openai_client,
    creator_review_json_schema,
    evaluator_feedback_json_schema,
)
from .deterministic import load_review_source_artifacts


CREATOR_RESPONSE_PATTERN = re.compile(
    r"<creator_response>\s*(?P<creator_response>.*?)\s*</creator_response>\s*"
    r"<revised_interpretation>\s*(?P<revised_interpretation>.*?)\s*</revised_interpretation>",
    re.DOTALL,
)


def load_openai_environment(env_path: Path | str = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load the OpenAI environment used for step 3.2 model calls."""
    require_openai_environment(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def load_client() -> OpenAI:
    """Load the OpenAI environment and return a client for step 3.2."""
    load_openai_environment()
    return build_openai_client()


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


def build_creator_repair_messages(
    original_messages: Sequence[Mapping[str, str]],
    *,
    validation_error: str,
    prior_response_text: str,
) -> list[dict[str, str]]:
    """Ask the creator model to correct an invalid structured review response."""
    repair_instruction = (
        "Your previous structured JSON response failed validation.\n\n"
        f"Validation error:\n- {validation_error}\n\n"
        "Correct the JSON and return JSON only.\n"
        "Do not omit any original rule.\n"
        "Do not remove a rule unless both evaluator and creator explicitly support removal.\n"
        "If you marked a rule as modify but do not need to change any fields, use decision keep.\n"
        "If you mark a rule as modify, include an updated_rule object or change the decision to keep.\n"
        "Do not invent creator-only new rules.\n"
        "Treat the evaluator structured review JSON new_rules array as the only authoritative source of evaluator-proposed new rule_ids.\n"
        "Do not include any new_rule_reviews entry unless its rule_id appears in that evaluator structured review JSON new_rules array.\n"
        "Every evaluator-proposed new rule must appear in new_rule_reviews with decision accept, modify, or reject.\n"
        "If you use decision modify for an evaluator-proposed new rule, include updated_rule.\n\n"
        "Previous response:\n"
        f"```json\n{prior_response_text}\n```"
    )

    repaired_messages = [dict(message) for message in original_messages]
    repaired_messages.append({"role": "user", "content": repair_instruction})
    return repaired_messages


def build_evaluator_repair_messages(
    original_messages: Sequence[Mapping[str, str]],
    *,
    validation_error: str,
    prior_response_text: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Ask the evaluator model to correct an invalid structured review response."""
    del ruleset_key
    repair_instruction = (
        "Your previous structured JSON response failed validation.\n\n"
        f"Validation error:\n- {validation_error}\n\n"
        "Correct the JSON and return JSON only.\n"
        "You must keep one rule_reviews item for every original rule_id.\n"
        "Do not silently drop any original rule.\n"
        "If you recommend removal, the rationale must clearly support that removal.\n"
        "Only use new_rules for clearly supported missing rules for the selected ruleset.\n\n"
        "Previous response:\n"
        f"```json\n{prior_response_text}\n```"
    )

    repaired_messages = [dict(message) for message in original_messages]
    repaired_messages.append({"role": "user", "content": repair_instruction})
    return repaired_messages


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


def build_review_evaluator_messages(*args, **kwargs):
    from src.prompts.overtime_interpretation_review import build_review_evaluator_messages

    return build_review_evaluator_messages(*args, **kwargs)


def build_review_creator_messages(*args, **kwargs):
    from src.prompts.overtime_interpretation_review import build_review_creator_messages

    return build_review_creator_messages(*args, **kwargs)
