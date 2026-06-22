import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.script_3_interpret_overtime_prompt import (
    OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT,
    OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT,
    OVERTIME_INTERPRETATION_SYSTEM_PROMPT,
    build_overtime_interpretation_user_prompt,
)

from src.output_paths import (
    OVERTIME_INTERPRETATIONS_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    write_text_with_archive,
)
from src.script_2_classify_payments import extract_response_text, parse_response_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / PAYMENT_CLAUSE_IDENTIFIER_DIR
    / "MA000018_payment_classification.json"
)
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


class OvertimeInterpretationError(RuntimeError):
    """Base exception for overtime interpretation failures."""


@dataclass(frozen=True)
class OvertimeClauseClassification:
    clause_number: str
    classification: str
    clause_text: str
    explanation: str
    classifications: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.classifications:
            object.__setattr__(self, "classifications", (self.classification,))


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeInterpretationError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_classification(classification_path: Path | str) -> dict[str, Any]:
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


def filter_overtime_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    classified_clauses = data.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        raise OvertimeInterpretationError("classified_clauses must be an object.")

    return {
        clause_id: clause
        for clause_id, clause in classified_clauses.items()
        if isinstance(clause, Mapping)
        and any(tag in clause.get("tags", []) for tag in OVERTIME_TAGS)
    }


def output_path_for_classification(classification_path: Path | str) -> Path:
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")
    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_interpretation.md",
    )


def classification_output_path_for_classification(classification_path: Path | str) -> Path:
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")
    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_clause_classification.json",
    )


def clause_text(clause: Mapping[str, Any]) -> str:
    text = clause.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(clause, ensure_ascii=False)


def format_clauses_for_prompt(overtime_clauses: Mapping[str, Any]) -> str:
    sections: list[str] = []

    for clause_number, clause in overtime_clauses.items():
        if not isinstance(clause, Mapping):
            continue
        sections.append(f"## Clause {clause_number}\n\n{clause_text(clause)}")

    return "\n\n---\n\n".join(sections)


def build_classification_messages(
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    clauses_text = format_clauses_for_prompt(overtime_clauses)
    return [
        {"role": "system", "content": OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT.format(
                clauses_text=clauses_text
            ),
        },
    ]


def classification_response_json_schema() -> dict[str, Any]:
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

        source_clause = overtime_clauses[clause_number]
        if not isinstance(source_clause, Mapping):
            raise OvertimeInterpretationError(
                f"Overtime clause is not an object: {clause_number}"
            )

        returned_clause_numbers.add(clause_number)
        clause_classifications.append(
            OvertimeClauseClassification(
                clause_number=clause_number,
                classification=classification,
                clause_text=clause_text(source_clause),
                explanation=explanation,
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


def classify_overtime_clauses(
    overtime_clauses: Mapping[str, Any],
    client: Any,
    model: str,
) -> list[OvertimeClauseClassification]:
    try:
        response = client.responses.create(
            model=model,
            input=build_classification_messages(overtime_clauses),
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

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError(
            "OpenAI classification response did not include output text."
        )

    return validate_overtime_clause_classifications(
        parse_response_json(output_text),
        overtime_clauses,
    )


def load_overtime_clause_classification_artifact(
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
) -> list[OvertimeClauseClassification]:
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

    return validate_overtime_clause_classifications(data, overtime_clauses)


def load_or_create_overtime_clause_classifications(
    source_path: Path,
    overtime_clauses: Mapping[str, Any],
    classification_output_path: Path,
    client: Any,
    model: str,
) -> list[OvertimeClauseClassification]:
    if classification_output_path.exists():
        try:
            return load_overtime_clause_classification_artifact(
                classification_output_path,
                overtime_clauses,
            )
        except OvertimeInterpretationError as exc:
            if "unsupported schema version" not in str(exc):
                raise

    clause_classifications = classify_overtime_clauses(
        overtime_clauses,
        client,
        model,
    )
    classification_text = json.dumps(
        classification_artifact(source_path, clause_classifications),
        indent=2,
        ensure_ascii=False,
    )
    write_text_with_archive(classification_output_path, classification_text)
    return clause_classifications


def filter_overtime_creation_clauses(
    classifications: Sequence[OvertimeClauseClassification],
) -> list[OvertimeClauseClassification]:
    return [
        classification
        for classification in classifications
        if any(
            category in OVERTIME_CREATION_CLASSIFICATIONS
            for category in classification.classifications
        )
    ]


def format_working_paper_input(
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
) -> str:
    sections = ["# Overtime Creation Clauses\n"]

    for clause in overtime_creation_clauses:
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


def build_messages(
    source_file: str,
    overtime_creation_clauses: Sequence[OvertimeClauseClassification],
) -> list[dict[str, str]]:
    working_paper_input = format_working_paper_input(overtime_creation_clauses)
    user_prompt = build_overtime_interpretation_user_prompt(
        source_file=source_file,
        working_paper_input=working_paper_input,
    )
    return [
        {"role": "system", "content": OVERTIME_INTERPRETATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
) -> dict[str, Any]:
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


def generate_overtime_interpretation(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    output_path: Path | str | None = None,
    classification_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    data = load_classification(source_path)
    overtime_clauses = filter_overtime_clauses(data)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No Ordinary Hours or Overtime clauses found in: {source_path}"
        )

    classification_destination = (
        Path(classification_output_path)
        if classification_output_path
        else classification_output_path_for_classification(source_path)
    )
    clause_classifications = load_or_create_overtime_clause_classifications(
        source_path=source_path,
        overtime_clauses=overtime_clauses,
        classification_output_path=classification_destination,
        client=client,
        model=selected_model,
    )

    overtime_creation_clauses = filter_overtime_creation_clauses(clause_classifications)
    if not overtime_creation_clauses:
        raise OvertimeInterpretationError(
            "No Ordinary Hours Boundary or Overtime Trigger clauses found."
        )

    try:
        response = client.responses.create(
            model=selected_model,
            input=build_messages(str(source_path), overtime_creation_clauses),
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI interpretation request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError("OpenAI response did not include output text.")

    destination = Path(output_path) if output_path else output_path_for_classification(source_path)
    write_text_with_archive(destination, output_text)
    return output_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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
    args = parse_args()
    generate_overtime_interpretation(
        classification_path=args.classification_path,
        output_path=args.output_path,
        classification_output_path=args.classification_output_path,
        model=args.model,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_classification(args.classification_path)
    )
    print(f"Overtime interpretation saved to {destination}")


if __name__ == "__main__":
    main()
