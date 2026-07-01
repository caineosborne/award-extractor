import argparse
from collections.abc import Sequence

from src.common.active_pipeline_paths import (
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
)
from src.script_3b_agentic_review_workflow import (
    DEFAULT_MAX_FEEDBACK_CYCLES,
    load_openai_environment,
    run_agentic_overtime_interpretation_review,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the agentic step-3B review command."""
    parser = argparse.ArgumentParser(
        description=(
            "Run an agentic creator/evaluator review for a step 3 overtime "
            "interpretation."
        )
    )
    parser.add_argument(
        "award_or_interpretation_path",
        nargs="?",
        default="MA000018",
        help=(
            "Award code such as MA000002, or a path to an overtime interpretation "
            "markdown file."
        ),
    )
    parser.add_argument(
        "--classification-path",
        default=None,
        help=(
            "Optional path to the payment classification JSON file. If omitted, "
            "the path is derived from the award code or interpretation filename."
        ),
    )
    parser.add_argument(
        "--overtime-clause-classification-path",
        default=None,
        help=(
            "Optional path to the Script 3 intermediate overtime clause classification "
            "JSON. If omitted, the path is derived from the payment classification path."
        ),
    )
    parser.add_argument(
        "--creator-model",
        default=None,
        help=(
            "OpenAI creator model to use. Defaults to "
            "OVERTIME_INTERPRETATION_AGENTIC_CREATOR_MODEL or the Script 3 default."
        ),
    )
    parser.add_argument(
        "--evaluator-model",
        default=None,
        help=(
            "OpenAI evaluator model to use. Defaults to "
            "OVERTIME_INTERPRETATION_AGENTIC_EVALUATOR_MODEL or the Script 3 default."
        ),
    )
    parser.add_argument(
        "--max-feedback-cycles",
        type=int,
        default=DEFAULT_MAX_FEEDBACK_CYCLES,
        help=f"Maximum evaluator feedback cycles. Defaults to {DEFAULT_MAX_FEEDBACK_CYCLES}.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the agentic step-3B review CLI."""
    args = parse_args(argv)
    load_openai_environment()

    interpretation_path = resolve_interpretation_path(args.award_or_interpretation_path)
    classification_path = resolve_classification_path(
        args.award_or_interpretation_path,
        args.classification_path,
    )
    overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        classification_path,
        args.overtime_clause_classification_path,
    )

    print(f"Starting agentic overtime interpretation review for {interpretation_path}")
    print(f"Using classification source {classification_path}")
    print(f"Using overtime clause classification source {overtime_clause_classification_path}")

    artifacts = run_agentic_overtime_interpretation_review(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        creator_model=args.creator_model,
        evaluator_model=args.evaluator_model,
        max_feedback_cycles=args.max_feedback_cycles,
        status_callback=lambda message: print(f"Status: {message}"),
    )

    print(f"Agentic conversation saved to {artifacts.conversation_path}")
    print(f"Revised overtime interpretation saved to {artifacts.revised_interpretation_path}")
    print(f"Evaluator feedback cycles used: {artifacts.evaluator_feedback_cycles}")


if __name__ == "__main__":
    main()
