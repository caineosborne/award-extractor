"""Step 3.1 stage 4: combine expert A and expert B into one reviewed ruleset."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.common.llm_io import extract_response_text
from src.common.prompt_logging import log_llm_prompt
from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
)
from src.common.overtime_rules import OvertimeRule, validate_rule_list
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET, overtime_ruleset_config
from src.prompts.step_3_1_generate_ruleset import build_expert_comparison_messages

from .step_3_apply_deterministic_checks import (
    candidate_parent_clause_keys,
    missing_shortlisted_clause_warning,
    normalize_duplicate_rule_ids,
    parse_response_json,
    scope_validation_warnings_for_rule,
)


def comparison_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from the combination model."""
    from src.common.overtime_rules import (
        ALLOWED_EMPLOYEE_COHORTS,
        ALLOWED_WORK_ARRANGEMENTS,
    )

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


def normalize_duplicate_merged_rule_ids(
    comparison_data: Mapping[str, Any],
) -> tuple[list[Any], list[dict[str, Any]], list[str]]:
    """Rename duplicate merged rule ids and keep merge explanations aligned."""
    raw_merged_rules = comparison_data.get("merged_rules", [])
    merge_explanations = comparison_data.get("merge_explanations", [])
    normalized_raw_rules, validation_warnings = normalize_duplicate_rule_ids(
        raw_merged_rules,
        context_label="Comparison output",
    )

    occurrence_tracker: dict[str, int] = {}
    renamed_rule_ids: list[str] = []
    for raw_rule in normalized_raw_rules:
        if not isinstance(raw_rule, Mapping):
            renamed_rule_ids.append("")
            continue

        renamed_rule_ids.append(str(raw_rule.get("rule_id") or "").strip())

    normalized_merge_explanations: list[dict[str, Any]] = []
    for explanation in merge_explanations:
        if not isinstance(explanation, Mapping):
            continue

        normalized_explanation = dict(explanation)
        original_rule_id = str(normalized_explanation.get("merged_rule_id") or "").strip()
        if original_rule_id:
            occurrence_tracker[original_rule_id] = occurrence_tracker.get(original_rule_id, 0) + 1
            occurrence_index = occurrence_tracker[original_rule_id]

            matching_rule_id = ""
            matching_count = 0
            for renamed_rule_id in renamed_rule_ids:
                if not renamed_rule_id:
                    continue
                if renamed_rule_id == original_rule_id or renamed_rule_id.startswith(
                    f"{original_rule_id}-"
                ):
                    matching_count += 1
                    if matching_count == occurrence_index:
                        matching_rule_id = renamed_rule_id
                        break

            if matching_rule_id:
                normalized_explanation["merged_rule_id"] = matching_rule_id

        normalized_merge_explanations.append(normalized_explanation)

    return normalized_raw_rules, normalized_merge_explanations, validation_warnings


def combine_expert_rulesets(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
    expert_a_rules: Sequence[OvertimeRule],
    expert_b_rules: Sequence[OvertimeRule],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], dict[str, Any], list[str]]:
    """Merge expert A and expert B into one validated ruleset."""
    config = overtime_ruleset_config(ruleset_key)
    messages = build_expert_comparison_messages(
        ruleset_key=ruleset_key,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        run_a_rules=expert_a_rules,
        run_b_rules=expert_b_rules,
    )
    log_llm_prompt(f"3.1 {config.display_name} Expert Comparison", messages)
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "medium"},
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

    run_a_rule_ids = {rule.rule_id for rule in expert_a_rules}
    run_b_rule_ids = {rule.rule_id for rule in expert_b_rules}
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
        raw_scope_fields_present = isinstance(raw_rule, Mapping) and any(
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
                ruleset_subject_label=(
                    "overtime"
                    if ruleset_key == OVERTIME_CREATION_RULESET
                    else config.display_name.lower()
                ),
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
