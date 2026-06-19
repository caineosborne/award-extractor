import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.Overtime_System_Prompt import OVERTIME_INTERPRETATION_SYSTEM_PROMPT
from src.output_paths import (
    OVERTIME_INTERPRETATIONS_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    write_text_with_archive,
)
from src.script_2_classify_payments import extract_response_text


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


class OvertimeInterpretationError(RuntimeError):
    """Base exception for overtime interpretation failures."""


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


def build_messages(source_file: str, overtime_clauses: Mapping[str, Any]) -> list[dict[str, str]]:
    clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)
    user_prompt = (
        f"Source classification file: {source_file}\n\n"
        "Filtered clauses tagged Ordinary Hours & Overtime:\n"
        f"{clauses_json}"
    )
    return [
        {"role": "system", "content": OVERTIME_INTERPRETATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def generate_overtime_interpretation(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    output_path: Path | str | None = None,
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

    try:
        response = client.responses.create(
            model=selected_model,
            input=build_messages(str(source_path), overtime_clauses),
        )
    except Exception as exc:
        raise OvertimeInterpretationError("OpenAI request failed.") from exc

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
