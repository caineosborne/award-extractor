"""LLM helpers for step 2.2 overtime clause classification."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.output_paths import write_text_output
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET

from .core import (
    DEFAULT_MODEL,
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    build_clause_classification_artifact,
    classify_overtime_clauses,
    load_environment,
    load_overtime_clause_classification_artifact,
)
from .deterministic import (
    load_step_2_classification,
    output_path_for_classification,
    select_overtime_source_clauses,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return a client."""
    load_environment()
    return OpenAI()


def model_name(selected_model: str | None) -> str:
    """Resolve the configured model for step 2.2."""
    return selected_model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)


def load_or_generate_clause_classifications(
    *,
    source_path: Path,
    overtime_clauses: dict[str, Any],
    output_path: Path,
    client: Any | None,
    selected_model: str | None,
) -> list[OvertimeClauseClassification]:
    """Reuse a valid step-2.2 artifact or regenerate it with the model."""
    if output_path.exists():
        try:
            return load_overtime_clause_classification_artifact(
                output_path,
                overtime_clauses,
                OVERTIME_CREATION_RULESET,
            )
        except OvertimeInterpretationError:
            # Step 2.1 may have been rerun, making the existing step 2.2 artifact
            # inconsistent with the current shortlisted clause set. Regenerate it.
            pass

    active_client = client or load_openai_client()
    classifications = classify_overtime_clauses(
        overtime_clauses,
        active_client,
        model_name(selected_model),
        OVERTIME_CREATION_RULESET,
    )
    artifact = build_clause_classification_artifact(
        source_path,
        classifications,
        OVERTIME_CREATION_RULESET,
    )
    write_text_output(
        output_path,
        json.dumps(artifact, indent=2, ensure_ascii=False),
    )
    return classifications


def prepare_overtime_clause_classifications(
    *,
    classification_path: Path | str,
    classification_output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> list[OvertimeClauseClassification]:
    """Run step 2.2 and write the intermediate overtime clause classification."""
    source_path = Path(classification_path)
    data = load_step_2_classification(source_path)
    overtime_clauses = select_overtime_source_clauses(data)
    destination = (
        Path(classification_output_path)
        if classification_output_path is not None
        else output_path_for_classification(source_path)
    )

    return load_or_generate_clause_classifications(
        source_path=source_path,
        overtime_clauses=overtime_clauses,
        output_path=destination,
        client=client,
        selected_model=model,
    )
