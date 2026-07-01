"""Run step 5.1 core overtime pseudocode generation."""

from __future__ import annotations

from typing import Any

from src.script_5b_generate_overtime_pseudocode import (
    DEFAULT_OVERTIME_SUMMARY_PATH,
    MAX_VALIDATION_REPAIR_ATTEMPTS,
)

from .deterministic import resolve_generation_inputs, validate_and_write_outputs
from .llm import (
    load_openai_client,
    request_initial_pseudocode,
    request_repaired_pseudocode,
    selected_model,
)


def generate_core_overtime_pseudocode(
    summary_path=DEFAULT_OVERTIME_SUMMARY_PATH,
    output_path=None,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str | None = None,
) -> str:
    """Run step 5.1 and write the pseudocode plus validation artifacts."""
    inputs = resolve_generation_inputs(
        summary_path=summary_path,
        output_path=output_path,
        ruleset_key=ruleset_key,
    )
    active_client = client or load_openai_client()
    active_model = selected_model(model)

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
            return output_text

        repair_attempts += 1
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
