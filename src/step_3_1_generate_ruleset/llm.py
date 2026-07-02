"""LLM helpers for step 3.1 ruleset generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.overtime_rules import OvertimeRule, rule_to_dict, rules_from_markdown_fallback, validate_rule_list
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET, overtime_ruleset_config
from src.common.pipeline_runtime import load_openai_environment
from src.prompts.step_3_1_generate_ruleset import (
    build_expert_comparison_messages,
    build_interpretation_messages,
)

from .core import (
    DEFAULT_MODEL,
    OvertimeInterpretationError,
    candidate_parent_clause_keys,
    comparison_output_path,
    normalize_duplicate_merged_rule_ids,
    normalize_duplicate_rule_ids,
    missing_shortlisted_clause_warning,
    scope_validation_warnings_for_rule,
    validate_interpretation_rules,
)


def load_environment(env_path: Path | str = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load and validate the OpenAI environment used by step 3.1."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 3.1 client."""
    load_environment()
    return OpenAI()


def selected_models(
    *,
    model: str | None,
    comparison_model: str | None,
) -> tuple[str, str]:
    """Resolve the generation and comparison models for step 3.1."""
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    selected_comparison_model = comparison_model or os.getenv(
        "OVERTIME_INTERPRETATION_COMPARISON_MODEL",
        selected_model,
    )
    return selected_model, selected_comparison_model


def parse_response_json(output_text: str) -> Any:
    """Parse the model's JSON text into Python data."""
    return json.loads(output_text)


def request_structured_interpretation_run(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str], str]:
    """Run one expert interpretation pass and return structured rules."""
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

    try:
        response_data = parse_response_json(output_text)
        structured_rules, validation_warnings = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
            ruleset_key,
        )
    except json.JSONDecodeError:
        structured_rules = rules_from_markdown_fallback(
            output_text,
            source_path=source_path,
        )
        validation_warnings = [
            "The step 3.1 model did not return valid JSON. A markdown fallback parser was "
            "used to rebuild the rules artifact."
        ]

    return structured_rules, validation_warnings, output_text


def draft_expert_a(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run expert A for step 3.1."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def draft_expert_b(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run expert B for step 3.1."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def draft_additional_expert(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run any additional expert draft beyond expert A and B."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def compare_expert_interpretation_runs(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    run_a_rules: list[OvertimeRule],
    run_b_rules: list[OvertimeRule],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], dict[str, Any], list[str]]:
    """Merge two expert rule sets using a comparison pass."""
    config = overtime_ruleset_config(ruleset_key)
    messages = build_expert_comparison_messages(
        ruleset_key=ruleset_key,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        run_a_rules=run_a_rules,
        run_b_rules=run_b_rules,
    )
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": config.comparison_schema_name,
                    "schema": comparison_response_json_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI comparison request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError(
            "OpenAI comparison response did not include output text."
        )

    try:
        comparison_data = parse_response_json(output_text)
    except json.JSONDecodeError as exc:
        raise OvertimeInterpretationError("Comparison response was not valid JSON.") from exc

    raw_merged_rules, normalized_merge_explanations, duplicate_rule_id_warnings = (
        normalize_duplicate_merged_rule_ids(comparison_data)
    )
    merged_rules = validate_rule_list(raw_merged_rules)
    validation_warnings: list[str] = list(duplicate_rule_id_warnings)

    run_a_rule_ids = {rule.rule_id for rule in run_a_rules}
    run_b_rule_ids = {rule.rule_id for rule in run_b_rules}
    accounted_run_a_rule_ids = {
        str(rule_id) for rule_id in comparison_data.get("accounted_run_a_rule_ids", [])
    }
    accounted_run_b_rule_ids = {
        str(rule_id) for rule_id in comparison_data.get("accounted_run_b_rule_ids", [])
    }

    missing_run_a_rule_ids = sorted(run_a_rule_ids - accounted_run_a_rule_ids)
    missing_run_b_rule_ids = sorted(run_b_rule_ids - accounted_run_b_rule_ids)
    if missing_run_a_rule_ids:
        validation_warnings.append(
            "The comparison output did not account for every run A rule_id: "
            + ", ".join(missing_run_a_rule_ids)
            + "."
        )
    if missing_run_b_rule_ids:
        validation_warnings.append(
            "The comparison output did not account for every run B rule_id: "
            + ", ".join(missing_run_b_rule_ids)
            + "."
        )

    shortlisted_clause_numbers = {
        classification.clause_number for classification in overtime_creation_clauses
    }
    represented_clause_numbers: set[str] = set()
    for raw_rule, rule in zip(raw_merged_rules, merged_rules):
        known_source_clauses: set[str] = set()
        for clause_number in rule.source_clause_numbers:
            candidate_keys = candidate_parent_clause_keys(clause_number)
            represented_clause_numbers.update(candidate_keys)
            known_source_clauses.update(
                candidate
                for candidate in candidate_keys
                if candidate in shortlisted_clause_numbers
            )

        matching_source_classifications = [
            classification
            for classification in overtime_creation_clauses
            if classification.clause_number in known_source_clauses
        ]
        raw_scope_fields_present = isinstance(raw_rule, dict) and any(
            field_name in raw_rule
            for field_name in (
                "employee_cohort",
                "work_arrangement",
                "other_scope_notes",
            )
        )
        if raw_scope_fields_present:
            validation_warnings.extend(
                scope_validation_warnings_for_rule(
                    rule,
                    matching_source_classifications,
                )
            )

    missing_shortlisted_clause_numbers = sorted(
        clause_number
        for clause_number in shortlisted_clause_numbers
        if clause_number not in represented_clause_numbers
    )
    for clause_number in missing_shortlisted_clause_numbers:
        validation_warnings.append(
            missing_shortlisted_clause_warning(
                clause_number,
                ruleset_label=f"merged {config.display_name.lower()} expert comparison ruleset",
            )
        )

    comparison_metadata = {
        "comparison_summary_markdown": str(
            comparison_data.get("comparison_summary_markdown") or ""
        ).strip(),
        "accounted_run_a_rule_ids": sorted(accounted_run_a_rule_ids),
        "accounted_run_b_rule_ids": sorted(accounted_run_b_rule_ids),
        "merge_explanations": normalized_merge_explanations,
    }
    return merged_rules, comparison_metadata, validation_warnings


def merge_expert_drafts(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    run_a_rules: list[OvertimeRule],
    run_b_rules: list[OvertimeRule],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], dict[str, Any], list[str]]:
    """Merge expert A and expert B into one ruleset."""
    return compare_expert_interpretation_runs(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        run_a_rules=run_a_rules,
        run_b_rules=run_b_rules,
        ruleset_key=ruleset_key,
    )


def interpretation_response_json_schema() -> dict[str, Any]:
    from src.common.overtime_rules import ALLOWED_EMPLOYEE_COHORTS, ALLOWED_WORK_ARRANGEMENTS

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


def comparison_response_json_schema() -> dict[str, Any]:
    from src.common.overtime_rules import ALLOWED_EMPLOYEE_COHORTS, ALLOWED_WORK_ARRANGEMENTS

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "comparison_summary_markdown": {"type": "string"},
            "accounted_run_a_rule_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "accounted_run_b_rule_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "merged_rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rule_id": {"type": "string"},
                        "section_heading": {"type": "string"},
                        "employee_scope": {"type": "array", "items": {"type": "string"}},
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
            },
            "merge_explanations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "merged_rule_id": {"type": "string"},
                        "run_a_rule_ids": {"type": "array", "items": {"type": "string"}},
                        "run_b_rule_ids": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "merged_rule_id",
                        "run_a_rule_ids",
                        "run_b_rule_ids",
                        "reason",
                    ],
                },
            },
        },
        "required": [
            "comparison_summary_markdown",
            "accounted_run_a_rule_ids",
            "accounted_run_b_rule_ids",
            "merged_rules",
            "merge_explanations",
        ],
    }
