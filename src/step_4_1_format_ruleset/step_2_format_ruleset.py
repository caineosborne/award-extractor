"""Step 4.1 stage 2: request and write the formatted ruleset."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.output_paths import write_text_output
from src.common.pipeline_runtime import load_openai_environment
from src.prompts.step_4_1_format_ruleset import build_messages

from .schema import DEFAULT_MODEL, OvertimeEntitlementSummaryError
from .step_1_load_inputs import strip_wrapping_markdown_fence


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 4.1 client."""
    load_openai_environment(
        env_path=Path(__file__).resolve().parents[2] / ".env",
        error_type=OvertimeEntitlementSummaryError,
    )
    return OpenAI()


def resolve_model(model: str | None) -> str:
    """Resolve the configured step 4.1 model."""
    return model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)


def request_formatted_ruleset(
    *,
    client: Any,
    model: str,
    interpretation_path: Path,
    interpretation_markdown: str,
    template_path: Path,
    template_markdown: str,
    ruleset_key: str,
) -> str:
    """Request the formatted overtime guide from the model."""
    response = client.responses.create(
        model=model,
        input=build_messages(
            interpretation_path,
            interpretation_markdown,
            template_path,
            template_markdown,
            ruleset_key,
        ),
    )
    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeEntitlementSummaryError("OpenAI response did not include output text.")
    return output_text


def write_formatted_output(destination: Path, output_text: str) -> str:
    """Clean and write the formatted ruleset output."""
    cleaned_output = strip_wrapping_markdown_fence(output_text)
    write_text_output(destination, cleaned_output)
    return cleaned_output
