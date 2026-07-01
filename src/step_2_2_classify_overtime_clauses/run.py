"""Run step 2.2 overtime clause classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import OvertimeClauseClassification
from .llm import prepare_overtime_clause_classifications


def run_step_2_2(
    *,
    classification_path: Path | str,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> list[OvertimeClauseClassification]:
    """Run step 2.2 and write the overtime clause classification artifact."""
    return prepare_overtime_clause_classifications(
        classification_path=classification_path,
        classification_output_path=output_path,
        model=model,
        client=client,
    )


def run_step_2_1(
    *,
    classification_path: Path | str,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> list[OvertimeClauseClassification]:
    """Backward-compatible alias for the step 2.2 runner."""
    return run_step_2_2(
        classification_path=classification_path,
        output_path=output_path,
        model=model,
        client=client,
    )
