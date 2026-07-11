"""Step 5.1 stage 2: request initial and repaired pseudocode drafts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.pipeline_runtime import build_openai_client, load_openai_environment
from src.common.prompt_logging import log_llm_prompt
from src.prompts.step_5_1_generate_pseudocode import build_messages, build_repair_messages

from .schema import DEFAULT_MODEL, CoreOvertimePseudocodeError


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 5.1 client."""
    load_openai_environment(
        env_path=Path(__file__).resolve().parents[2] / ".env",
        error_type=CoreOvertimePseudocodeError,
    )
    return build_openai_client()


def resolve_model(model: str | None) -> str:
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
    messages = build_messages(
        str(source_path), summary_text, source_inventory, ruleset_key
    )
    log_llm_prompt(f"5.1 {ruleset_key} Pseudocode Creation", messages)
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "medium"},
        )
    except Exception as exc:
        raise CoreOvertimePseudocodeError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise CoreOvertimePseudocodeError("OpenAI response did not include output text.")

    if output_text.endswith("\n"):
        return output_text
    return output_text + "\n"


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
    messages = build_repair_messages(
        source_file=str(source_path),
        overtime_summary_markdown=summary_text,
        source_inventory=source_inventory,
        initial_pseudocode_markdown=initial_pseudocode_markdown,
        validation_report_markdown=validation_report_markdown,
        ruleset_key=ruleset_key,
    )
    log_llm_prompt(f"5.1 {ruleset_key} Pseudocode Repair", messages)
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "medium"},
        )
    except Exception as exc:
        raise CoreOvertimePseudocodeError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise CoreOvertimePseudocodeError("OpenAI response did not include output text.")

    if output_text.endswith("\n"):
        return output_text
    return output_text + "\n"
