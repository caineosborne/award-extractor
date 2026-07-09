"""Step 3.2 stage 1: load source artifacts and resolve output context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.active_pipeline_paths import resolve_overtime_clause_classification_path
from src.common.overtime_clause_classification import load_classification
from src.common.overtime_rules import (
    OVERTIME_RULE_SCHEMA_VERSION,
    json_output_path_for_markdown,
    load_rules_artifact,
    rules_from_markdown_fallback,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.common.pipeline_io import load_json_object, load_text_file

from .schema import OvertimeInterpretationReviewError


@dataclass(frozen=True)
class Step3ReviewInputs:
    """Loaded deterministic inputs for step 3.2 review."""

    selected_interpretation_path: Path
    selected_classification_path: Path
    selected_overtime_clause_classification_path: Path
    selected_ruleset_key: str
    original_rules_artifact: dict[str, Any]
    interpretation_markdown: str
    classification_data: dict[str, Any]
    overtime_clause_classification: dict[str, Any]


def load_required_text(path: Path | str, description: str) -> str:
    """Load a required text artifact for the review workflow."""
    return load_text_file(path, description, error_type=OvertimeInterpretationReviewError)


def load_required_json(path: Path | str, description: str) -> dict[str, Any]:
    """Load a required JSON artifact for the review workflow."""
    return load_json_object(path, description, error_type=OvertimeInterpretationReviewError)


def load_review_inputs(
    *,
    interpretation_path,
    classification_path,
    overtime_clause_classification_path,
    ruleset_key: str | None,
) -> Step3ReviewInputs:
    """Load and validate the deterministic source artifacts for step 3.2."""
    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    try:
        inferred_ruleset_key = infer_overtime_ruleset_key_from_path(selected_interpretation_path)
    except ValueError:
        inferred_ruleset_key = OVERTIME_CREATION_RULESET

    selected_overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        selected_classification_path,
        overtime_clause_classification_path,
        selected_interpretation_path,
    )
    selected_rules_json_path = json_output_path_for_markdown(selected_interpretation_path)

    if selected_rules_json_path.exists():
        original_rules_artifact = load_rules_artifact(
            selected_rules_json_path,
            expected_schema_version=OVERTIME_RULE_SCHEMA_VERSION,
        )
        interpretation_markdown = str(original_rules_artifact["rendered_markdown"])
    else:
        interpretation_markdown = load_required_text(
            selected_interpretation_path,
            "Overtime interpretation markdown",
        )
        original_rules_artifact = {
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "source_classification_file": str(selected_classification_path),
            "source_clause_classification_file": str(
                selected_overtime_clause_classification_path
            ),
            "rendered_markdown": interpretation_markdown,
            "rules": rules_from_markdown_fallback(
                interpretation_markdown,
                source_path=selected_interpretation_path,
            ),
        }

    classification_data = load_classification(selected_classification_path)
    classified_clauses = classification_data.get("classified_clauses")
    if not classified_clauses:
        raise OvertimeInterpretationReviewError(
            f"No classified clauses found in: {selected_classification_path}"
        )

    overtime_clause_classification = load_required_json(
        selected_overtime_clause_classification_path,
        "Step 2.2 overtime clause classification JSON",
    )

    selected_ruleset_key = ruleset_key or inferred_ruleset_key

    return Step3ReviewInputs(
        selected_interpretation_path=selected_interpretation_path,
        selected_classification_path=selected_classification_path,
        selected_overtime_clause_classification_path=selected_overtime_clause_classification_path,
        selected_ruleset_key=selected_ruleset_key,
        original_rules_artifact=original_rules_artifact,
        interpretation_markdown=interpretation_markdown,
        classification_data=classification_data,
        overtime_clause_classification=overtime_clause_classification,
    )
