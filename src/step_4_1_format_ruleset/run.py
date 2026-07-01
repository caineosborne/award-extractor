"""Run step 4.1 ruleset formatting."""

from __future__ import annotations

from typing import Any

from .deterministic import DEFAULT_TEMPLATE_PATH, resolve_formatting_inputs, write_formatted_output
from .llm import load_openai_client, request_formatted_ruleset, selected_model


def summarize_overtime_entitlements(
    interpretation_path,
    output_path=None,
    template_path=DEFAULT_TEMPLATE_PATH,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str | None = None,
) -> str:
    """Run step 4.1 and write the formatted overtime guide."""
    inputs = resolve_formatting_inputs(
        interpretation_path=interpretation_path,
        output_path=output_path,
        template_path=template_path,
        ruleset_key=ruleset_key,
    )
    active_client = client or load_openai_client()
    output_text = request_formatted_ruleset(
        client=active_client,
        model=selected_model(model),
        interpretation_path=inputs.interpretation_path,
        interpretation_markdown=inputs.interpretation_markdown,
        template_path=inputs.template_path,
        template_markdown=inputs.template_markdown,
        ruleset_key=inputs.ruleset_key,
    )
    return write_formatted_output(inputs.output_path, output_text)
