"""Run one explicit step-3 overtime ruleset from start to finish."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    explicit_ruleset_output_path,
)
from src.script_3_part1_classify_overtime_clauses import (
    DEFAULT_CLASSIFICATION_PATH,
    overtime_clause_classification_path_for_source,
    prepare_overtime_clause_classifications,
)
from src.script_3_part2_generate_overtime_interpretation import (
    DEFAULT_EXPERT_RUN_COUNT,
    generate_overtime_interpretation_from_classifications,
)


RULESET_CHOICES = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
)


def generate_overtime_ruleset(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    *,
    ruleset_key: str,
    clause_classification_output_path: Path | str | None = None,
    output_path: Path | str | None = None,
    model: str | None = None,
    comparison_model: str | None = None,
    expert_run_count: int = DEFAULT_EXPERT_RUN_COUNT,
    client: Any | None = None,
) -> str:
    source_path = Path(classification_path)
    selected_clause_output_path = (
        Path(clause_classification_output_path)
        if clause_classification_output_path
        else overtime_clause_classification_path_for_source(source_path)
    )
    selected_output_path = (
        Path(output_path)
        if output_path
        else explicit_ruleset_output_path(source_path, ruleset_key)
    )

    prepare_overtime_clause_classifications(
        classification_path=source_path,
        classification_output_path=selected_clause_output_path,
        model=model,
        client=client,
        ruleset_key=ruleset_key,
    )
    return generate_overtime_interpretation_from_classifications(
        classification_path=source_path,
        output_path=selected_output_path,
        classification_output_path=selected_clause_output_path,
        model=model,
        comparison_model=comparison_model,
        expert_run_count=expert_run_count,
        client=client,
        ruleset_key=ruleset_key,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one overtime ruleset from a payment classification file."
    )
    parser.add_argument(
        "classification_path",
        nargs="?",
        default=str(DEFAULT_CLASSIFICATION_PATH),
        help="Path to a payment classification JSON file.",
    )
    parser.add_argument(
        "--ruleset",
        choices=RULESET_CHOICES,
        default=OVERTIME_CREATION_RULESET,
        help="The overtime ruleset to generate.",
    )
    parser.add_argument(
        "--classification-output-path",
        default=None,
        help="Optional path for the intermediate clause classification JSON.",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the final ruleset markdown.",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--comparison-model", default=None)
    parser.add_argument(
        "--expert-run-count",
        type=int,
        default=DEFAULT_EXPERT_RUN_COUNT,
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    generate_overtime_ruleset(
        classification_path=args.classification_path,
        ruleset_key=args.ruleset,
        clause_classification_output_path=args.classification_output_path,
        output_path=args.output_path,
        model=args.model,
        comparison_model=args.comparison_model,
        expert_run_count=args.expert_run_count,
    )
    source_path = Path(args.classification_path)
    destination = (
        Path(args.output_path)
        if args.output_path
        else explicit_ruleset_output_path(source_path, args.ruleset)
    )
    print(f"{args.ruleset} ruleset saved to {destination}")


if __name__ == "__main__":
    main()
