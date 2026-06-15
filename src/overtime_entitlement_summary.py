import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.payment_clause_classifier import extract_response_text
from src.payment_clause_classifier_prompt import DEFINITIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATION_PATH = (
    PROJECT_ROOT / "data" / "processed" / "MA000018_payment_classification.json"
)
DEFAULT_MODEL = "gpt-5.4-mini"
OVERTIME_TAGS = ("Ordinary Hours", "Overtime")


class OvertimeEntitlementSummaryError(RuntimeError):
    """Base exception for overtime entitlement summary failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeEntitlementSummaryError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_classification(classification_path: Path | str) -> dict[str, Any]:
    path = Path(classification_path)
    if not path.exists():
        raise OvertimeEntitlementSummaryError(f"Classification JSON not found: {path}")

    try:
        with path.open(encoding="utf-8") as classification_file:
            data = json.load(classification_file)
    except json.JSONDecodeError as exc:
        raise OvertimeEntitlementSummaryError(
            f"Classification JSON is not valid JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise OvertimeEntitlementSummaryError(
            f"Classification JSON must contain an object: {path}"
        )
    if not isinstance(data.get("classified_clauses"), dict):
        raise OvertimeEntitlementSummaryError(
            f"Classification JSON must contain classified_clauses object: {path}"
        )

    return data


def filter_overtime_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    classified_clauses = data.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        raise OvertimeEntitlementSummaryError("classified_clauses must be an object.")

    return {
        clause_id: clause
        for clause_id, clause in classified_clauses.items()
        if isinstance(clause, Mapping)
        and (
            "Ordinary Hours" in clause.get("tags", [])
            or "Overtime" in clause.get("tags", [])
        )
    }


def output_path_for_classification(classification_path: Path | str) -> Path:
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")
    return path.with_name(f"{stem}_overtime_entitlements.md")


def build_messages(source_file: str, overtime_clauses: Mapping[str, Any]) -> list[dict[str, str]]:
    clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)
    system_prompt = f"""You summarise Australian modern award overtime entitlements for payroll implementation.

Use the glossary below:
{DEFINITIONS}

Task:
- Produce concise markdown bullet points explaining when employees are entitled to overtime.
- Include additional breakdowns where needed, such as employee type, day worker/shiftworker, ordinary-hours thresholds, day of week, public holiday, recall, breaks, roster changes, or other conditions.
- Treat Ordinary Hours and Overtime clauses as a combined source set.
- Use Ordinary Hours clauses to identify the boundary for overtime: any hours that are not ordinary hours are overtime.
- Do not calculate dollar amounts.
- Do not invent rules that are not supported by the supplied clauses.
- Cite clause references inline in each bullet.
- Include ordinary-hours rules in the summary where they define when overtime starts.

Return markdown only, with a heading and bullet points.
"""
    user_prompt = (
        f"Source classification file: {source_file}\n\n"
        "Filtered clauses tagged Ordinary Hours or Overtime:\n"
        f"{clauses_json}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def summarize_overtime_entitlements(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    data = load_classification(source_path)
    overtime_clauses = filter_overtime_clauses(data)
    if not overtime_clauses:
        raise OvertimeEntitlementSummaryError(
            f"No Ordinary Hours or Overtime clauses found in: {source_path}"
        )

    try:
        response = client.responses.create(
            model=selected_model,
            input=build_messages(str(source_path), overtime_clauses),
        )
    except Exception as exc:
        raise OvertimeEntitlementSummaryError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeEntitlementSummaryError("OpenAI response did not include output text.")

    destination = Path(output_path) if output_path else output_path_for_classification(source_path)
    destination.write_text(output_text, encoding="utf-8")
    return output_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise overtime entitlements from a payment classification JSON file."
    )
    parser.add_argument(
        "classification_path",
        nargs="?",
        default=str(DEFAULT_CLASSIFICATION_PATH),
        help=(
            "Path to a payment classification JSON file, for example "
            "data/processed/MA000018_payment_classification.json."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown overtime entitlement summary.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to OVERTIME_ENTITLEMENT_SUMMARY_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    summarize_overtime_entitlements(
        classification_path=args.classification_path,
        output_path=args.output_path,
        model=args.model,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_classification(args.classification_path)
    )
    print(f"Overtime entitlement summary saved to {destination}")


if __name__ == "__main__":
    main()
