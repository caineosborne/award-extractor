"""LLM helpers for step 4.1 ruleset formatting."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.prompts.overtime_guide_formatting import build_messages
from src.script_4a_summarize_overtime import (
    DEFAULT_MODEL,
    OvertimeEntitlementSummaryError,
    extract_response_text,
    load_environment,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 4.1 client."""
    load_environment()
    return OpenAI()


def selected_model(model: str | None) -> str:
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
