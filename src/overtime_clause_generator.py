import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.core_overtime_pseudocode import (
    generate_core_overtime_pseudocode,
    output_path_for_summary,
)
from src.overtime_entitlement_summary import (
    DEFAULT_CLASSIFICATION_PATH,
    load_environment,
    output_path_for_classification,
    summarize_overtime_entitlements,
)


DEFAULT_MODEL = "gpt-5.4-mini"


@dataclass(frozen=True)
class OvertimeClauseArtifacts:
    entitlements_path: Path
    pseudocode_path: Path
    entitlements_markdown: str
    pseudocode_markdown: str


def generate_overtime_clause_artifacts(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    entitlements_output_path: Path | str | None = None,
    pseudocode_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OvertimeClauseArtifacts:
    selected_model = model or os.getenv("OVERTIME_CLAUSE_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(classification_path)
    entitlements_path = (
        Path(entitlements_output_path)
        if entitlements_output_path
        else output_path_for_classification(source_path)
    )
    pseudocode_path = (
        Path(pseudocode_output_path)
        if pseudocode_output_path
        else output_path_for_summary(entitlements_path)
    )

    entitlements_markdown = summarize_overtime_entitlements(
        classification_path=source_path,
        output_path=entitlements_path,
        model=selected_model,
        client=client,
    )
    pseudocode_markdown = generate_core_overtime_pseudocode(
        summary_path=entitlements_path,
        output_path=pseudocode_path,
        model=selected_model,
        client=client,
    )

    return OvertimeClauseArtifacts(
        entitlements_path=entitlements_path,
        pseudocode_path=pseudocode_path,
        entitlements_markdown=entitlements_markdown,
        pseudocode_markdown=pseudocode_markdown,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate overtime entitlement and pseudocode markdown artifacts."
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
        "--entitlements-output-path",
        default=None,
        help="Optional path for the markdown overtime entitlement output.",
    )
    parser.add_argument(
        "--pseudocode-output-path",
        default=None,
        help="Optional path for the markdown overtime pseudocode output.",
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
        entitlements_output_path=args.entitlements_output_path,
        pseudocode_output_path=args.pseudocode_output_path,
        model=args.model,
    )
    print(f"Overtime entitlement summary saved to {artifacts.entitlements_path}")
    print(f"Overtime pseudocode saved to {artifacts.pseudocode_path}")


if __name__ == "__main__":
    main()
