from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.output_naming import (
    award_json_path_for_output_stem,
    classification_path_for_award_json,
    core_overtime_pseudocode_path_for_interpretation,
    creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation,
    output_stem_for_award,
    overtime_clause_classification_path_for_classification,
    raw_html_path_for_output_stem,
    revised_interpretation_path_for_interpretation,
    interpretation_path_for_classification,
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


@dataclass(frozen=True)
class ActivePipelineContext:
    """Deterministic path context for one active pipeline run."""

    award_code: str
    suffix: str | None
    output_stem: str
    url: str
    raw_html_path: Path
    award_json_path: Path
    classification_path: Path
    overtime_clause_classification_path: Path
    interpretation_path: Path
    evaluator_feedback_path: Path
    creator_response_path: Path
    revised_interpretation_path: Path
    core_overtime_pseudocode_path: Path
    core_overtime_validation_json_path: Path
    core_overtime_validation_markdown_path: Path


def build_active_pipeline_context(
    award_code: str,
    suffix: str | None,
    url: str,
) -> ActivePipelineContext:
    """Build all deterministic artifact paths for one active pipeline run."""
    output_stem = output_stem_for_award(award_code, suffix)
    raw_html_path = raw_html_path_for_output_stem(output_stem)
    award_json_path = award_json_path_for_output_stem(output_stem)
    classification_path = classification_path_for_award_json(award_json_path)
    overtime_clause_classification_path = (
        overtime_clause_classification_path_for_classification(classification_path)
    )
    interpretation_path = interpretation_path_for_classification(classification_path)
    evaluator_feedback_path = evaluator_feedback_path_for_interpretation(
        interpretation_path
    )
    creator_response_path = creator_response_path_for_interpretation(
        interpretation_path
    )
    revised_interpretation_path = revised_interpretation_path_for_interpretation(
        interpretation_path
    )
    core_overtime_pseudocode_path = core_overtime_pseudocode_path_for_interpretation(
        revised_interpretation_path
    )
    core_overtime_validation_json_path = validation_json_path_for_pseudocode(
        core_overtime_pseudocode_path
    )
    core_overtime_validation_markdown_path = validation_markdown_path_for_pseudocode(
        core_overtime_pseudocode_path
    )

    return ActivePipelineContext(
        award_code=award_code,
        suffix=suffix,
        output_stem=output_stem,
        url=url,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        interpretation_path=interpretation_path,
        evaluator_feedback_path=evaluator_feedback_path,
        creator_response_path=creator_response_path,
        revised_interpretation_path=revised_interpretation_path,
        core_overtime_pseudocode_path=core_overtime_pseudocode_path,
        core_overtime_validation_json_path=core_overtime_validation_json_path,
        core_overtime_validation_markdown_path=core_overtime_validation_markdown_path,
    )
