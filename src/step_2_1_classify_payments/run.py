"""Run step 2.1 payment classification."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .schema import DEFAULT_AWARD_PATH

from .deterministic import (
    build_result_artifact,
    resolve_classification_inputs,
    write_result,
)
from .llm import classify_groups, load_openai_client, selected_model


def classify_payments(
    award_path: str = str(DEFAULT_AWARD_PATH),
    output_path: str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OrderedDict[str, Any]:
    """Run step 2.1 and write the payment classification artifact."""
    inputs = resolve_classification_inputs(
        award_path=award_path,
        output_path=output_path,
    )
    active_model = selected_model(model)
    active_client = client or load_openai_client()
    top_level_clauses, classified_clauses = classify_groups(
        groups=inputs.groups,
        client=active_client,
        model=active_model,
    )
    result = build_result_artifact(
        source_path=inputs.source_path,
        model=active_model,
        top_level_clauses=top_level_clauses,
        classified_clauses=classified_clauses,
    )
    write_result(inputs.destination, result)
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
        help="OpenAI model to use. Defaults to PAYMENT_CLAUSE_CLASSIFIER_MODEL or gpt-5.4-mini.",
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
        from .deterministic import output_path_for_award

        destination = output_path_for_award(args.award_path)
    print(f"Payment classification saved to {destination}")
    print(
        f"Classified {len(result['top_level_clauses'])} top-level clauses and "
        f"{len(result['classified_clauses'])} descendant clauses."
    )
