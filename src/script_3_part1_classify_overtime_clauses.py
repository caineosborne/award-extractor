"""Step 3 part 1: prepare overtime clauses for interpretation.

This file covers the deterministic and clause-classification parts of step 3:
1. load the step-2 payment classification artifact;
2. keep only clauses tagged as overtime-related;
3. classify each shortlisted clause by its overtime role; and
4. write the intermediate `*_overtime_clause_classification.json` artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    default_classification_path_for_award,
    overtime_clause_classification_output_path_for_classification,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    explicit_clause_classification_output_path,
    overtime_ruleset_config,
)
from src.common.overtime_rules import (
    ALLOWED_EMPLOYEE_COHORTS,
    ALLOWED_WORK_ARRANGEMENTS,
)
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_runtime import load_openai_environment
from src.common.llm_io import extract_response_text
from src.prompts.overtime_ruleset import (
    build_clause_classification_messages as build_ruleset_clause_classification_messages,
)
from src.script_2_classify_payments import parse_response_json


DEFAULT_CLASSIFICATION_PATH = default_classification_path_for_award("MA000018")
DEFAULT_MODEL = "gpt-5.4-mini"
OVERTIME_TAGS = overtime_ruleset_config(OVERTIME_CREATION_RULESET).source_tags
SCHEMA_VERSION = "overtime-clause-classification-v3"
SUPPORTED_SCHEMA_VERSIONS = (
    "overtime-clause-classification-v2",
    SCHEMA_VERSION,
)
OVERTIME_CLASSIFICATIONS = overtime_ruleset_config(
    OVERTIME_CREATION_RULESET
).allowed_classifications
OVERTIME_CREATION_CLASSIFICATIONS = (
    "Ordinary Hours Boundary",
    "Overtime Trigger",
)


class OvertimeInterpretationError(RuntimeError):
    """Base exception for step-3 overtime interpretation failures."""


@dataclass(frozen=True)
class OvertimeClauseClassification:
    """Store the overtime-role classification for one shortlisted clause."""

    clause_number: str
    classification: str
    clause_text: str
    explanation: str
    employee_cohort: str = "all"
    work_arrangement: str = "all"
    other_scope_notes: str = ""
    classifications: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Ensure the primary classification always appears in the full category list."""
        if not self.classifications:
            object.__setattr__(self, "classifications", (self.classification,))


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load and validate the OpenAI environment used by step 3."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


def load_classification(classification_path: Path | str) -> dict[str, Any]:
    """Load the step-2 payment classification artifact."""
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


def overtime_clause_classification_path_for_source(
    classification_path: Path | str,
) -> Path:
    """Return the default path for the intermediate clause-classification artifact."""
    return overtime_clause_classification_output_path_for_classification(
        classification_path
    )


def ruleset_clause_classification_path_for_source(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the explicit ruleset clause-classification artifact path."""
    return explicit_clause_classification_output_path(classification_path, ruleset_key)


def classification_output_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Return the clause-classification path using the legacy helper name."""
    return overtime_clause_classification_path_for_source(classification_path)


def clause_source_text(clause: Mapping[str, Any]) -> str:
    """Return the stored clause text, or a JSON fallback when text is missing."""
    text = clause.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(clause, ensure_ascii=False)


def clause_text(clause: Mapping[str, Any]) -> str:
    """Return clause source text using the legacy helper name."""
    return clause_source_text(clause)


def normalized_work_arrangement_from_clause_text(clause_text: str) -> str:
    """Return an explicit work-arrangement tag supported by the clause text."""
    normalized_text = clause_text.lower()

    if re.search(r"\bday[- ]workers?\b", normalized_text):
        return "day-worker"
    if re.search(r"\bshiftworkers?\b", normalized_text):
        return "shiftworker"
    if re.search(r"\bshiftwork\b", normalized_text):
        return "shiftworker"

    return "all"


def select_ruleset_related_clauses(
    data: Mapping[str, Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> dict[str, Any]:
    """Keep only step-2 clauses tagged as ordinary-hours or overtime related."""
    classified_clauses = data.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        raise OvertimeInterpretationError("classified_clauses must be an object.")

    config = overtime_ruleset_config(ruleset_key)
    overtime_related_clauses: dict[str, Any] = {}

    for clause_id, clause in classified_clauses.items():
        if not isinstance(clause, Mapping):
            continue

        if any(tag in clause.get("tags", []) for tag in config.source_tags):
            overtime_related_clauses[clause_id] = clause

    return overtime_related_clauses


def select_overtime_related_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    return select_ruleset_related_clauses(data, OVERTIME_CREATION_RULESET)


def filter_overtime_related_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return overtime-related clauses using the legacy internal helper name."""
    return select_ruleset_related_clauses(data, OVERTIME_CREATION_RULESET)


def filter_overtime_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return overtime-related clauses using the legacy helper name."""
    return select_ruleset_related_clauses(data, OVERTIME_CREATION_RULESET)


def format_clauses_for_prompt(overtime_clauses: Mapping[str, Any]) -> str:
    """Format shortlisted clauses into clear markdown sections for the model."""
    sections: list[str] = []

    for clause_number, clause in overtime_clauses.items():
        if not isinstance(clause, Mapping):
            continue

        sections.append(f"## Clause {clause_number}\n\n{clause_source_text(clause)}")

    return "\n\n---\n\n".join(sections)


def build_clause_classification_messages(
    overtime_clauses: Mapping[str, Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Build the messages used for the clause-role classification pass."""
    clauses_text = format_clauses_for_prompt(overtime_clauses)
    return build_ruleset_clause_classification_messages(ruleset_key, clauses_text)


def build_classification_messages(
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return clause-classification messages using the legacy helper name."""
    return build_clause_classification_messages(
        overtime_clauses,
        OVERTIME_CREATION_RULESET,
    )


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
    """Validate the clause-classification output against the shortlisted clauses."""
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
        elif work_arrangement == "shiftworker" and supported_work_arrangement != "shiftworker":
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


def classify_overtime_clauses(
    overtime_clauses: Mapping[str, Any],
    client: Any,
    model: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Ask the model to classify each shortlisted clause by overtime role."""
    config = overtime_ruleset_config(ruleset_key)
    try:
        response = client.responses.create(
            model=model,
            input=build_clause_classification_messages(overtime_clauses, ruleset_key),
            text={
                "format": {
                    "type": "json_schema",
                    "name": config.clause_classification_schema_name,
                    "schema": classification_response_json_schema(ruleset_key),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI classification request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError(
            "OpenAI classification response did not include output text."
        )

    return validate_overtime_clause_classifications(
        parse_response_json(output_text),
        overtime_clauses,
        ruleset_key,
    )


def build_clause_classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> dict[str, Any]:
    """Build the JSON artifact that part 2 will read."""
    config = overtime_ruleset_config(ruleset_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_key": ruleset_key,
        "source_classification_file": str(source_file),
        "included_categories_for_interpretation": list(config.generation_classifications),
        "clauses": [
            {
                "clause_number": classification.clause_number,
                "classification": classification.classification,
                "classifications": list(classification.classifications),
                "clause_text": classification.clause_text,
                "explanation": classification.explanation,
                "employee_cohort": classification.employee_cohort,
                "work_arrangement": classification.work_arrangement,
                "other_scope_notes": classification.other_scope_notes,
            }
            for classification in classifications
        ],
    }


def classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
) -> dict[str, Any]:
    """Return the clause-classification artifact using the legacy helper name."""
    return build_clause_classification_artifact(
        source_file,
        classifications,
        OVERTIME_CREATION_RULESET,
    )


def load_or_create_overtime_clause_classifications(
    source_path: Path,
    overtime_clauses: Mapping[str, Any],
    classification_output_path: Path,
    client: Any,
    model: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Reuse a valid clause-classification file or regenerate it from step 2."""
    if classification_output_path.exists():
        try:
            return load_overtime_clause_classification_artifact(
                classification_output_path,
                overtime_clauses,
                ruleset_key,
            )
        except OvertimeInterpretationError:
            pass

    clause_classifications = classify_overtime_clauses(
        overtime_clauses,
        client,
        model,
        ruleset_key,
    )
    classification_text = json.dumps(
        build_clause_classification_artifact(
            source_path,
            clause_classifications,
            ruleset_key,
        ),
        indent=2,
        ensure_ascii=False,
    )
    write_text_with_archive(classification_output_path, classification_text)
    return clause_classifications


def select_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Keep only clause roles that can create overtime entitlement."""
    config = overtime_ruleset_config(ruleset_key)
    overtime_creation_clauses: list[OvertimeClauseClassification] = []

    for classification in classifications:
        if any(
            category in config.generation_classifications
            for category in classification.classifications
        ):
            overtime_creation_clauses.append(classification)

    return overtime_creation_clauses


def filter_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
) -> list[OvertimeClauseClassification]:
    """Return overtime-creation clauses using the legacy helper name."""
    return select_overtime_creation_clauses(
        classifications,
        OVERTIME_CREATION_RULESET,
    )


def prepare_overtime_clause_classifications(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    classification_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Run step 3 part 1 and write the intermediate clause-classification artifact."""
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    data = load_classification(source_path)
    overtime_clauses = select_ruleset_related_clauses(data, ruleset_key)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No {overtime_ruleset_config(ruleset_key).display_name.lower()} source clauses found in: {source_path}"
        )

    destination = (
        Path(classification_output_path)
        if classification_output_path
        else (
            overtime_clause_classification_path_for_source(source_path)
            if ruleset_key == OVERTIME_CREATION_RULESET
            else ruleset_clause_classification_path_for_source(source_path, ruleset_key)
        )
    )

    return load_or_create_overtime_clause_classifications(
        source_path=source_path,
        overtime_clauses=overtime_clauses,
        classification_output_path=destination,
        client=client,
        model=selected_model,
        ruleset_key=ruleset_key,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for step 3 part 1."""
    parser = argparse.ArgumentParser(
        description="Prepare overtime clause classifications from step-2 payment classification JSON."
    )
    parser.add_argument(
        "classification_path",
        nargs="?",
        default=str(DEFAULT_CLASSIFICATION_PATH),
        help=(
            "Path to a payment classification JSON file, for example "
            "data/processed/2_payment_clause_identifier/MA000018_payment_classification.json."
        ),
    )
    parser.add_argument(
        "--classification-output-path",
        default=None,
        help="Optional path for the intermediate overtime clause classification JSON.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to OVERTIME_INTERPRETATION_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Run step 3 part 1 from the command line."""
    args = parse_args()
    prepare_overtime_clause_classifications(
        classification_path=args.classification_path,
        classification_output_path=args.classification_output_path,
        model=args.model,
    )
    destination = (
        Path(args.classification_output_path)
        if args.classification_output_path
        else overtime_clause_classification_path_for_source(args.classification_path)
    )
    print(f"Overtime clause classification saved to {destination}")


if __name__ == "__main__":
    main()
