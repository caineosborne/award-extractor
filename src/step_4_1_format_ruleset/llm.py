"""LLM helpers for step 4.1 ruleset formatting."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text as extract_llm_response_text
from src.prompts.step_4_1_format_ruleset import build_messages
from .deterministic import OvertimeEntitlementSummaryError


DEFAULT_MODEL = "gpt-5.4-mini"


def load_environment() -> None:
    """Load the OpenAI environment required by the formatter."""
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeEntitlementSummaryError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 4.1 client."""
    load_environment()
    return OpenAI()


def selected_model(model: str | None) -> str:
    """Resolve the configured step 4.1 model."""
    return model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)


def extract_response_text(response: Any) -> str:
    """Extract plain text from the OpenAI response object."""
    return extract_llm_response_text(response)


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
