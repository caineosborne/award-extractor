"""Step 3B overtime interpretation review workflow.

Prompt ownership:
- Uses `src/prompts/overtime_interpretation_review.py`.
"""

import argparse
import json
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    creator_response_path_for_interpretation,
    default_classification_path_for_award,
    default_interpretation_path_for_award,
    evaluator_feedback_path_for_interpretation,
    feedback_dir_for_interpretation,
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
    revised_output_path_for_interpretation,
)
from src.common.model_call_budget import log_model_call_budget
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_io import load_json_object, load_text_file as load_text_document
from src.common.pipeline_runtime import (
    load_openai_environment as require_openai_environment,
)
from src.common.llm_io import extract_response_text
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
from src.script_3_interpret_overtime import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_MODEL as DEFAULT_CREATOR_MODEL,
    load_classification,
)
from src.prompts.overtime_interpretation_review import (
    build_full_evaluator_review_prompt,
    build_minimal_creator_revision_prompt,
    build_relevant_clause_excerpt_markdown,
    build_script_3_creator_prompt_context,
    creator_structured_output_instructions,
    evaluator_structured_output_instructions,
    evaluation_system_prompt,
)


# 1. Imports / constants

DEFAULT_INTERPRETATION_PATH = default_interpretation_path_for_award("MA000018")
EVALUATOR_MODEL = "gpt-5-mini"
DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS = 8000
DEFAULT_CREATOR_MAX_OUTPUT_TOKENS = 4000
CREATOR_RESPONSE_PATTERN = re.compile(
    r"<creator_response>\s*(?P<creator_response>.*?)\s*</creator_response>\s*"
    r"<revised_interpretation>\s*(?P<revised_interpretation>.*?)\s*</revised_interpretation>",
    re.DOTALL,
)
DEFAULT_INTER_CALL_DELAY_SECONDS = 30.0
MAX_CREATOR_REPAIR_ATTEMPTS = 1
MAX_EVALUATOR_REPAIR_ATTEMPTS = 2


def _structured_rule_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": {"type": "string"},
            "section_heading": {"type": "string"},
            "employee_scope": {"type": "array", "items": {"type": "string"}},
            "clause_references": {"type": "array", "items": {"type": "string"}},
            "rule_markdown": {"type": "string"},
            "rule_plain_text": {"type": "string"},
            "source_clause_numbers": {"type": "array", "items": {"type": "string"}},
            "source_classifications": {"type": "array", "items": {"type": "string"}},
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


class OvertimeInterpretationReviewError(RuntimeError):
    """Base exception for overtime interpretation review failures."""


# 2. Data structures


@dataclass(frozen=True)
class OvertimeInterpretationReviewArtifacts:
    """Store the output paths and text produced by the step-3B review workflow."""

    evaluator_feedback_path: Path
    evaluator_feedback_json_path: Path
    creator_response_path: Path
    creator_response_json_path: Path
    revised_interpretation_path: Path
    revised_interpretation_json_path: Path
    evaluator_feedback_markdown: str
    creator_response_markdown: str
    revised_interpretation_markdown: str


# 3. Environment / file helpers


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
            # OpenRouter content blocks may be dicts or SDK objects, so handle both shapes.
            if isinstance(content_item, Mapping):
                text = content_item.get("text")
            else:
                text = getattr(content_item, "text", None)

            # Keep only non-empty text blocks when assembling the response body.
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

        return "\n".join(text_parts)

    return ""


def extract_chat_completion_text(response: Any) -> str:
    """Return chat response text using the legacy helper name."""
    return extract_chat_response_text(response)


def extract_json_object_from_text(output_text: str) -> dict[str, Any]:
    """Parse a JSON object from raw model text, including fenced JSON output."""
    stripped_text = output_text.strip()
    if not stripped_text:
        raise ValueError("Model output was empty.")

    try:
        parsed_data = json.loads(stripped_text)
    except json.JSONDecodeError:
        repaired_text = _repair_multiline_json_strings(stripped_text)
        if repaired_text != stripped_text:
            try:
                parsed_data = json.loads(repaired_text)
            except json.JSONDecodeError:
                parsed_data = None
        else:
            parsed_data = None

        if parsed_data is not None:
            if not isinstance(parsed_data, dict):
                raise ValueError("Model output was not a JSON object.")
            return parsed_data

        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            stripped_text,
            flags=re.DOTALL,
        )
        if fenced_match is not None:
            return extract_json_object_from_text(fenced_match.group(1))

        object_start = stripped_text.find("{")
        object_end = stripped_text.rfind("}")
        if object_start == -1 or object_end == -1 or object_end < object_start:
            raise

        candidate_text = stripped_text[object_start : object_end + 1]
        parsed_data = json.loads(candidate_text)

    if not isinstance(parsed_data, dict):
        raise ValueError("Model output was not a JSON object.")

    return parsed_data


def _repair_multiline_json_strings(json_text: str) -> str:
    """Escape raw control characters that appear inside JSON string values."""
    repaired_chars: list[str] = []
    in_string = False
    escaped = False

    for char in json_text:
        if not in_string:
            repaired_chars.append(char)
            if char == '"':
                in_string = True
            continue

        if escaped:
            repaired_chars.append(char)
            escaped = False
            continue

        if char == "\\":
            repaired_chars.append(char)
            escaped = True
            continue

        if char == '"':
            repaired_chars.append(char)
            in_string = False
            continue

        if char == "\n":
            repaired_chars.append("\\n")
            continue

        if char == "\r":
            repaired_chars.append("\\r")
            continue

        if char == "\t":
            repaired_chars.append("\\t")
            continue

        repaired_chars.append(char)

    return "".join(repaired_chars)


def load_openai_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load the OpenAI environment used for step 3B model calls."""
    require_openai_environment(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def build_openai_client() -> OpenAI:
    """Build the direct OpenAI client used by the step 3B models."""
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
) -> tuple[Path, Path, Path, dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Load and validate all source artifacts needed for the step-3B review."""
    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    selected_overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        selected_classification_path,
        overtime_clause_classification_path,
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
    # Load the payment-classification JSON from step 2.
    classification_data = load_classification(selected_classification_path)
    classified_clauses = classification_data.get("classified_clauses")
    if not classified_clauses:
        raise OvertimeInterpretationReviewError(
            f"No classified clauses found in: {selected_classification_path}"
        )

    # Load the intermediate clause-classification JSON from step 3.
    overtime_clause_classification = load_json_file(
        selected_overtime_clause_classification_path,
        "Script 3 overtime clause classification JSON",
    )

    return (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        original_rules_artifact,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    )


def load_review_sources(
    interpretation_path: Path | str,
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> tuple[Path, Path, Path, dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Return review source artifacts using the legacy helper name."""
    return load_review_source_artifacts(
        interpretation_path,
        classification_path,
        overtime_clause_classification_path,
    )


# 4. Prompt building / parsing


def build_review_evaluator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    original_rules_artifact: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the evaluator prompt set for the step-3B review."""
    return [
        {"role": "system", "content": evaluation_system_prompt()},
        {
            "role": "user",
            # Build the full evaluator review prompt from the interpretation and source artifacts.
            "content": build_full_evaluator_review_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                original_rules_artifact=original_rules_artifact,
                classification_path=classification_path,
                payment_classification=payment_classification,
                overtime_clause_classification_path=overtime_clause_classification_path,
                overtime_clause_classification=overtime_clause_classification,
            )
            + "\n\n"
            + evaluator_structured_output_instructions(),
        },
    ]


def build_evaluator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    original_rules_artifact: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return evaluator messages using the legacy helper name."""
    return build_review_evaluator_messages(
        interpretation_path=interpretation_path,
        original_rules_artifact=original_rules_artifact,
        interpretation_markdown=interpretation_markdown,
        classification_path=classification_path,
        payment_classification=payment_classification,
        overtime_clause_classification_path=overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
    )


def build_review_creator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    evaluator_feedback_data: Mapping[str, Any] | None = None,
    prior_creator_decision_markdown: str | None = None,
    original_rules_artifact: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the creator prompt set used to revise the interpretation."""
    # Extract only the clause excerpts that matter to the evaluator's feedback.
    relevant_clause_excerpt_markdown = build_relevant_clause_excerpt_markdown(
        interpretation_markdown=interpretation_markdown,
        payment_classification=payment_classification,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        prior_creator_decision_markdown=prior_creator_decision_markdown,
    )

    # Rebuild the original script-3 creator prompt context for consistency with the source workflow.
    creator_prompt_context = build_script_3_creator_prompt_context(
        classification_path,
        payment_classification,
        overtime_clause_classification,
    )

    return [
        # Reuse the original system message from the step-3 creator context.
        creator_prompt_context["interpretation_messages"][0],
        {
            "role": "user",
            # Ask the creator model to revise the interpretation in response to evaluator feedback.
            "content": build_minimal_creator_revision_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                relevant_clause_excerpt_markdown=relevant_clause_excerpt_markdown,
                evaluator_feedback_markdown=evaluator_feedback_markdown,
                prior_creator_decision_markdown=prior_creator_decision_markdown,
            )
            + "\n\nOriginal step-3 rules JSON:\n```json\n"
            + json.dumps(
                {
                    **(dict(original_rules_artifact) if original_rules_artifact else {}),
                    "rules": [
                        rule_to_dict(rule) if isinstance(rule, OvertimeRule) else rule
                        for rule in (
                            list((original_rules_artifact or {}).get("rules", []))
                        )
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n"
            + "\n\nEvaluator structured review JSON:\n```json\n"
            + json.dumps(
                make_json_serializable(dict(evaluator_feedback_data or {})),
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n"
            + "\n\n"
            + creator_structured_output_instructions(),
        },
    ]


def build_creator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    evaluator_feedback_data: Mapping[str, Any] | None = None,
    prior_creator_decision_markdown: str | None = None,
    original_rules_artifact: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return creator messages using the legacy helper name."""
    return build_review_creator_messages(
        interpretation_path=interpretation_path,
        original_rules_artifact=original_rules_artifact,
        interpretation_markdown=interpretation_markdown,
        classification_path=classification_path,
        payment_classification=payment_classification,
        overtime_clause_classification_path=overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        prior_creator_decision_markdown=prior_creator_decision_markdown,
    )


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
) -> list[dict[str, str]]:
    """Ask the evaluator model to correct an invalid structured review response."""
    repair_instruction = (
        "Your previous structured JSON response failed validation.\n\n"
        f"Validation error:\n- {validation_error}\n\n"
        "Correct the JSON and return JSON only.\n"
        "You must keep one rule_reviews item for every original rule_id.\n"
        "Do not silently drop any original rule.\n"
        "If you recommend removal, the rationale must clearly support that removal.\n"
        "Only use new_rules for clearly supported missing overtime-creation rules.\n\n"
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
        loaded_response = json.loads(creator_output_text)
        if isinstance(loaded_response, dict):
            parsed_response = loaded_response
    except json.JSONDecodeError:
        parsed_response = None

    rendered_sections: list[str] = [
        "# Creator response validation failure",
        "",
        "The structured step 3B creator response could not be applied automatically.",
        "",
        "## Validation error",
        "",
        f"- {validation_error}",
        "",
    ]

    decision_record_markdown = ""
    if parsed_response is not None:
        decision_record_markdown = str(
            parsed_response.get("decision_record_markdown") or ""
        ).strip()

    if decision_record_markdown:
        rendered_sections.extend(
            [
                "## Creator decision record",
                "",
                decision_record_markdown,
                "",
            ]
        )

    if parsed_response is not None:
        rule_updates = parsed_response.get("rule_updates", [])
        new_rule_reviews = parsed_response.get("new_rule_reviews", [])
        rendered_sections.extend(
            [
                "## Structured response summary",
                "",
                f"- Rule updates returned: {len(rule_updates) if isinstance(rule_updates, list) else 0}",
                f"- Evaluator-proposed new rule decisions returned: {len(new_rule_reviews) if isinstance(new_rule_reviews, list) else 0}",
                "",
            ]
        )

    rendered_sections.extend(
        [
            "## Raw creator response",
            "",
            "```json" if parsed_response is not None else "```text",
            (
                json.dumps(parsed_response, indent=2, ensure_ascii=False)
                if parsed_response is not None
                else creator_output_text
            ),
            "```",
            "",
            "The original step-3 rules were preserved as the revised output so a human can "
            "review the failure manually.",
        ]
    )

    return "\n".join(rendered_sections)


def fallback_evaluator_feedback_markdown(
    *,
    validation_error: str,
    evaluator_output_text: str,
) -> str:
    """Build a manual-review record when structured evaluator output is invalid."""
    parsed_response: dict[str, Any] | None = None
    try:
        loaded_response = extract_json_object_from_text(evaluator_output_text)
        if isinstance(loaded_response, dict):
            parsed_response = loaded_response
    except (json.JSONDecodeError, ValueError):
        parsed_response = None

    rendered_sections: list[str] = [
        "# Evaluator feedback validation failure",
        "",
        "The structured step 3B evaluator feedback could not be applied automatically.",
        "",
        "## Validation error",
        "",
        f"- {validation_error}",
        "",
    ]

    if parsed_response is not None:
        summary_markdown = str(parsed_response.get("summary_markdown") or "").strip()
        rule_reviews = parsed_response.get("rule_reviews", [])
        new_rules = parsed_response.get("new_rules", [])

        if summary_markdown:
            rendered_sections.extend(
                [
                    "## Extracted evaluator summary",
                    "",
                    summary_markdown,
                    "",
                ]
            )

        rendered_sections.extend(
            [
                "## Structured response summary",
                "",
                f"- Rule reviews returned: {len(rule_reviews) if isinstance(rule_reviews, list) else 0}",
                f"- New rules returned: {len(new_rules) if isinstance(new_rules, list) else 0}",
                "",
            ]
        )

    rendered_sections.extend(
        [
            "## Raw evaluator response",
            "",
            "```json" if parsed_response is not None else "```text",
            (
                json.dumps(parsed_response, indent=2, ensure_ascii=False)
                if parsed_response is not None
                else evaluator_output_text
            ),
            "```",
            "",
            "The evaluator recommendations were not applied automatically. Review this "
            "response manually before relying on the revised interpretation.",
        ]
    )

    return "\n".join(rendered_sections)


def evaluator_feedback_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_markdown": {"type": "string"},
            "rule_reviews": {
                "type": "array",
                "items": {
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
                },
            },
            "new_rules": {
                "type": "array",
                "items": {
                    **_structured_rule_schema(),
                },
            },
        },
        "required": ["summary_markdown", "rule_reviews", "new_rules"],
    }


def creator_review_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_record_markdown": {"type": "string"},
            "rule_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rule_id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["keep", "modify", "remove"]},
                        "reason": {"type": "string"},
                        "updated_rule": {
                            "anyOf": [
                                _structured_rule_schema(),
                                {"type": "null"},
                            ]
                        },
                    },
                    "required": ["rule_id", "decision", "reason", "updated_rule"],
                },
            },
            "new_rule_reviews": {
                "type": "array",
                "items": {
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
                            "anyOf": [_structured_rule_schema(), {"type": "null"}]
                        },
                    },
                    "required": ["rule_id", "decision", "reason", "updated_rule"],
                },
            },
        },
        "required": [
            "decision_record_markdown",
            "rule_updates",
            "new_rule_reviews",
        ],
    }


def split_creator_update_sections(output_text: str) -> tuple[str, str]:
    """Support legacy tagged output and newer JSON creator-review output."""
    match = CREATOR_RESPONSE_PATTERN.search(output_text)
    if match:
        creator_response = match.group("creator_response").strip()
        revised_interpretation = match.group("revised_interpretation").strip()
        if not creator_response or not revised_interpretation:
            raise OvertimeInterpretationReviewError(
                "Creator response contained empty tagged sections."
            )
        return creator_response, revised_interpretation

    try:
        data = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OvertimeInterpretationReviewError(
            "Creator response did not include the required tagged sections or valid JSON."
        ) from exc

    creator_response = str(data.get("decision_record_markdown") or "").strip()
    revised_interpretation = str(data.get("rendered_markdown") or "").strip()

    if not creator_response:
        raise OvertimeInterpretationReviewError("Creator response section is empty.")
    if not revised_interpretation:
        raise OvertimeInterpretationReviewError("Revised interpretation section is empty.")

    return creator_response, revised_interpretation


def parse_creator_update(output_text: str) -> tuple[str, str]:
    """Return the split creator output using the legacy helper name."""
    return split_creator_update_sections(output_text)


# 5. Review orchestration


def review_overtime_interpretation(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    overtime_clause_classification_path: Path | str | None = None,
    feedback_output_path: Path | str | None = None,
    creator_response_output_path: Path | str | None = None,
    revised_output_path: Path | str | None = None,
    evaluator_model: str | None = None,
    creator_model: str | None = None,
    evaluator_client: Any | None = None,
    creator_client: Any | None = None,
    status_callback: Callable[[str], None] | None = None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
) -> OvertimeInterpretationReviewArtifacts:
    """Run the one-pass evaluator and creator review workflow for step 3B."""
    # Pick explicit model overrides first, then environment variables, then defaults.
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

    if evaluator_client is None:
        # Load OpenAI credentials only when this function owns evaluator setup.
        load_openai_environment()
        evaluator_client = build_openai_client()
    if creator_client is None:
        # Load OpenAI credentials only when this function owns creator setup.
        load_openai_environment()
        creator_client = build_openai_client()

    if status_callback:
        status_callback("Loading interpretation and Script 2/3 classification sources")

    # Load the interpretation and both supporting classification artifacts.
    (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        original_rules_artifact,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    ) = load_review_source_artifacts(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
    )

    # Build the evaluator prompt from the current interpretation and its source evidence.
    evaluator_messages = build_review_evaluator_messages(
        interpretation_path=selected_interpretation_path,
        original_rules_artifact=original_rules_artifact,
        interpretation_markdown=interpretation_markdown,
        classification_path=selected_classification_path,
        payment_classification=classification_data,
        overtime_clause_classification_path=selected_overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
    )

    if status_callback:
        status_callback(f"Awaiting evaluator model: {selected_evaluator_model}")

    current_evaluator_messages = evaluator_messages
    evaluator_output_text = ""
    evaluator_feedback_data: dict[str, Any] = {}
    evaluator_feedback_markdown = ""
    last_evaluator_validation_error = ""

    for attempt_number in range(MAX_EVALUATOR_REPAIR_ATTEMPTS + 1):
        # Log the evaluator model-call budget before sending the request.
        log_model_call_budget(
            status_callback,
            call_label="script_3b_evaluator_review",
            model=selected_evaluator_model,
            payload=current_evaluator_messages,
            max_output_tokens=selected_evaluator_max_output_tokens,
        )
        evaluator_response = evaluator_client.responses.create(
            model=selected_evaluator_model,
            input=current_evaluator_messages,
            max_output_tokens=selected_evaluator_max_output_tokens,
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
            evaluator_output_text = extract_chat_response_text(evaluator_response)
        if not evaluator_output_text:
            last_evaluator_validation_error = (
                "Evaluator response did not include output text."
            )
            if attempt_number >= MAX_EVALUATOR_REPAIR_ATTEMPTS:
                raise OvertimeInterpretationReviewError(
                    last_evaluator_validation_error
                )
            if status_callback:
                status_callback(
                    "Evaluator response was empty; requesting one corrected response."
                )
            current_evaluator_messages = build_evaluator_repair_messages(
                current_evaluator_messages,
                validation_error=last_evaluator_validation_error,
                prior_response_text="<empty response>",
            )
            continue
        try:
            evaluator_feedback_data = validate_review_feedback_artifact(
                extract_json_object_from_text(evaluator_output_text),
                original_rules_artifact["rules"],
            )
            evaluator_feedback_markdown = str(evaluator_feedback_data["summary_markdown"])
            break
        except (json.JSONDecodeError, ValueError) as error:
            last_evaluator_validation_error = str(error)
            if attempt_number >= MAX_EVALUATOR_REPAIR_ATTEMPTS:
                raise OvertimeInterpretationReviewError(
                    "Evaluator response could not be validated as structured JSON: "
                    f"{last_evaluator_validation_error}"
                )

            if status_callback:
                status_callback(
                    "Evaluator response failed validation; requesting one corrected response."
                )
            current_evaluator_messages = build_evaluator_repair_messages(
                current_evaluator_messages,
                validation_error=last_evaluator_validation_error,
                prior_response_text=evaluator_output_text,
            )

    if status_callback:
        status_callback("Evaluator processed feedback")
        status_callback(f"Awaiting creator update model: {selected_creator_model}")

    if inter_call_delay_seconds > 0:
        if status_callback:
            status_callback(
                "Waiting "
                f"{inter_call_delay_seconds:.1f} seconds before creator update."
            )
        # Pause between calls when requested so the review workflow is easier to monitor and budget.
        time.sleep(inter_call_delay_seconds)

    # Build the creator prompt from the original interpretation plus evaluator feedback.
    creator_messages = build_review_creator_messages(
        interpretation_path=selected_interpretation_path,
        original_rules_artifact=original_rules_artifact,
        interpretation_markdown=interpretation_markdown,
        classification_path=selected_classification_path,
        payment_classification=classification_data,
        overtime_clause_classification_path=selected_overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
    )
    # Log the creator model-call budget before sending the revision request.
    log_model_call_budget(
        status_callback,
        call_label="script_3b_creator_revision",
        model=selected_creator_model,
        payload=creator_messages,
        max_output_tokens=selected_creator_max_output_tokens,
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
            model=selected_creator_model,
            input=current_creator_messages,
            max_output_tokens=selected_creator_max_output_tokens,
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
                original_rules=original_rules_artifact["rules"],
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
            break
        except json.JSONDecodeError as exc:
            last_validation_error = f"Creator response was not valid JSON: {exc}"
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
        creator_response_markdown = fallback_creator_response_markdown(
            validation_error=last_validation_error or "Unknown validation error.",
            creator_output_text=creator_output_text,
        )
        revised_interpretation_markdown = str(
            original_rules_artifact["rendered_markdown"]
        )
        reviewed_rules_artifact = {
            "rules": list(original_rules_artifact["rules"]),
            "review_decisions": [
                {
                    "rule_id": rule.rule_id,
                    "evaluator_recommendation": "keep",
                    "creator_decision": "keep",
                    "final_decision": "kept",
                    "reason": "Preserved original rules after creator validation failure.",
                }
                for rule in original_rules_artifact["rules"]
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

    feedback_path = (
        Path(feedback_output_path)
        if feedback_output_path
        else evaluator_feedback_path_for_interpretation(selected_interpretation_path)
    )
    creator_response_path = (
        Path(creator_response_output_path)
        if creator_response_output_path
        else creator_response_path_for_interpretation(selected_interpretation_path)
    )
    revised_path = (
        Path(revised_output_path)
        if revised_output_path
        else revised_output_path_for_interpretation(selected_interpretation_path)
    )
    feedback_json_path = decision_output_path_for_markdown(feedback_path)
    creator_response_json_path = decision_output_path_for_markdown(creator_response_path)
    revised_json_path = json_output_path_for_markdown(revised_path)
    revised_validation_warnings = clause_coverage_warnings(
        original_rules=original_rules_artifact["rules"],
        revised_rules=reviewed_rules_artifact["rules"],
        context_label="Original step 3.4",
    )
    revised_interpretation_markdown = prepend_validation_warnings(
        revised_interpretation_markdown,
        revised_validation_warnings,
    )

    if status_callback:
        if last_validation_error and reviewed_rules_artifact is not None:
            status_callback(
                "Writing feedback and revised interpretation. "
                "Any creator validation failure has been recorded for manual review."
            )
        else:
            status_callback("Writing feedback, creator response, and revised interpretation")

    # Save each output artifact separately so the review trail remains auditable.
    write_text_with_archive(feedback_path, evaluator_feedback_markdown)
    write_text_with_archive(
        feedback_json_path,
        json.dumps(
            make_json_serializable(evaluator_feedback_data),
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_text_with_archive(creator_response_path, creator_response_markdown)
    write_text_with_archive(
        creator_response_json_path,
        json.dumps(
            make_json_serializable(creator_response_data),
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_rules_artifact(
        json_path=revised_json_path,
        markdown_path=revised_path,
        artifact={
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "source_classification_file": str(selected_classification_path),
            "source_clause_classification_file": str(
                selected_overtime_clause_classification_path
            ),
            "source_original_rules_file": str(
                json_output_path_for_markdown(selected_interpretation_path)
            ),
            "source_evaluator_feedback_file": str(feedback_json_path),
            "review_decisions": reviewed_rules_artifact["review_decisions"],
            "rendered_markdown": revised_interpretation_markdown,
            "validation_warnings": revised_validation_warnings,
            "rules": [
                rule_to_dict(rule) for rule in reviewed_rules_artifact["rules"]
            ],
        },
    )

    if status_callback:
        status_callback("Review update complete")

    return OvertimeInterpretationReviewArtifacts(
        evaluator_feedback_path=feedback_path,
        evaluator_feedback_json_path=feedback_json_path,
        creator_response_path=creator_response_path,
        creator_response_json_path=creator_response_json_path,
        revised_interpretation_path=revised_path,
        revised_interpretation_json_path=revised_json_path,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_response_markdown=creator_response_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
    )


# 6. Main orchestration


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the one-pass step-3B review command."""
    parser = argparse.ArgumentParser(
        description="Run one-pass supervisor feedback and creator update for a step 3 overtime interpretation."
    )
    parser.add_argument(
        "award_or_interpretation_path",
        nargs="?",
        default="MA000018",
        help=(
            "Award code such as MA000002, or a path to an overtime interpretation "
            "markdown file."
        ),
    )
    parser.add_argument(
        "--classification-path",
        default=None,
        help=(
            "Optional path to the payment classification JSON file. If omitted, "
            "the path is derived from the award code or interpretation filename."
        ),
    )
    parser.add_argument(
        "--overtime-clause-classification-path",
        default=None,
        help=(
            "Optional path to the Script 3 intermediate overtime clause classification "
            "JSON. If omitted, the path is derived from the payment classification path."
        ),
    )
    parser.add_argument(
        "--evaluator-model",
        default=None,
        help=f"OpenAI evaluator model to use. Defaults to {EVALUATOR_MODEL}.",
    )
    parser.add_argument(
        "--creator-model",
        default=None,
        help=(
            "OpenAI creator model to use. Defaults to "
            f"OVERTIME_INTERPRETATION_REVIEW_CREATOR_MODEL or {DEFAULT_CREATOR_MODEL}."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the one-pass step-3B review workflow from the command line."""
    # Read the CLI inputs that determine which interpretation and supporting files to review.
    args = parse_args(argv)
    # Resolve the interpretation markdown path from either an award code or an explicit file path.
    interpretation_path = resolve_interpretation_path(args.award_or_interpretation_path)
    # Resolve the payment-classification source that belongs to this interpretation.
    classification_path = resolve_classification_path(
        args.award_or_interpretation_path,
        args.classification_path,
    )
    # Resolve the step-3 clause-classification source that belongs to the payment classification.
    overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        classification_path,
        args.overtime_clause_classification_path,
    )

    print(f"Starting overtime interpretation review for {interpretation_path}")
    print(f"Using classification source {classification_path}")
    print(f"Using overtime clause classification source {overtime_clause_classification_path}")

    # Run the evaluator-plus-creator review loop and print status updates as it progresses.
    artifacts = review_overtime_interpretation(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        evaluator_model=args.evaluator_model,
        creator_model=args.creator_model,
        status_callback=lambda message: print(f"Status: {message}"),
    )

    print(f"Evaluator feedback saved to {artifacts.evaluator_feedback_path}")
    print(f"Creator response saved to {artifacts.creator_response_path}")
    print(f"Revised overtime interpretation saved to {artifacts.revised_interpretation_path}")


if __name__ == "__main__":
    main()
