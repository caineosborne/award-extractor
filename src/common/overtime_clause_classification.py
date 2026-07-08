"""Shared overtime clause classification helpers used across pipeline steps."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.active_pipeline_paths import (
    default_classification_path_for_award,
    ruleset_clause_classification_output_path_for_classification,
)
from src.common.overtime_rules import (
    ALLOWED_EMPLOYEE_COHORTS,
    ALLOWED_WORK_ARRANGEMENTS,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)

DEFAULT_CLASSIFICATION_PATH = default_classification_path_for_award("MA000018")
DEFAULT_MODEL = "gpt-5.4-mini"
SCHEMA_VERSION = "overtime-clause-classification-v3"
SUPPORTED_SCHEMA_VERSIONS = (
    "overtime-clause-classification-v2",
    SCHEMA_VERSION,
)
PENALTIES_CLASSIFICATION = "Penalty Rule"


class OvertimeInterpretationError(RuntimeError):
    """Base exception for overtime clause classification failures."""


@dataclass(frozen=True)
class OvertimeClauseClassification:
    """Store the classification outcome for one shortlisted clause."""

    clause_number: str
    classification: str
    clause_text: str
    explanation: str
    employee_cohort: str = "all"
    work_arrangement: str = "all"
    other_scope_notes: str = ""
    classifications: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Ensure the primary classification appears in the full category list."""
        if not self.classifications:
            object.__setattr__(self, "classifications", (self.classification,))


def load_classification(classification_path: Path | str) -> dict[str, Any]:
    """Load the step 2.1 payment classification artifact."""
    path = Path(classification_path)
    if not path.exists():
        raise OvertimeInterpretationError(f"Classification JSON not found: {path}")

    try:
        with path.open(encoding="utf-8") as classification_file:
            data = json.load(classification_file)
    except json.JSONDecodeError as exc:
        raise OvertimeInterpretationError(
            f"Classification JSON is not valid JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise OvertimeInterpretationError(
            f"Classification JSON must contain an object: {path}"
        )
    if not isinstance(data.get("classified_clauses"), dict):
        raise OvertimeInterpretationError(
            f"Classification JSON must contain classified_clauses object: {path}"
        )

    return data


def classification_output_path_for_source(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 2.2 output path for one step 2.1 input."""
    return ruleset_clause_classification_output_path_for_classification(
        classification_path,
        ruleset_key,
    )


def clause_source_text(clause: Mapping[str, Any]) -> str:
    """Return the stored clause text, or a JSON fallback when text is missing."""
    text = clause.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(clause, ensure_ascii=False)


def normalized_work_arrangement_from_clause_text(clause_text: str) -> str:
    """Return the work arrangement explicitly supported by the clause text."""
    normalized_text = clause_text.lower()

    if re.search(r"\bday[- ]workers?\b", normalized_text):
        return "day-worker"
    if re.search(r"\bshiftworkers?\b", normalized_text):
        return "shiftworker"
    if re.search(r"\bshiftwork\b", normalized_text):
        return "shiftworker"

    return "all"


def normalized_employee_cohort_from_clause_text(clause_text: str) -> str:
    """Return the employee cohort explicitly supported by the clause text."""
    normalized_text = clause_text.lower()

    has_full_time = bool(re.search(r"\bfull[- ]time\b", normalized_text))
    has_part_time = bool(re.search(r"\bpart[- ]time\b", normalized_text))
    has_casual = bool(re.search(r"\bcasual\b", normalized_text))

    if has_full_time and has_part_time and not has_casual:
        return "permanent"
    if has_full_time and not has_part_time and not has_casual:
        return "full-time"
    if has_part_time and not has_full_time and not has_casual:
        return "part-time"
    if has_casual and not has_full_time and not has_part_time:
        return "casual"

    return "all"


def select_ruleset_related_clauses(
    data: Mapping[str, Any],
    ruleset_or_source_tags: str | Sequence[str] = OVERTIME_CREATION_RULESET,
) -> dict[str, Any]:
    """Keep only clauses tagged as relevant for the requested ruleset."""
    classified_clauses = data.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        raise OvertimeInterpretationError("classified_clauses must be an object.")

    if isinstance(ruleset_or_source_tags, str):
        source_tags = overtime_ruleset_config(ruleset_or_source_tags).source_tags
    else:
        source_tags = tuple(ruleset_or_source_tags)

    shortlisted_clauses: dict[str, Any] = {}

    for clause_id, clause in classified_clauses.items():
        if not isinstance(clause, Mapping):
            continue

        if any(tag in clause.get("tags", []) for tag in source_tags):
            shortlisted_clauses[clause_id] = clause

    return shortlisted_clauses


def classification_response_json_schema(
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> dict[str, Any]:
    """Define the strict JSON schema expected from clause classification."""
    config = overtime_ruleset_config(ruleset_key)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "clauses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "clause_number": {"type": "string"},
                        "classification": {
                            "type": "string",
                            "enum": list(config.allowed_classifications),
                        },
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(config.allowed_classifications),
                            },
                            "minItems": 1,
                        },
                        "clause_text": {"type": "string"},
                        "explanation": {"type": "string"},
                        "employee_cohort": {
                            "type": "string",
                            "enum": list(ALLOWED_EMPLOYEE_COHORTS),
                        },
                        "work_arrangement": {
                            "type": "string",
                            "enum": list(ALLOWED_WORK_ARRANGEMENTS),
                        },
                        "other_scope_notes": {"type": "string"},
                    },
                    "required": [
                        "clause_number",
                        "classification",
                        "classifications",
                        "clause_text",
                        "explanation",
                        "employee_cohort",
                        "work_arrangement",
                        "other_scope_notes",
                    ],
                },
            },
        },
        "required": ["clauses"],
    }


def validate_overtime_clause_classifications(
    response_data: Mapping[str, Any],
    overtime_clauses: Mapping[str, Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Validate clause classifications against the shortlisted clause set."""
    config = overtime_ruleset_config(ruleset_key)
    raw_clauses = response_data.get("clauses")
    if not isinstance(raw_clauses, list):
        raise OvertimeInterpretationError(
            "Clause classification response must contain clauses array."
        )

    expected_clause_numbers = set(overtime_clauses)
    returned_clause_numbers: set[str] = set()
    clause_classifications: list[OvertimeClauseClassification] = []

    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, Mapping):
            raise OvertimeInterpretationError(
                "Clause classification items must be objects."
            )

        clause_number = str(raw_clause.get("clause_number") or "")
        classification = str(raw_clause.get("classification") or "")
        raw_classifications = raw_clause.get("classifications")
        explanation = str(raw_clause.get("explanation") or "")
        employee_cohort = str(raw_clause.get("employee_cohort") or "all").strip().lower()
        work_arrangement = str(raw_clause.get("work_arrangement") or "all").strip().lower()
        other_scope_notes = str(raw_clause.get("other_scope_notes") or "").strip()

        if clause_number not in expected_clause_numbers:
            raise OvertimeInterpretationError(
                f"Unknown overtime clause classification reference: {clause_number}"
            )
        if clause_number in returned_clause_numbers:
            raise OvertimeInterpretationError(
                f"Duplicate overtime clause classification reference: {clause_number}"
            )
        if classification not in config.allowed_classifications:
            raise OvertimeInterpretationError(
                f"Unsupported overtime clause classification: {classification}"
            )

        if raw_classifications is None:
            categories = (classification,)
        elif isinstance(raw_classifications, list):
            categories = tuple(str(item) for item in raw_classifications)
        else:
            raise OvertimeInterpretationError(
                f"Overtime clause classifications must be an array: {clause_number}"
            )

        if not categories:
            raise OvertimeInterpretationError(
                f"Overtime clause classifications are empty: {clause_number}"
            )

        unsupported_classifications = [
            item for item in categories if item not in config.allowed_classifications
        ]
        if unsupported_classifications:
            unsupported = ", ".join(unsupported_classifications)
            raise OvertimeInterpretationError(
                f"Unsupported overtime clause classifications for {clause_number}: "
                f"{unsupported}"
            )
        if classification not in categories:
            raise OvertimeInterpretationError(
                "Primary classification must be included in classifications: "
                f"{clause_number}"
            )
        if not explanation.strip():
            raise OvertimeInterpretationError(
                f"Overtime clause classification explanation is empty: {clause_number}"
            )
        if employee_cohort not in ALLOWED_EMPLOYEE_COHORTS:
            raise OvertimeInterpretationError(
                f"Unsupported employee cohort for {clause_number}: {employee_cohort}"
            )
        if work_arrangement not in ALLOWED_WORK_ARRANGEMENTS:
            raise OvertimeInterpretationError(
                f"Unsupported work arrangement for {clause_number}: {work_arrangement}"
            )

        source_clause = overtime_clauses[clause_number]
        if not isinstance(source_clause, Mapping):
            raise OvertimeInterpretationError(
                f"Overtime clause is not an object: {clause_number}"
            )

        supported_work_arrangement = normalized_work_arrangement_from_clause_text(
            clause_source_text(source_clause)
        )
        if work_arrangement == "day-worker" and supported_work_arrangement != "day-worker":
            work_arrangement = "all"
        elif (
            work_arrangement == "shiftworker"
            and supported_work_arrangement != "shiftworker"
        ):
            work_arrangement = "all"

        returned_clause_numbers.add(clause_number)
        clause_classifications.append(
            OvertimeClauseClassification(
                clause_number=clause_number,
                classification=classification,
                clause_text=clause_source_text(source_clause),
                explanation=explanation,
                employee_cohort=employee_cohort,
                work_arrangement=work_arrangement,
                other_scope_notes=other_scope_notes,
                classifications=categories,
            )
        )

    missing_clause_numbers = expected_clause_numbers - returned_clause_numbers
    if missing_clause_numbers:
        missing = ", ".join(sorted(missing_clause_numbers))
        raise OvertimeInterpretationError(
            f"Missing overtime clause classifications: {missing}"
        )

    return clause_classifications


def load_overtime_clause_classification_artifact(
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Load and validate a saved clause-classification artifact."""
    path = Path(classification_path)

    try:
        with path.open(encoding="utf-8") as classification_file:
            data = json.load(classification_file)
    except json.JSONDecodeError as exc:
        raise OvertimeInterpretationError(
            f"Overtime clause classification JSON is not valid JSON: {path}"
        ) from exc

    if not isinstance(data, Mapping):
        raise OvertimeInterpretationError(
            f"Overtime clause classification JSON must contain an object: {path}"
        )

    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise OvertimeInterpretationError(
            "Overtime clause classification JSON has unsupported schema version: "
            f"{schema_version}"
        )

    return validate_overtime_clause_classifications(
        data,
        overtime_clauses,
        ruleset_key,
    )


def select_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Keep only classifications that feed the downstream ruleset generator."""
    config = overtime_ruleset_config(ruleset_key)
    overtime_creation_clauses: list[OvertimeClauseClassification] = []

    for classification in classifications:
        if any(
            category in config.generation_classifications
            for category in classification.classifications
        ):
            overtime_creation_clauses.append(classification)

    return overtime_creation_clauses
