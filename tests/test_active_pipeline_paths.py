from pathlib import Path

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    creator_response_path_for_interpretation,
    default_classification_path_for_award,
    default_interpretation_path_for_award,
    evaluator_feedback_path_for_interpretation,
    interpretation_output_path_for_classification,
    ruleset_clause_classification_output_path_for_classification,
    ruleset_output_path_for_classification,
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
    revised_output_path_for_interpretation,
)
from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET


def test_default_step_3_paths_match_award_first_layout():
    assert default_classification_path_for_award("MA000018") == PROJECT_ROOT / Path(
        "data/processed/MA000018/MA000018_payment_classification.json"
    )
    assert default_interpretation_path_for_award("MA000018") == PROJECT_ROOT / Path(
        "data/processed/MA000018/MA000018_overtime_interpretation.md"
    )


def test_interpretation_artifact_paths_match_award_first_layout():
    interpretation_path = Path("data/processed/MA000018/MA000018_overtime_interpretation.md")
    classification_path = Path("data/processed/MA000018/MA000018_payment_classification.json")

    assert interpretation_output_path_for_classification(classification_path) == interpretation_path
    assert resolve_overtime_clause_classification_path(classification_path, None) == Path(
        "data/processed/MA000018/MA000018_overtime_clause_classification.json"
    )
    assert evaluator_feedback_path_for_interpretation(interpretation_path) == Path(
        "data/processed/MA000018/feedback/"
        "MA000018_overtime_interpretation_evaluator_feedback.md"
    )
    assert creator_response_path_for_interpretation(interpretation_path) == Path(
        "data/processed/MA000018/feedback/"
        "MA000018_overtime_interpretation_creator_response.md"
    )
    assert revised_output_path_for_interpretation(interpretation_path) == Path(
        "data/processed/MA000018/MA000018_overtime_interpretation_revised.md"
    )


def test_explicit_ruleset_paths_match_award_first_layout():
    classification_path = Path("data/processed/MA000018/MA000018_payment_classification.json")

    assert ruleset_clause_classification_output_path_for_classification(
        classification_path,
        OVERTIME_CONSEQUENCE_RULESET,
    ) == Path(
        "data/processed/MA000018/MA000018_overtime_clause_classification.json"
    )
    assert ruleset_output_path_for_classification(
        classification_path,
        OVERTIME_CONSEQUENCE_RULESET,
    ) == Path("data/processed/MA000018/MA000018_overtime_consequence_ruleset.md")


def test_resolve_clause_classification_path_uses_ruleset_when_interpretation_is_explicit_ruleset():
    classification_path = Path("data/processed/MA000018/MA000018_payment_classification.json")
    interpretation_path = Path("data/processed/MA000018/MA000018_overtime_consequence_ruleset.md")

    assert resolve_overtime_clause_classification_path(
        classification_path,
        None,
        interpretation_path,
    ) == Path("data/processed/MA000018/MA000018_overtime_clause_classification.json")


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
