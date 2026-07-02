"""Run step 5.1 core overtime pseudocode generation."""

from __future__ import annotations

import argparse
from typing import Any
from pathlib import Path

from .core import (
    DEFAULT_OVERTIME_SUMMARY_PATH,
    MAX_VALIDATION_REPAIR_ATTEMPTS,
    RULESET_CHOICES,
)

from .deterministic import resolve_generation_inputs, validate_and_write_outputs
from .llm import (
    load_openai_client,
    request_initial_pseudocode,
    request_repaired_pseudocode,
    selected_model,
)
from .verification import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


def generate_core_overtime_pseudocode(
    summary_path=DEFAULT_OVERTIME_SUMMARY_PATH,
    output_path=None,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str | None = None,
) -> str:
    """Run step 5.1 and write the pseudocode plus validation artifacts."""
    print(f"Step 5.1: Loading source ruleset from {summary_path}")
    inputs = resolve_generation_inputs(
        summary_path=summary_path,
        output_path=output_path,
        ruleset_key=ruleset_key,
    )
    active_client = client or load_openai_client()
    active_model = selected_model(model)
    print(f"Step 5.1: Generating pseudocode with model {active_model}")

    output_text = request_initial_pseudocode(
        client=active_client,
        model=active_model,
        source_path=inputs.source_path,
        summary_text=inputs.summary_text,
        source_inventory=inputs.source_inventory,
        ruleset_key=inputs.effective_ruleset_key,
    )

    repair_attempts = 0

    while True:
        print("Step 5.1: Running deterministic pseudocode validation")
        validation_report, validation_markdown = validate_and_write_outputs(
            destination=inputs.destination,
            output_text=output_text,
            source_inventory=inputs.source_inventory,
        )
        needs_repair = (
            validation_report.failed_rule_count > 0
            and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS
        )
        if not needs_repair:
            print(f"Step 5.1: Wrote pseudocode markdown to {inputs.destination}")
            print(
                "Step 5.1: Wrote validation JSON to "
                f"{validation_json_path_for_pseudocode(inputs.destination)}"
            )
            print(
                "Step 5.1: Wrote validation markdown to "
                f"{validation_markdown_path_for_pseudocode(inputs.destination)}"
            )
            return output_text

        repair_attempts += 1
        print(
            "Step 5.1: Validation found missing coverage. "
            f"Requesting repair attempt {repair_attempts}."
        )
        output_text = request_repaired_pseudocode(
            client=active_client,
            model=active_model,
            source_path=inputs.source_path,
            summary_text=inputs.summary_text,
            source_inventory=inputs.source_inventory,
            initial_pseudocode_markdown=output_text,
            validation_report_markdown=validation_markdown,
            ruleset_key=inputs.effective_ruleset_key,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate core ordinary/overtime pseudocode from an overtime entitlement summary."
    )
    parser.add_argument(
        "summary_path",
        nargs="?",
        default=str(DEFAULT_OVERTIME_SUMMARY_PATH),
        help=(
            "Award code or path to an overtime interpretation markdown file. "
            "When an award code is provided, use the 4B file when present, otherwise 4A, then the revised overtime interpretation."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown core overtime pseudocode output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model to use. Defaults to CORE_OVERTIME_PSEUDOCODE_MODEL or gpt-5.4-mini.",
    )
    parser.add_argument(
        "--ruleset-key",
        choices=RULESET_CHOICES,
        default=None,
        help="Optional ruleset key when resolving an award code input.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    inputs = resolve_generation_inputs(
        summary_path=args.summary_path,
        output_path=args.output_path,
        ruleset_key=args.ruleset_key,
    )
    generate_core_overtime_pseudocode(
        summary_path=args.summary_path,
        output_path=args.output_path,
        model=args.model,
        ruleset_key=args.ruleset_key,
    )
    destination = (
        Path(args.output_path) if args.output_path else inputs.destination
    )
    print(f"Core overtime pseudocode saved to {destination}")
    print(f"Validation report saved to {validation_markdown_path_for_pseudocode(destination)}")
