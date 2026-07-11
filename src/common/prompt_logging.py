"""Write LLM requests and responses to the audit log."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_active_prompt_log_path: Path | None = None


def configure_prompt_log(log_path: Path) -> None:
    """Set the prompt log path for the active pipeline run."""
    global _active_prompt_log_path
    _active_prompt_log_path = log_path


def log_llm_prompt(
    heading: str,
    messages: Sequence[Mapping[str, Any]],
    log_path: Path | None = None,
) -> None:
    """Append one raw LLM request to the active run's prompt log."""
    selected_log_path = log_path or _active_prompt_log_path
    if selected_log_path is None:
        return
    log_parts = [f"\n{'=' * 80}\n{heading}\n{'=' * 80}\n"]

    for message in messages:
        role = str(message.get("role", "message")).upper()
        content = message.get("content", "")
        log_parts.append(f"\n--- {role} ---\n{content}\n")

    selected_log_path.parent.mkdir(parents=True, exist_ok=True)
    with selected_log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("".join(log_parts))


def log_llm_response(
    heading: str,
    response: Any,
    extracted_text: str,
    log_path: Path | None = None,
) -> None:
    """Append the complete model response for audit and failure diagnosis."""
    selected_log_path = log_path or _active_prompt_log_path
    if selected_log_path is None:
        return

    model_dump_json = getattr(response, "model_dump_json", None)
    if callable(model_dump_json):
        response_payload = model_dump_json(indent=2)
    elif isinstance(response, Mapping):
        response_payload = json.dumps(response, indent=2, default=str)
    else:
        response_payload = repr(response)

    displayed_text = extracted_text or "<no text extracted>"
    log_text = (
        f"\n{'=' * 80}\n{heading}\n{'=' * 80}\n"
        f"\n--- EXTRACTED TEXT ---\n{displayed_text}\n"
        f"\n--- RAW RESPONSE ---\n{response_payload}\n"
    )
    selected_log_path.parent.mkdir(parents=True, exist_ok=True)
    with selected_log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(log_text)


def log_llm_error(
    heading: str,
    error: Exception,
    log_path: Path | None = None,
) -> None:
    """Append an LLM request error to the audit log without suppressing it."""
    selected_log_path = log_path or _active_prompt_log_path
    if selected_log_path is None:
        return

    log_text = (
        f"\n{'=' * 80}\n{heading}\n{'=' * 80}\n"
        f"{type(error).__name__}: {error}\n"
    )
    selected_log_path.parent.mkdir(parents=True, exist_ok=True)
    with selected_log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(log_text)
