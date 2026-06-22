from pathlib import Path

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    creator_response_path_for_interpretation,
    default_classification_path_for_award,
    default_interpretation_path_for_award,
    evaluator_feedback_path_for_interpretation,
    interpretation_output_path_for_classification,
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
    revised_output_path_for_interpretation,
)


def test_default_step_3_paths_match_existing_layout():
    assert default_classification_path_for_award("MA000018") == PROJECT_ROOT / Path(
        "data/processed/2_payment_clause_identifier/MA000018_payment_classification.json"
    )
    assert default_interpretation_path_for_award("MA000018") == PROJECT_ROOT / Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"
    )


def test_interpretation_artifact_paths_match_existing_layout():
    interpretation_path = Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"
    )
    classification_path = Path(
        "data/processed/2_payment_clause_identifier/MA000018_payment_classification.json"
    )

    assert interpretation_output_path_for_classification(classification_path) == interpretation_path
    assert resolve_overtime_clause_classification_path(classification_path, None) == Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_clause_classification.json"
    )
    assert evaluator_feedback_path_for_interpretation(interpretation_path) == Path(
        "data/processed/3_overtime_interpretations/feedback/"
        "MA000018_overtime_interpretation_evaluator_feedback.md"
    )
    assert creator_response_path_for_interpretation(interpretation_path) == Path(
        "data/processed/3_overtime_interpretations/feedback/"
        "MA000018_overtime_interpretation_creator_response.md"
    )
    assert revised_output_path_for_interpretation(interpretation_path) == Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md"
    )


def test_resolve_paths_support_award_codes_and_explicit_inputs():
    explicit_interpretation = Path("custom/interpretation.md")
    explicit_classification = Path("custom/classification.json")

    assert resolve_interpretation_path("MA000018") == default_interpretation_path_for_award(
        "MA000018"
    )
    assert resolve_interpretation_path(explicit_interpretation) == explicit_interpretation
    assert resolve_classification_path("MA000018", None) == default_classification_path_for_award(
        "MA000018"
    )
    assert (
        resolve_classification_path(explicit_interpretation, explicit_classification)
        == explicit_classification
    )
