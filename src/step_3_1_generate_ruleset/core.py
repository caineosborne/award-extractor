"""Shared logic for step 3.1 ruleset generation."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.active_pipeline_paths import interpretation_output_path_for_classification
from src.common.llm_io import extract_response_text
from src.common.overtime_rules import (
    ALLOWED_EMPLOYEE_COHORTS,
    ALLOWED_WORK_ARRANGEMENTS,
    OvertimeRule,
    build_step_3_rules_artifact,
    employee_cohort_from_employee_scope,
    employee_scope_from_employee_cohort,
    json_output_path_for_markdown,
    make_json_serializable,
    rules_from_markdown_fallback,
    rule_to_dict,
    validate_rule_list,
    write_rules_artifact,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
    explicit_ruleset_output_path,
    overtime_ruleset_config,
)
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_runtime import load_openai_environment
from src.prompts.step_3_1_generate_ruleset import (
    build_expert_comparison_messages,
    build_interpretation_messages,
)
from src.step_2_2_classify_overtime_clauses.core import (
    DEFAULT_MODEL as STEP_2_2_DEFAULT_MODEL,
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    load_classification,
    load_overtime_clause_classification_artifact,
    overtime_clause_classification_path_for_source,
    select_overtime_creation_clauses,
    select_ruleset_related_clauses,
)


DEFAULT_MODEL = STEP_2_2_DEFAULT_MODEL
DEFAULT_EXPERT_RUN_COUNT = 2
RULE_ID_ALLOWED_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CLAUSE_REFERENCE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b",
    re.IGNORECASE,
)
CLAUSE_REFERENCE_FULL_PATTERN = re.compile(
    r"^\d+(?:\.\d+)+(?:\([a-z0-9]+\))*$",
    re.IGNORECASE,
)
EXPERT_RUN_LABELS = ("expert_a", "expert_b", "expert_c")


@dataclass(frozen=True)
class Step3GenerationInputs:
    """Prepared step 3.1 inputs after deterministic loading and validation."""

    source_path: Path
    clause_classification_path: Path
    destination: Path
    json_destination: Path
    clause_classifications: list[OvertimeClauseClassification]
    overtime_creation_clauses: list[OvertimeClauseClassification]
    ruleset_key: str


def load_environment(env_path: Path | str = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load and validate the OpenAI environment used by step 3.1."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


def parse_response_json(output_text: str) -> Mapping[str, Any]:
    """Parse the model's JSON text into a Python mapping."""
    return json.loads(output_text)


def deduplicate_preserving_order(items: Sequence[str]) -> list[str]:
    """Remove duplicates while keeping the first-seen order."""
    unique_items: list[str] = []
    seen_items: set[str] = set()

    for item in items:
        if item in seen_items:
            continue
        unique_items.append(item)
        seen_items.add(item)

    return unique_items


def candidate_parent_clause_keys(clause_reference: str) -> list[str]:
    """Return progressively broader clause keys for source-clause matching."""
    candidates = [clause_reference]
    simplified = re.sub(
        r"(?:\([a-z0-9]+\))+$",
        "",
        clause_reference,
        flags=re.IGNORECASE,
    )
    if simplified not in candidates:
        candidates.append(simplified)

    dotted_parts = simplified.split(".")
    while len(dotted_parts) > 1:
        dotted_parts = dotted_parts[:-1]
        candidate = ".".join(dotted_parts)
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def employee_cohort_display(employee_cohort: str) -> str:
    if employee_cohort == "full-time":
        return "full-time employees"
    if employee_cohort == "part-time":
        return "part-time employees"
    if employee_cohort == "casual":
        return "casual employees"
    if employee_cohort == "permanent":
        return "permanent employees"
    return "all employees"


def work_arrangement_display(work_arrangement: str) -> str:
    if work_arrangement == "day-worker":
        return "day workers"
    if work_arrangement == "shiftworker":
        return "shiftworkers"
    return "all work arrangements"


def combined_employee_cohort(
    classifications: Sequence[OvertimeClauseClassification],
) -> str:
    combined_scope: list[str] = []

    for classification in classifications:
        combined_scope.extend(
            employee_scope_from_employee_cohort(classification.employee_cohort)
        )

    return employee_cohort_from_employee_scope(combined_scope)


def combined_work_arrangement(
    classifications: Sequence[OvertimeClauseClassification],
) -> str:
    arrangements = {
        classification.work_arrangement
        for classification in classifications
        if classification.work_arrangement
    }

    if "all" in arrangements or len(arrangements) != 1:
        return "all"

    return next(iter(arrangements))


def combined_other_scope_notes(
    classifications: Sequence[OvertimeClauseClassification],
) -> str:
    notes: list[str] = []

    for classification in classifications:
        note = classification.other_scope_notes.strip()
        if note and note not in notes:
            notes.append(note)

    return "; ".join(notes)


def scope_validation_warnings_for_rule(
    rule: OvertimeRule,
    source_classifications: Sequence[OvertimeClauseClassification],
) -> list[str]:
    warnings: list[str] = []

    if not source_classifications:
        return warnings

    expected_employee_cohort = combined_employee_cohort(source_classifications)
    actual_employee_cohort = rule.employee_cohort
    if actual_employee_cohort != expected_employee_cohort:
        clause_numbers = ", ".join(
            classification.clause_number for classification in source_classifications
        )
        warnings.append(
            f"Rule '{rule.rule_id}' draws on clause {clause_numbers}, which is classified "
            f"as applying to {employee_cohort_display(expected_employee_cohort)}, but the "
            f"rule is written as applying to {employee_cohort_display(actual_employee_cohort)}."
        )

    expected_work_arrangement = combined_work_arrangement(source_classifications)
    if rule.work_arrangement != expected_work_arrangement:
        clause_numbers = ", ".join(
            classification.clause_number for classification in source_classifications
        )
        warnings.append(
            f"Rule '{rule.rule_id}' draws on clause {clause_numbers}, which is classified "
            f"as applying to {work_arrangement_display(expected_work_arrangement)}, but the "
            f"rule is written as applying to {work_arrangement_display(rule.work_arrangement)}."
        )

    expected_other_scope_notes = combined_other_scope_notes(source_classifications)
    if expected_other_scope_notes and rule.other_scope_notes.strip() != expected_other_scope_notes:
        clause_numbers = ", ".join(
            classification.clause_number for classification in source_classifications
        )
        warnings.append(
            f"Rule '{rule.rule_id}' draws on clause {clause_numbers}, which is classified "
            f"with the scope note '{expected_other_scope_notes}', but the rule now records "
            f"'{rule.other_scope_notes.strip() or 'no additional scope note'}'."
        )

    return warnings


def missing_shortlisted_clause_warning(
    clause_number: str,
    *,
    ruleset_label: str,
) -> str:
    """Return a reviewer-friendly warning when a shortlisted clause is missing."""
    return (
        f"Clause {clause_number} was identified as relevant to overtime, "
        f"but it is not present in the {ruleset_label}."
    )


def interpretation_output_path_for_source(
    classification_path: Path | str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> Path:
    """Return the default markdown interpretation path for step 3.1."""
    if ruleset_key == OVERTIME_CREATION_RULESET:
        return interpretation_output_path_for_classification(classification_path)
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        return explicit_ruleset_output_path(classification_path, ruleset_key)
    raise ValueError(f"Unsupported overtime ruleset: {ruleset_key}")


def output_path_for_classification(classification_path: Path | str) -> Path:
    """Return the interpretation path using the legacy helper name."""
    return interpretation_output_path_for_source(classification_path)


def expert_markdown_output_path(base_markdown_path: Path | str, label: str) -> Path:
    """Return the sibling markdown path used for one expert run."""
    path = Path(base_markdown_path)
    return path.with_name(f"{path.stem}_{label}{path.suffix}")


def comparison_output_path(base_markdown_path: Path | str) -> Path:
    """Return the JSON path used for the expert-comparison artifact."""
    path = Path(base_markdown_path)
    return path.with_name(f"{path.stem}_comparison.json")


def interpretation_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from the interpretation model."""
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


def validate_interpretation_rules(
    response_data: Mapping[str, Any],
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Validate the structured rule output from the interpretation model."""
    config = overtime_ruleset_config(ruleset_key)
    supported_classification_label = (
        "creation"
        if ruleset_key == OVERTIME_CREATION_RULESET
        else config.display_name.lower()
    )
    missing_clause_ruleset_label = (
        "draft ruleset before review"
        if ruleset_key == OVERTIME_CREATION_RULESET
        else f"{config.display_name.lower()} ruleset"
    )
    raw_rules = response_data.get("rules")
    if not isinstance(raw_rules, list):
        raise OvertimeInterpretationError("Interpretation response must contain rules array.")

    validation_warnings: list[str] = []
    normalized_raw_rules, duplicate_rule_id_warnings = normalize_duplicate_rule_ids(
        raw_rules,
        context_label="Interpretation output",
    )
    validation_warnings.extend(duplicate_rule_id_warnings)
    rules = validate_rule_list(normalized_raw_rules)
    valid_clause_numbers: set[str] = set()
    for classification in overtime_creation_clauses:
        valid_clause_numbers.add(classification.clause_number)
        for clause_reference_match in CLAUSE_REFERENCE_PATTERN.finditer(
            classification.clause_text
        ):
            valid_clause_numbers.add(clause_reference_match.group(0))

    valid_classifications = set(config.generation_classifications)
    shortlisted_clause_numbers = {
        classification.clause_number for classification in overtime_creation_clauses
    }
    represented_shortlisted_clause_numbers: set[str] = set()

    for raw_rule, rule in zip(normalized_raw_rules, rules):
        if not RULE_ID_ALLOWED_PATTERN.fullmatch(rule.rule_id):
            raise OvertimeInterpretationError(
                f"Rule id contains unsupported characters: {rule.rule_id}"
            )

        malformed_source_clauses = {
            clause_reference
            for clause_reference in rule.source_clause_numbers
            if not CLAUSE_REFERENCE_FULL_PATTERN.fullmatch(clause_reference)
        }
        if malformed_source_clauses:
            malformed_display = ", ".join(sorted(malformed_source_clauses))
            validation_warnings.append(
                f"Rule {rule.rule_id} referenced malformed source clauses: "
                f"{malformed_display}."
            )

        known_source_clauses: set[str] = set()
        for source_clause in rule.source_clause_numbers:
            for candidate in candidate_parent_clause_keys(source_clause):
                if candidate in valid_clause_numbers:
                    known_source_clauses.add(candidate)
                    if candidate in shortlisted_clause_numbers:
                        represented_shortlisted_clause_numbers.add(candidate)
                    break
        if not known_source_clauses:
            source_display = ", ".join(rule.source_clause_numbers)
            validation_warnings.append(
                f"Rule {rule.rule_id} is included despite not being linked to a known "
                f"shortlisted step-3 source clause. Returned source clauses: "
                f"{source_display}."
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

        unsupported_source_classifications = (
            set(rule.source_classifications) - valid_classifications
        )
        supported_source_classifications = (
            set(rule.source_classifications) & valid_classifications
        )
        if unsupported_source_classifications and not supported_source_classifications:
            unsupported_display = ", ".join(sorted(unsupported_source_classifications))
            validation_warnings.append(
                f"Rule {rule.rule_id} is included despite not being listed as a useful "
                f"clause classification. Returned source classifications: "
                f"{unsupported_display}."
            )
        elif unsupported_source_classifications:
            unsupported_display = ", ".join(sorted(unsupported_source_classifications))
            supported_display = ", ".join(sorted(supported_source_classifications))
            validation_warnings.append(
                f"Rule {rule.rule_id} cited additional non-creation classifications "
                f"({unsupported_display}) but was accepted because it also contains an "
                f"allowed {supported_classification_label} classification ({supported_display})."
            )

    missing_shortlisted_clauses = (
        shortlisted_clause_numbers - represented_shortlisted_clause_numbers
    )
    for clause_number in sorted(missing_shortlisted_clauses):
        validation_warnings.append(
            missing_shortlisted_clause_warning(
                clause_number,
                ruleset_label=missing_clause_ruleset_label,
            )
        )

    return rules, validation_warnings


def normalize_duplicate_rule_ids(
    raw_rules: Sequence[Any],
    *,
    context_label: str,
) -> tuple[list[Any], list[str]]:
    """Rename duplicate rule ids so validation can continue with explicit warnings."""
    normalized_rules: list[Any] = []
    validation_warnings: list[str] = []
    seen_rule_id_counts: dict[str, int] = {}

    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, Mapping):
            normalized_rules.append(raw_rule)
            continue

        normalized_rule = dict(raw_rule)
        original_rule_id = str(normalized_rule.get("rule_id") or "").strip()
        if not original_rule_id:
            normalized_rules.append(normalized_rule)
            continue

        current_count = seen_rule_id_counts.get(original_rule_id, 0) + 1
        seen_rule_id_counts[original_rule_id] = current_count

        if current_count == 1:
            normalized_rules.append(normalized_rule)
            continue

        updated_rule_id = f"{original_rule_id}-{current_count}"
        normalized_rule["rule_id"] = updated_rule_id
        normalized_rules.append(normalized_rule)
        validation_warnings.append(
            f"{context_label} returned duplicate rule_id `{original_rule_id}`. "
            f"Rule {index} was renamed to `{updated_rule_id}`."
        )

    return normalized_rules, validation_warnings


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


def request_structured_interpretation_run(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str], str]:
    """Run one expert interpretation pass and return structured rules."""
    config = overtime_ruleset_config(ruleset_key)
    try:
        response = client.responses.create(
            model=model,
            input=build_interpretation_messages(
                str(source_path),
                overtime_creation_clauses,
                ruleset_key,
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


def comparison_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from the comparison model."""
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


def compare_expert_interpretation_runs(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
    run_a_rules: Sequence[OvertimeRule],
    run_b_rules: Sequence[OvertimeRule],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], dict[str, Any], list[str]]:
    """Merge two expert rule sets using a comparison pass."""
    config = overtime_ruleset_config(ruleset_key)
    messages = build_expert_comparison_messages(
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        run_a_rules=run_a_rules,
        run_b_rules=run_b_rules,
        ruleset_key=ruleset_key,
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


def load_prepared_clause_classifications(
    source_path: Path,
    classification_output_path: Path,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Load part-1 output and validate it against the current step-2 source."""
    if not classification_output_path.exists():
        raise OvertimeInterpretationError(
            "Overtime clause classification JSON not found: "
            f"{classification_output_path}. Run step 3 part 1 first."
        )

    data = load_classification(source_path)
    overtime_clauses = select_ruleset_related_clauses(
        data,
        OVERTIME_CREATION_RULESET,
    )
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No overtime source clauses found in: {source_path}"
        )

    return load_overtime_clause_classification_artifact(
        classification_output_path,
        overtime_clauses,
        OVERTIME_CREATION_RULESET,
    )
