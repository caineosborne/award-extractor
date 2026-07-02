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
    destination = Path(output_path) if output_path is not None else None
    print(
        "Step 2.2: Loading payment classification JSON from "
        f"{classification_path}"
    )
    classifications = prepare_overtime_clause_classifications(
        classification_path=classification_path,
        classification_output_path=output_path,
        model=model,
        client=client,
    )
    if destination is not None:
        print(f"Step 2.2: Wrote overtime clause classification JSON to {destination}")
    print(
        "Step 2.2: Classified "
        f"{len(classifications)} overtime-related clauses for review"
    )
    return classifications
