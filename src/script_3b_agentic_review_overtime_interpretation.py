import argparse
from collections.abc import Sequence
from pathlib import Path

from src.overtime_interpretation_agentic_review import (
    DEFAULT_MAX_FEEDBACK_CYCLES,
    load_openai_environment,
    run_agentic_overtime_interpretation_review,
)
from src.script_3b_review_overtime_interpretation import (
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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
        "--conversation-output-path",
        default=None,
        help="Optional path for the agentic creator/evaluator conversation markdown.",
    )
    parser.add_argument(
        "--revised-output-path",
        default=None,
        help="Optional path for the revised overtime interpretation markdown.",
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
        conversation_output_path=(
            Path(args.conversation_output_path)
            if args.conversation_output_path
            else None
        ),
        revised_output_path=(
            Path(args.revised_output_path) if args.revised_output_path else None
        ),
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
