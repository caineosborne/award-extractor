"""Run step 4.1 ruleset formatting."""

from __future__ import annotations

from typing import Any

from .schema import DEFAULT_TEMPLATE_PATH
from .step_1_load_inputs import resolve_formatting_inputs
from .step_2_format_ruleset import (
    load_openai_client,
    request_formatted_ruleset,
    resolve_model,
    validate_formatted_ruleset_coverage,
    write_formatted_ruleset_metadata,
    write_formatted_output,
)


def summarize_overtime_entitlements(
    interpretation_path,
    output_path=None,
    template_path=DEFAULT_TEMPLATE_PATH,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str | None = None,
    validation_warnings_output: list[str] | None = None,
) -> str:
    """Run step 4.1 and write the formatted overtime guide."""
    print(f"Step 4.1: Loading revised ruleset from {interpretation_path}")
    inputs = resolve_formatting_inputs(
        interpretation_path=interpretation_path,
        output_path=output_path,
        template_path=template_path,
        ruleset_key=ruleset_key,
    )
    active_client = client or load_openai_client()
    selected_format_model = resolve_model(model)
    print(f"Step 4.1: Formatting ruleset with model {selected_format_model}")
    output_text = request_formatted_ruleset(
        client=active_client,
        model=selected_format_model,
        interpretation_path=inputs.interpretation_path,
        interpretation_markdown=inputs.interpretation_markdown,
        template_path=inputs.template_path,
        template_markdown=inputs.template_markdown,
        ruleset_key=inputs.ruleset_key,
    )
    validation_warnings = validate_formatted_ruleset_coverage(
        reviewed_ruleset_markdown=inputs.interpretation_markdown,
        formatted_ruleset_markdown=output_text,
    )
    if validation_warnings_output is not None:
        validation_warnings_output.extend(validation_warnings)

    if validation_warnings:
        print("Step 4.1: Formatting coverage warnings detected.")
        for warning in validation_warnings:
            print(f"- {warning}")

    written_output = write_formatted_output(inputs.output_path, output_text)
    write_formatted_ruleset_metadata(
        destination=inputs.output_path,
        source_path=inputs.interpretation_path,
        rendered_markdown=written_output,
        validation_warnings=validation_warnings,
    )
    print(f"Step 4.1: Wrote formatted ruleset to {inputs.output_path}")
    return written_output
