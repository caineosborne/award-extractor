"""Deterministic helpers for step 2.2 overtime clause classification."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .core import (
    OvertimeInterpretationError,
    load_classification,
    overtime_clause_classification_path_for_source,
    select_ruleset_related_clauses,
)


def load_step_2_classification(classification_path: Path | str) -> dict[str, Any]:
    """Load the upstream step-2 payment classification artifact."""
    return load_classification(classification_path)


def select_overtime_source_clauses(data: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the clauses relevant to overtime ruleset drafting."""
    overtime_clauses = select_ruleset_related_clauses(data)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            "No overtime source clauses were found in step 2 output."
        )

    return overtime_clauses


def output_path_for_classification(classification_path: Path | str) -> Path:
    """Return the canonical step-2.2 output path for one step-2.1 input."""
    return overtime_clause_classification_path_for_source(classification_path)
