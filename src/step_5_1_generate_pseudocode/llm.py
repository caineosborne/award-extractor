"""LLM helpers for step 5.1 pseudocode generation."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from src.script_5b_generate_overtime_pseudocode import (
    DEFAULT_MODEL,
    build_messages,
    build_repair_messages,
    load_environment,
    request_pseudocode_output,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 5.1 client."""
    load_environment()
    return OpenAI()


def selected_model(model: str | None) -> str:
    """Resolve the configured step 5.1 model."""
    return model or os.getenv("CORE_OVERTIME_PSEUDOCODE_MODEL", DEFAULT_MODEL)


def request_initial_pseudocode(
    *,
    client: Any,
    model: str,
    source_path,
    summary_text: str,
    source_inventory,
    ruleset_key: str,
) -> str:
    """Request the first pseudocode draft."""
    return request_pseudocode_output(
        client=client,
        model=model,
        messages=build_messages(
            str(source_path),
            summary_text,
            source_inventory,
            ruleset_key,
        ),
    )


def request_repaired_pseudocode(
    *,
    client: Any,
    model: str,
    source_path,
    summary_text: str,
    source_inventory,
    initial_pseudocode_markdown: str,
    validation_report_markdown: str,
    ruleset_key: str,
) -> str:
    """Request one repaired pseudocode draft after deterministic validation fails."""
    return request_pseudocode_output(
        client=client,
        model=model,
        messages=build_repair_messages(
            source_file=str(source_path),
            overtime_summary_markdown=summary_text,
            source_inventory=source_inventory,
            initial_pseudocode_markdown=initial_pseudocode_markdown,
            validation_report_markdown=validation_report_markdown,
            ruleset_key=ruleset_key,
        ),
    )
