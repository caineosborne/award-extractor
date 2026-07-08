"""Run step 2.2 overtime clause classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    classification_output_path_for_source,
    load_classification,
    select_ruleset_related_clauses,
)
from .step_3_classify_overtime import (
    classify_overtime_clauses,
    load_openai_client,
    model_name,
    select_overtime_creation_clauses,
)
from .step_4_build_penalties import build_deterministic_penalties_classifications
from .step_5_write_artifact import (
    build_clause_classification_artifact,
    write_clause_classification_artifact,
)
from src.common.overtime_rulesets import (
    PENALTIES_RULESET,
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)


def run_step_2_2(
    *,
    classification_path: Path | str,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str = "overtime_creation",
) -> list[OvertimeClauseClassification]:
    """Run step 2.2 and write the overtime clause classification artifact."""
    print(
        "Step 2.2: Loading payment classification JSON from "
        f"{classification_path}"
    )
    source_path = Path(classification_path)
    data = load_classification(source_path)
    config = overtime_ruleset_config(ruleset_key)
    overtime_clauses = select_ruleset_related_clauses(data, config.source_tags)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            "No ruleset source clauses were found in step 2 output."
        )

    destination = (
        Path(output_path)
        if output_path is not None
        else classification_output_path_for_source(source_path, ruleset_key)
    )

    if ruleset_key == PENALTIES_RULESET:
        classifications = build_deterministic_penalties_classifications(
            overtime_clauses
        )
    else:
        active_client = client or load_openai_client()
        active_model = model_name(model)
        raw_classifications = classify_overtime_clauses(
            overtime_clauses,
            active_client,
            active_model,
            ruleset_key,
        )
        classifications = (
            raw_classifications
            if ruleset_key == OVERTIME_CREATION_RULESET
            else select_overtime_creation_clauses(raw_classifications, ruleset_key)
        )

    artifact = build_clause_classification_artifact(
        source_path,
        classifications,
        ruleset_key,
    )
    write_clause_classification_artifact(destination, artifact)
    print(f"Step 2.2: Wrote overtime clause classification JSON to {destination}")
    print(
        "Step 2.2: Classified "
        f"{len(classifications)} ruleset-related clauses for review"
    )
    return classifications
