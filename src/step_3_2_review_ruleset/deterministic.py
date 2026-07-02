"""Deterministic helpers for step 3.2 ruleset review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.active_pipeline_paths import (
    creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation,
    resolve_overtime_clause_classification_path,
    revised_output_path_for_interpretation,
)
from src.common.overtime_rules import (
    OVERTIME_RULE_SCHEMA_VERSION,
    clause_coverage_warnings,
    decision_output_path_for_markdown,
    json_output_path_for_markdown,
    make_json_serializable,
    prepend_validation_warnings,
    rule_to_dict,
    load_rules_artifact,
    rules_from_markdown_fallback,
    write_rules_artifact,
)
from src.common.output_paths import write_text_output
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.step_2_2_classify_overtime_clauses.core import load_classification

from .core import (
    OvertimeInterpretationReviewArtifacts,
    OvertimeInterpretationReviewError,
    load_json_file,
    load_text_file,
)


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


def load_review_source_artifacts(
    interpretation_path: Path | str,
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> tuple[Path, Path, Path, str, dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Load and validate all source artifacts needed for the step-3.2 review."""
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
        interpretation_markdown = load_text_file(
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

    overtime_clause_classification = load_json_file(
        selected_overtime_clause_classification_path,
        "Step 2.2 overtime clause classification JSON",
    )

    return (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        inferred_ruleset_key,
        original_rules_artifact,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    )


def load_review_inputs(
    *,
    interpretation_path,
    classification_path,
    overtime_clause_classification_path,
    ruleset_key: str | None,
) -> Step3ReviewInputs:
    """Load and validate the deterministic source artifacts for step 3.2."""
    (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        inferred_ruleset_key,
        original_rules_artifact,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    ) = load_review_source_artifacts(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
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


def write_review_outputs(
    *,
    inputs: Step3ReviewInputs,
    evaluator_feedback_data: dict[str, Any],
    evaluator_feedback_markdown: str,
    creator_response_data: dict[str, Any],
    creator_response_markdown: str,
    revised_interpretation_markdown: str,
    reviewed_rules_artifact: dict[str, Any],
    feedback_output_path=None,
    creator_response_output_path=None,
    revised_output_path=None,
) -> OvertimeInterpretationReviewArtifacts:
    """Write the auditable step 3.2 review outputs."""
    feedback_path = (
        Path(feedback_output_path)
        if feedback_output_path
        else evaluator_feedback_path_for_interpretation(inputs.selected_interpretation_path)
    )
    creator_response_path = (
        Path(creator_response_output_path)
        if creator_response_output_path
        else creator_response_path_for_interpretation(inputs.selected_interpretation_path)
    )
    revised_path = (
        Path(revised_output_path)
        if revised_output_path
        else revised_output_path_for_interpretation(inputs.selected_interpretation_path)
    )
    feedback_json_path = decision_output_path_for_markdown(feedback_path)
    creator_response_json_path = decision_output_path_for_markdown(creator_response_path)
    revised_json_path = json_output_path_for_markdown(revised_path)
    revised_validation_warnings = clause_coverage_warnings(
        original_rules=inputs.original_rules_artifact["rules"],
        revised_rules=reviewed_rules_artifact["rules"],
        context_label="The earlier draft",
    )
    revised_interpretation_markdown = prepend_validation_warnings(
        revised_interpretation_markdown,
        revised_validation_warnings,
    )

    write_text_output(feedback_path, evaluator_feedback_markdown)
    write_text_output(
        feedback_json_path,
        json.dumps(
            make_json_serializable(evaluator_feedback_data),
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_text_output(creator_response_path, creator_response_markdown)
    write_text_output(
        creator_response_json_path,
        json.dumps(
            make_json_serializable(creator_response_data),
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_rules_artifact(
        json_path=revised_json_path,
        markdown_path=revised_path,
        artifact={
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "source_classification_file": str(inputs.selected_classification_path),
            "source_clause_classification_file": str(
                inputs.selected_overtime_clause_classification_path
            ),
            "source_original_rules_file": str(
                json_output_path_for_markdown(inputs.selected_interpretation_path)
            ),
            "source_evaluator_feedback_file": str(feedback_json_path),
            "review_decisions": reviewed_rules_artifact["review_decisions"],
            "rendered_markdown": revised_interpretation_markdown,
            "validation_warnings": revised_validation_warnings,
            "rules": [
                rule_to_dict(rule) for rule in reviewed_rules_artifact["rules"]
            ],
        },
    )

    return OvertimeInterpretationReviewArtifacts(
        evaluator_feedback_path=feedback_path,
        evaluator_feedback_json_path=feedback_json_path,
        creator_response_path=creator_response_path,
        creator_response_json_path=creator_response_json_path,
        revised_interpretation_path=revised_path,
        revised_interpretation_json_path=revised_json_path,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_response_markdown=creator_response_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
    )
