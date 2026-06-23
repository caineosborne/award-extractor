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
    interpretation_output_path_for_classification,
    overtime_clause_classification_output_path_for_classification,
)
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_runtime import load_openai_environment
from src.common.llm_io import extract_response_text
from src.common.overtime_rules import (
    OvertimeRule,
    build_step_3_rules_artifact,
    json_output_path_for_markdown,
    rules_from_markdown_fallback,
    validate_rule_list,
    write_rules_artifact,
)
from src.script_2_classify_payments import parse_response_json
from src.script_3_interpret_overtime_prompt import (
    OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT,
    OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT,
    OVERTIME_INTERPRETATION_SYSTEM_PROMPT,
    build_overtime_interpretation_user_prompt,
)


# 1. Imports / constants

DEFAULT_CLASSIFICATION_PATH = default_classification_path_for_award("MA000018")
DEFAULT_MODEL = "gpt-5.4-mini"
OVERTIME_TAGS = ("Ordinary Hours & Overtime",)
SCHEMA_VERSION = "overtime-clause-classification-v2"
OVERTIME_CLASSIFICATIONS = (
    "Ordinary Hours Boundary",
    "Overtime Trigger",
    "Overtime Consequence",
    "Related Rule",
    "Not Relevant",
)
OVERTIME_CREATION_CLASSIFICATIONS = (
    "Ordinary Hours Boundary",
    "Overtime Trigger",
)
RULE_ID_ALLOWED_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CLAUSE_REFERENCE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b",
    re.IGNORECASE,
)
CLAUSE_REFERENCE_FULL_PATTERN = re.compile(
    r"^\d+(?:\.\d+)+(?:\([a-z0-9]+\))*$",
    re.IGNORECASE,
)


class OvertimeInterpretationError(RuntimeError):
    """Base exception for overtime interpretation failures."""


# 2. Data structures


@dataclass(frozen=True)
class OvertimeClauseClassification:
    """Store the classification result for one overtime-related clause."""

    clause_number: str
    classification: str
    clause_text: str
    explanation: str
    classifications: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Ensure the multi-classification field always includes the primary category."""
        if not self.classifications:
            object.__setattr__(self, "classifications", (self.classification,))


# 3. Input / path helpers


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load and validate the OpenAI environment for step 3."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


def load_classification(classification_path: Path | str) -> dict[str, Any]:
    """Load and validate the step-2 payment classification JSON artifact."""
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


def interpretation_output_path_for_source(
    classification_path: Path | str,
) -> Path:
    """Return the default step-3 interpretation markdown path."""
    return interpretation_output_path_for_classification(classification_path)


def overtime_clause_classification_path_for_source(
    classification_path: Path | str,
) -> Path:
    """Return the default step-3 clause-classification JSON path."""
    return overtime_clause_classification_output_path_for_classification(
        classification_path
    )


def output_path_for_classification(classification_path: Path | str) -> Path:
    """Return the default interpretation path using the legacy helper name."""
    return interpretation_output_path_for_source(classification_path)


def classification_output_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Return the clause-classification path using the legacy helper name."""
    return overtime_clause_classification_path_for_source(classification_path)


def clause_source_text(clause: Mapping[str, Any]) -> str:
    """Return the stored clause text, or serialize the clause when text is missing."""
    text = clause.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(clause, ensure_ascii=False)


def clause_text(clause: Mapping[str, Any]) -> str:
    """Return clause source text using the legacy helper name."""
    return clause_source_text(clause)


# 4. Select overtime-related clauses


def select_overtime_related_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Select the clauses that step 2 tagged as ordinary-hours or overtime related."""
    classified_clauses = data.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        raise OvertimeInterpretationError("classified_clauses must be an object.")

    overtime_related_clauses: dict[str, Any] = {}

    for clause_id, clause in classified_clauses.items():
        # Skip malformed clause entries so only clause-like objects reach the model.
        if not isinstance(clause, Mapping):
            continue

        # Keep only clauses that were tagged in step 2 as overtime-related.
        if any(tag in clause.get("tags", []) for tag in OVERTIME_TAGS):
            overtime_related_clauses[clause_id] = clause

    return overtime_related_clauses


def filter_overtime_related_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return overtime-related clauses using the legacy internal helper name."""
    return select_overtime_related_clauses(data)


def filter_overtime_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return overtime-related clauses using the legacy helper name."""
    return select_overtime_related_clauses(data)


# 5. Classify overtime clause roles


def format_clauses_for_prompt(overtime_clauses: Mapping[str, Any]) -> str:
    """Format overtime-related clauses into markdown sections for the model."""
    sections: list[str] = []

    for clause_number, clause in overtime_clauses.items():
        if not isinstance(clause, Mapping):
            continue

        # Put each clause in its own labelled section so the model can cite it clearly.
        sections.append(f"## Clause {clause_number}\n\n{clause_source_text(clause)}")

    return "\n\n---\n\n".join(sections)


def build_clause_classification_messages(
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build the step-3A messages used to classify overtime-related clauses."""
    # Convert the candidate clauses into a readable markdown block for the user prompt.
    clauses_text = format_clauses_for_prompt(overtime_clauses)
    return [
        {"role": "system", "content": OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT},
        {
            "role": "user",
            # Insert the clause markdown into the fixed classification prompt template.
            "content": OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT.format(
                clauses_text=clauses_text
            ),
        },
    ]


def build_classification_messages(
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return clause-classification messages using the legacy helper name."""
    return build_clause_classification_messages(overtime_clauses)


def classification_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from clause classification."""
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
                            "enum": list(OVERTIME_CLASSIFICATIONS),
                        },
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(OVERTIME_CLASSIFICATIONS),
                            },
                            "minItems": 1,
                        },
                        "clause_text": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "clause_number",
                        "classification",
                        "classifications",
                        "clause_text",
                        "explanation",
                    ],
                },
            },
        },
        "required": ["clauses"],
    }


def validate_overtime_clause_classifications(
    response_data: Mapping[str, Any],
    overtime_clauses: Mapping[str, Any],
) -> list[OvertimeClauseClassification]:
    """Validate the clause-classification response against the source clauses."""
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

        # Read the model's key fields for this clause-level classification.
        clause_number = str(raw_clause.get("clause_number") or "")
        classification = str(raw_clause.get("classification") or "")
        raw_classifications = raw_clause.get("classifications")
        explanation = str(raw_clause.get("explanation") or "")

        # Check that the model only returned clauses that were actually sent in.
        if clause_number not in expected_clause_numbers:
            raise OvertimeInterpretationError(
                f"Unknown overtime clause classification reference: {clause_number}"
            )
        if clause_number in returned_clause_numbers:
            raise OvertimeInterpretationError(
                f"Duplicate overtime clause classification reference: {clause_number}"
            )
        if classification not in OVERTIME_CLASSIFICATIONS:
            raise OvertimeInterpretationError(
                f"Unsupported overtime clause classification: {classification}"
            )

        # Normalise the optional multi-classification field into a tuple.
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
            item for item in categories if item not in OVERTIME_CLASSIFICATIONS
        ]
        if unsupported_classifications:
            unsupported = ", ".join(unsupported_classifications)
            raise OvertimeInterpretationError(
                f"Unsupported overtime clause classifications for {clause_number}: "
                f"{unsupported}"
            )
        if classification not in categories:
            raise OvertimeInterpretationError(
                f"Primary classification must be included in classifications: {clause_number}"
            )
        if not explanation.strip():
            raise OvertimeInterpretationError(
                f"Overtime clause classification explanation is empty: {clause_number}"
            )

        # Confirm the source clause is still a clause-like object before using its text.
        source_clause = overtime_clauses[clause_number]
        if not isinstance(source_clause, Mapping):
            raise OvertimeInterpretationError(
                f"Overtime clause is not an object: {clause_number}"
            )

        # Record that this clause has been accounted for in the model response.
        returned_clause_numbers.add(clause_number)
        clause_classifications.append(
            OvertimeClauseClassification(
                clause_number=clause_number,
                classification=classification,
                clause_text=clause_source_text(source_clause),
                explanation=explanation,
                classifications=categories,
            )
        )

    # Make sure the model classified every clause that was sent for this step.
    missing_clause_numbers = expected_clause_numbers - returned_clause_numbers
    if missing_clause_numbers:
        missing = ", ".join(sorted(missing_clause_numbers))
        raise OvertimeInterpretationError(
            f"Missing overtime clause classifications: {missing}"
        )

    return clause_classifications


def classify_overtime_clauses(
    overtime_clauses: Mapping[str, Any],
    client: Any,
    model: str,
) -> list[OvertimeClauseClassification]:
    """Ask the model to classify each overtime-related clause."""
    try:
        # Send the clause set to the model with a strict JSON schema response format.
        response = client.responses.create(
            model=model,
            input=build_clause_classification_messages(overtime_clauses),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "overtime_clause_classification",
                    "schema": classification_response_json_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI classification request failed.") from exc

    # Extract the model's text payload before parsing the JSON body.
    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError(
            "OpenAI classification response did not include output text."
        )

    # Parse and validate the returned clause classifications against the source clause set.
    return validate_overtime_clause_classifications(
        parse_response_json(output_text),
        overtime_clauses,
    )


def load_overtime_clause_classification_artifact(
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
) -> list[OvertimeClauseClassification]:
    """Load and validate a saved step-3 clause-classification artifact."""
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
    if schema_version != SCHEMA_VERSION:
        raise OvertimeInterpretationError(
            "Overtime clause classification JSON has unsupported schema version: "
            f"{schema_version}"
        )

    # Re-run the same validation used for fresh model output so cached files stay trustworthy.
    return validate_overtime_clause_classifications(data, overtime_clauses)


def build_clause_classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
) -> dict[str, Any]:
    """Build the saved JSON artifact for step-3 clause classifications."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source_classification_file": str(source_file),
        "included_categories_for_interpretation": list(OVERTIME_CREATION_CLASSIFICATIONS),
        "clauses": [
            {
                "clause_number": classification.clause_number,
                "classification": classification.classification,
                "classifications": list(classification.classifications),
                "clause_text": classification.clause_text,
                "explanation": classification.explanation,
            }
            for classification in classifications
        ],
    }


def classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
) -> dict[str, Any]:
    """Return the clause-classification artifact using the legacy helper name."""
    return build_clause_classification_artifact(source_file, classifications)


def load_or_create_overtime_clause_classifications(
    source_path: Path,
    overtime_clauses: Mapping[str, Any],
    classification_output_path: Path,
    client: Any,
    model: str,
) -> list[OvertimeClauseClassification]:
    """Reuse a valid clause-classification file or regenerate it from step 2."""
    if classification_output_path.exists():
        try:
            # Reuse the saved artifact when it still matches the current clause set.
            return load_overtime_clause_classification_artifact(
                classification_output_path,
                overtime_clauses,
            )
        except OvertimeInterpretationError:
            # Ignore stale or invalid cached files and regenerate them from the source data.
            pass

    # Run the clause-classification model when there is no usable cached artifact.
    clause_classifications = classify_overtime_clauses(
        overtime_clauses,
        client,
        model,
    )
    classification_text = json.dumps(
        build_clause_classification_artifact(source_path, clause_classifications),
        indent=2,
        ensure_ascii=False,
    )
    # Save the fresh artifact for reuse by later steps and future runs.
    write_text_with_archive(classification_output_path, classification_text)
    return clause_classifications


# 6. Select overtime-creation clauses


def select_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
) -> list[OvertimeClauseClassification]:
    """Select the clause classifications that can create overtime entitlement."""
    overtime_creation_clauses: list[OvertimeClauseClassification] = []

    for classification in classifications:
        # Keep clauses that define the ordinary-hours boundary or trigger overtime directly.
        if any(
            category in OVERTIME_CREATION_CLASSIFICATIONS
            for category in classification.classifications
        ):
            overtime_creation_clauses.append(classification)

    return overtime_creation_clauses


def filter_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
) -> list[OvertimeClauseClassification]:
    """Return overtime-creation clauses using the legacy helper name."""
    return select_overtime_creation_clauses(classifications)


# 7. Generate interpretation markdown
def format_working_paper_input(
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
) -> str:
    """Format the clause input used by the interpretation-writing model."""
    sections = ["# Overtime Creation Clauses\n"]

    for clause in overtime_creation_clauses:
        # Present each clause as a compact working-paper section for the interpretation step.
        sections.append(
            f"""## Clause {clause.clause_number}

Classification:
{", ".join(clause.classifications)}

Explanation:
{clause.explanation}

Source Text:
{clause.clause_text}
"""
        )

    return "\n".join(sections)

def build_interpretation_messages(
    source_file: str,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
) -> list[dict[str, str]]:
    """Build the step-3 messages used to write the overtime interpretation."""
    # Turn the shortlisted clause set into the working-paper text used in the prompt.
    working_paper_input = format_working_paper_input(overtime_creation_clauses)
    # Build the user prompt that tells the model how to write the interpretation document.
    user_prompt = build_overtime_interpretation_user_prompt(
        source_file=source_file,
        working_paper_input=working_paper_input,
    )
    return [
        {"role": "system", "content": OVERTIME_INTERPRETATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_messages(
    source_file: str,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
) -> list[dict[str, str]]:
    """Return interpretation messages using the legacy helper name."""
    return build_interpretation_messages(source_file, overtime_creation_clauses)


def interpretation_response_json_schema() -> dict[str, Any]:
    """Define the strict JSON schema expected from the step-3 interpretation model."""
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
) -> list[OvertimeRule]:
    """Validate the structured rule output from step 3."""
    raw_rules = response_data.get("rules")
    if not isinstance(raw_rules, list):
        raise OvertimeInterpretationError("Interpretation response must contain rules array.")

    rules = validate_rule_list(raw_rules)
    valid_clause_numbers: set[str] = set()
    for classification in overtime_creation_clauses:
        valid_clause_numbers.add(classification.clause_number)
        for clause_reference_match in CLAUSE_REFERENCE_PATTERN.finditer(
            classification.clause_text
        ):
            valid_clause_numbers.add(clause_reference_match.group(0))

    valid_classifications = set(OVERTIME_CREATION_CLASSIFICATIONS)

    def candidate_parent_clause_keys(clause_reference: str) -> list[str]:
        """Return progressively broader clause keys for matching shortlisted clauses."""
        candidates = [clause_reference]
        simplified = re.sub(r"(?:\([a-z0-9]+\))+$", "", clause_reference, flags=re.IGNORECASE)
        if simplified not in candidates:
            candidates.append(simplified)

        dotted_parts = simplified.split(".")
        while len(dotted_parts) > 1:
            dotted_parts = dotted_parts[:-1]
            candidate = ".".join(dotted_parts)
            if candidate not in candidates:
                candidates.append(candidate)

        return candidates

    for rule in rules:
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
            raise OvertimeInterpretationError(
                f"Rule {rule.rule_id} referenced malformed source clauses: "
                f"{malformed_display}"
            )

        known_source_clauses: set[str] = set()
        for source_clause in rule.source_clause_numbers:
            for candidate in candidate_parent_clause_keys(source_clause):
                if candidate in valid_clause_numbers:
                    known_source_clauses.add(candidate)
                    break
        if not known_source_clauses:
            source_display = ", ".join(rule.source_clause_numbers)
            raise OvertimeInterpretationError(
                f"Rule {rule.rule_id} did not reference any known step-3 source clause. "
                f"Returned source clauses: {source_display}"
            )

        unsupported_source_classifications = (
            set(rule.source_classifications) - valid_classifications
        )
        if unsupported_source_classifications:
            unsupported_display = ", ".join(sorted(unsupported_source_classifications))
            raise OvertimeInterpretationError(
                f"Rule {rule.rule_id} referenced unsupported source classifications: "
                f"{unsupported_display}"
            )

    return rules


# 8. Output writing / orchestration


def generate_overtime_interpretation(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    output_path: Path | str | None = None,
    classification_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    """Generate the step-3 interpretation JSON and derived markdown artifact."""
    # Pick the explicit model first, then the environment override, then the default.
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    if client is None:
        # Load credentials only when this function is creating its own OpenAI client.
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    # Stage 1: load the payment-classification output produced by step 2.
    data = load_classification(source_path)
    # Stage 2: select only the clauses that step 2 already marked as overtime-related.
    overtime_clauses = select_overtime_related_clauses(data)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No Ordinary Hours or Overtime clauses found in: {source_path}"
        )

    classification_destination = (
        Path(classification_output_path)
        if classification_output_path
        else overtime_clause_classification_path_for_source(source_path)
    )
    # Stage 3: reuse or regenerate the intermediate clause-role classifications for step 3.
    clause_classifications = load_or_create_overtime_clause_classifications(
        source_path=source_path,
        overtime_clauses=overtime_clauses,
        classification_output_path=classification_destination,
        client=client,
        model=selected_model,
    )

    # Stage 4: keep only the clause roles that actually create overtime entitlement.
    overtime_creation_clauses = select_overtime_creation_clauses(
        clause_classifications
    )
    if not overtime_creation_clauses:
        raise OvertimeInterpretationError(
            "No Ordinary Hours Boundary or Overtime Trigger clauses found."
        )

    try:
        # Stage 5: ask the model to write the structured overtime rules from the shortlisted clause set.
        response = client.responses.create(
            model=selected_model,
            input=build_interpretation_messages(
                str(source_path),
                overtime_creation_clauses,
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "overtime_rules",
                    "schema": interpretation_response_json_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI interpretation request failed.") from exc

    # Extract the final structured rule output from the model response.
    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError("OpenAI response did not include output text.")

    try:
        response_data = parse_response_json(output_text)
        structured_rules = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
        )
    except json.JSONDecodeError:
        # Support legacy markdown-only model output while the pipeline transitions to JSON.
        structured_rules = rules_from_markdown_fallback(
            output_text,
            source_path=source_path,
        )

    destination = (
        Path(output_path)
        if output_path
        else interpretation_output_path_for_source(source_path)
    )
    json_destination = json_output_path_for_markdown(destination)
    rules_artifact = build_step_3_rules_artifact(
        source_classification_file=source_path,
        source_clause_classification_file=classification_destination,
        rules=structured_rules,
    )
    # Save both the canonical JSON artifact and a derived markdown view.
    write_rules_artifact(
        json_path=json_destination,
        markdown_path=destination,
        artifact=rules_artifact,
    )
    return str(rules_artifact["rendered_markdown"])


# 9. Main orchestration


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the step-3 interpretation generator."""
    parser = argparse.ArgumentParser(
        description="Generate an overtime interpretation working document from classification JSON."
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
        "--output-path",
        default=None,
        help="Optional path for the markdown overtime interpretation working document.",
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
    """Run the step-3 interpretation generator from the command line."""
    # Read the CLI inputs that control the source file, model, and optional outputs.
    args = parse_args()
    # Run the end-to-end step-3 interpretation workflow.
    generate_overtime_interpretation(
        classification_path=args.classification_path,
        output_path=args.output_path,
        classification_output_path=args.classification_output_path,
        model=args.model,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else interpretation_output_path_for_source(args.classification_path)
    )
    print(f"Overtime interpretation saved to {destination}")


if __name__ == "__main__":
    main()
