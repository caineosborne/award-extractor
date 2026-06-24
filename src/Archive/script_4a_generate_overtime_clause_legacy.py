import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.Archive.script_4a_summarize_overtime_legacy import (
    load_environment,
    output_path_for_classification,
    summarize_overtime_entitlements,
)
from src.script_3_interpret_overtime import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_EXPERT_RUN_COUNT,
    generate_overtime_interpretation,
    output_path_for_classification as interpretation_path_for_classification,
)


DEFAULT_MODEL = "gpt-5.4-mini"


@dataclass(frozen=True)
class OvertimeClauseArtifacts:
    interpretation_path: Path
    entitlements_path: Path
    interpretation_markdown: str
    entitlements_markdown: str


def generate_overtime_clause_artifacts(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    interpretation_output_path: Path | str | None = None,
    entitlements_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OvertimeClauseArtifacts:
    selected_model = model or os.getenv("OVERTIME_CLAUSE_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    interpretation_path = (
        Path(interpretation_output_path)
        if interpretation_output_path
        else interpretation_path_for_classification(source_path)
    )
    entitlements_path = (
        Path(entitlements_output_path)
        if entitlements_output_path
        else output_path_for_classification(source_path)
    )

    interpretation_markdown = generate_overtime_interpretation(
        classification_path=source_path,
        output_path=interpretation_path,
        model=selected_model,
        expert_run_count=DEFAULT_EXPERT_RUN_COUNT,
        client=client,
    )
    entitlements_markdown = summarize_overtime_entitlements(
        interpretation_path=interpretation_path,
        output_path=entitlements_path,
        model=selected_model,
        client=client,
    )

    return OvertimeClauseArtifacts(
        interpretation_path=interpretation_path,
        entitlements_path=entitlements_path,
        interpretation_markdown=interpretation_markdown,
        entitlements_markdown=entitlements_markdown,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate overtime interpretation and entitlement markdown artifacts."
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
        "--interpretation-output-path",
        default=None,
        help="Optional path for the markdown overtime interpretation output.",
    )
    parser.add_argument(
        "--entitlements-output-path",
        default=None,
        help="Optional path for the markdown overtime entitlement output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to OVERTIME_CLAUSE_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    artifacts = generate_overtime_clause_artifacts(
        classification_path=args.classification_path,
        interpretation_output_path=args.interpretation_output_path,
        entitlements_output_path=args.entitlements_output_path,
        model=args.model,
    )
    print(f"Overtime interpretation saved to {artifacts.interpretation_path}")
    print(f"Overtime entitlement summary saved to {artifacts.entitlements_path}")


if __name__ == "__main__":
    main()
