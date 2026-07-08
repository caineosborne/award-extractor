"""Step 2.2 stage 5: build and write the clause-classification artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from src.common.output_paths import write_text_output
from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    SCHEMA_VERSION,
)
from src.common.overtime_rulesets import overtime_ruleset_config


def build_clause_classification_artifact(
    source_file: Path | str,
    classifications: Sequence[OvertimeClauseClassification],
    ruleset_key: str,
) -> dict[str, Any]:
    """Build the JSON artifact written by step 2.2."""
    config = overtime_ruleset_config(ruleset_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_key": ruleset_key,
        "source_classification_file": str(source_file),
        "included_categories_for_interpretation": list(config.generation_classifications),
        "clauses": [
            {
                "clause_number": classification.clause_number,
                "classification": classification.classification,
                "classifications": list(classification.classifications),
                "clause_text": classification.clause_text,
                "explanation": classification.explanation,
                "employee_cohort": classification.employee_cohort,
                "work_arrangement": classification.work_arrangement,
                "other_scope_notes": classification.other_scope_notes,
            }
            for classification in classifications
        ],
    }


def write_clause_classification_artifact(
    destination: Path,
    artifact: dict[str, Any],
) -> None:
    """Write the current step 2.2 classification artifact."""
    write_text_output(destination, json.dumps(artifact, indent=2, ensure_ascii=False))
