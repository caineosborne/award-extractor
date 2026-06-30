"""Step 3 overtime interpretation generator.

Prompt ownership:
- Uses the canonical ruleset prompts in `src/prompts/overtime_ruleset.py`.

This compatibility entrypoint keeps the existing step-3 public API while
delegating the work to two clearer internal scripts:
- `src/script_3_part1_classify_overtime_clauses.py`
- `src/script_3_part2_generate_overtime_interpretation.py`
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.script_3_part1_classify_overtime_clauses import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_MODEL,
    OVERTIME_CLASSIFICATIONS,
    OVERTIME_CREATION_CLASSIFICATIONS,
    OVERTIME_TAGS,
    SCHEMA_VERSION,
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    build_classification_messages,
    build_clause_classification_artifact,
    build_clause_classification_messages,
    classification_artifact,
    classification_output_path_for_classification,
    classification_response_json_schema,
    clause_source_text,
    clause_text,
    classify_overtime_clauses,
    filter_overtime_clauses,
    filter_overtime_creation_clauses,
    filter_overtime_related_clauses,
    format_clauses_for_prompt,
    load_classification,
    load_environment,
    load_or_create_overtime_clause_classifications,
    load_overtime_clause_classification_artifact,
    overtime_clause_classification_path_for_source,
    prepare_overtime_clause_classifications,
    select_overtime_creation_clauses,
    select_overtime_related_clauses,
    validate_overtime_clause_classifications,
)
from src.script_3_part2_generate_overtime_interpretation import (
    DEFAULT_EXPERT_RUN_COUNT,
    EXPERT_RUN_LABELS,
    RULE_ID_ALLOWED_PATTERN,
    build_expert_comparison_messages,
    build_interpretation_messages,
    build_messages,
    candidate_parent_clause_keys,
    compare_expert_interpretation_runs,
    comparison_output_path,
    comparison_response_json_schema,
    deduplicate_preserving_order,
    expert_markdown_output_path,
    format_working_paper_input,
    generate_overtime_interpretation_from_classifications,
    interpretation_output_path_for_source,
    interpretation_response_json_schema,
    load_prepared_clause_classifications,
    output_path_for_classification,
    request_structured_interpretation_run,
    validate_interpretation_rules,
)


def generate_overtime_interpretation(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    output_path: Path | str | None = None,
    classification_output_path: Path | str | None = None,
    model: str | None = None,
    comparison_model: str | None = None,
    expert_run_count: int = 1,
    client: Any | None = None,
) -> str:
    """Run both step-3 parts in sequence and return the rendered markdown."""
    prepare_overtime_clause_classifications(
        classification_path=classification_path,
        classification_output_path=classification_output_path,
        model=model,
        client=client,
    )
    return generate_overtime_interpretation_from_classifications(
        classification_path=classification_path,
        output_path=output_path,
        classification_output_path=classification_output_path,
        model=model,
        comparison_model=comparison_model,
        expert_run_count=expert_run_count,
        client=client,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the end-to-end step-3 entrypoint."""
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
    parser.add_argument(
        "--comparison-model",
        default=None,
        help=(
            "OpenAI model to use for the expert comparison pass when more than one expert "
            "run is used. Defaults to OVERTIME_INTERPRETATION_COMPARISON_MODEL or the "
            "main model."
        ),
    )
    parser.add_argument(
        "--expert-run-count",
        type=int,
        default=DEFAULT_EXPERT_RUN_COUNT,
        help=(
            "Number of independent step 3.4 expert generations to run before comparison. "
            f"Defaults to {DEFAULT_EXPERT_RUN_COUNT}."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    """Run the end-to-end step-3 workflow from the command line."""
    args = parse_args()
    generate_overtime_interpretation(
        classification_path=args.classification_path,
        output_path=args.output_path,
        classification_output_path=args.classification_output_path,
        model=args.model,
        comparison_model=args.comparison_model,
        expert_run_count=args.expert_run_count,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else interpretation_output_path_for_source(args.classification_path)
    )
    print(f"Overtime interpretation saved to {destination}")


if __name__ == "__main__":
    main()
