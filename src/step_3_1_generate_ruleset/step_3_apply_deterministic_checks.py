"""Step 3.1 stage 3: apply deterministic validation to one expert draft."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
)
from src.common.overtime_rules import (
    OvertimeRule,
    employee_cohort_from_employee_scope,
    employee_scope_from_employee_cohort,
    rules_from_markdown_fallback,
    validate_rule_list,
)
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET, overtime_ruleset_config

RULE_ID_ALLOWED_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CLAUSE_REFERENCE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b",
    re.IGNORECASE,
)
CLAUSE_REFERENCE_FULL_PATTERN = re.compile(
    r"^\d+(?:\.\d+)+(?:\([a-z0-9]+\))*$",
    re.IGNORECASE,
)


def parse_response_json(output_text: str) -> Mapping[str, Any]:
    """Parse the model's JSON text into a Python mapping."""
    return json.loads(output_text)


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
    """Render the reviewer-facing employee cohort label."""
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
    """Render the reviewer-facing work arrangement label."""
    if work_arrangement == "day-worker":
        return "day workers"
    if work_arrangement == "shiftworker":
        return "shiftworkers"
    return "all work arrangements"


def combined_employee_cohort(
    classifications: Sequence[OvertimeClauseClassification],
) -> str:
    """Collapse multiple source classifications into one expected cohort label."""
    combined_scope: list[str] = []

    for classification in classifications:
        combined_scope.extend(
            employee_scope_from_employee_cohort(classification.employee_cohort)
        )

    return employee_cohort_from_employee_scope(combined_scope)


def combined_work_arrangement(
    classifications: Sequence[OvertimeClauseClassification],
) -> str:
    """Collapse multiple source classifications into one expected work arrangement."""
    arrangements = {
        classification.work_arrangement
        for classification in classifications
        if classification.work_arrangement
    }

    if "all" in arrangements or len(arrangements) != 1:
        return "all"

    return next(iter(arrangements))


def scope_validation_warnings_for_rule(
    rule: OvertimeRule,
    source_classifications: Sequence[OvertimeClauseClassification],
) -> list[str]:
    """Return scope mismatch warnings for one rule."""
    warnings: list[str] = []

    if not source_classifications:
        return warnings

    if len(source_classifications) != 1:
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

    return warnings


def missing_shortlisted_clause_warning(
    clause_number: str,
    *,
    ruleset_subject_label: str,
    ruleset_label: str,
) -> str:
    """Return a reviewer-friendly warning when a shortlisted clause is missing."""
    return (
        f"Clause {clause_number} was identified as relevant to {ruleset_subject_label}, "
        f"but it is not present in the {ruleset_label}."
    )


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


def validate_interpretation_rules(
    output_text: str,
    *,
    source_path: Path,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Validate one expert draft against the shortlisted clause set."""
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
    missing_clause_subject_label = (
        "overtime" if ruleset_key == OVERTIME_CREATION_RULESET else config.display_name.lower()
    )

    try:
        response_data = parse_response_json(output_text)
    except json.JSONDecodeError:
        structured_rules = rules_from_markdown_fallback(
            output_text,
            source_path=source_path,
        )
        validation_warnings = [
            "The step 3.1 model did not return valid JSON. A markdown fallback parser was "
            "used to rebuild the rules artifact."
        ]
        return structured_rules, validation_warnings

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
                ruleset_subject_label=missing_clause_subject_label,
                ruleset_label=missing_clause_ruleset_label,
            )
        )

    return rules, validation_warnings
