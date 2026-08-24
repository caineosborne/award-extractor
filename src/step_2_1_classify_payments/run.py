"""Run step 2.1 payment classification."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.award_sources import SOURCE_TYPE_LOCAL_PDF, source_record_for_award

from .step_1_load_award import resolve_classification_inputs
from .step_3_classify_groups import classify_groups, load_openai_client, selected_model
from .step_6_write_artifact import build_result_artifact, write_result
from .schema import DEFAULT_AWARD_PATH


def uses_local_pdf_source(award_path: Path) -> bool:
    """Return whether this award output set originated from a registered PDF."""
    try:
        source_record = source_record_for_award(award_path.parent.name)
    except ValueError:
        return False

    return source_record.get("source_type") == SOURCE_TYPE_LOCAL_PDF


def classify_payments(
    award_path: str = str(DEFAULT_AWARD_PATH),
    output_path: str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OrderedDict[str, Any]:
    """Run step 2.1 and write the payment classification artifact."""
    print(f"Step 2.1: Loading parsed award JSON from {award_path}")
    inputs = resolve_classification_inputs(
        award_path=award_path,
        output_path=output_path,
    )
    active_model = selected_model(model)
    active_client = client or load_openai_client()
    prefer_exact_full_references = uses_local_pdf_source(inputs.source_path)
    print(f"Step 2.1: Classifying payment-related clauses with model {active_model}")
    top_level_clauses, classified_clauses = classify_groups(
        groups=inputs.groups,
        client=active_client,
        model=active_model,
        prefer_exact_full_references=prefer_exact_full_references,
    )
    result = build_result_artifact(
        source_path=inputs.source_path,
        model=active_model,
        top_level_clauses=top_level_clauses,
        classified_clauses=classified_clauses,
    )
    write_result(inputs.destination, result)
    print(f"Step 2.1: Wrote payment classification JSON to {inputs.destination}")
    print(
        "Step 2.1: Classified "
        f"{len(top_level_clauses)} top-level clauses and "
        f"{len(classified_clauses)} descendant clauses"
    )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify payment-relevant clauses in a processed award JSON file."
    )
    parser.add_argument(
        "award_path",
        nargs="?",
        default=str(DEFAULT_AWARD_PATH),
        help=(
            "Path to a processed full award JSON file, for example "
            "data/processed/1_fetch_award/MA000018.json."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the payment classification JSON output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model to use. Defaults to PAYMENT_CLAUSE_CLASSIFIER_MODEL or gpt-5.6-luna.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    result = classify_payments(
        award_path=args.award_path,
        output_path=args.output_path,
        model=args.model,
    )
    destination = Path(args.output_path) if args.output_path else None
    if destination is None:
        from src.common.output_naming import classification_path_for_award_json

        destination = classification_path_for_award_json(args.award_path)
    print(f"Payment classification saved to {destination}")
