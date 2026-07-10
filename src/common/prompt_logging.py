"""Write the exact prompts sent to the LLM to the audit log."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.common.output_naming import PROJECT_ROOT


PROMPT_LOG_PATH = PROJECT_ROOT / "MAxxx120.log"
_active_prompt_log_path = PROMPT_LOG_PATH


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
    log_parts = [f"\n{'=' * 80}\n{heading}\n{'=' * 80}\n"]

    for message in messages:
        role = str(message.get("role", "message")).upper()
        content = message.get("content", "")
        log_parts.append(f"\n--- {role} ---\n{content}\n")

    selected_log_path.parent.mkdir(parents=True, exist_ok=True)
    with selected_log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("".join(log_parts))
