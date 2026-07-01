from src.common.output_naming import (
    DEFAULT_ACTIVE_PIPELINE_STEPS,
    FUTURE_PIPELINE_STEP_IDS,
    default_award_url_for_code,
    normalize_output_suffix,
)
from src.common.pipeline_context import build_active_pipeline_context


def test_build_active_pipeline_context_covers_current_artifacts():
    context = build_active_pipeline_context(
        award_code="MA000018",
        suffix="draft",
        url=default_award_url_for_code("MA000018"),
    )

    assert context.output_stem == "MA000018_draft"
    assert context.raw_html_path.name == "MA000018_draft.html"
    assert context.award_json_path.name == "MA000018_draft.json"
    assert context.classification_path.name == "MA000018_draft_payment_classification.json"
    assert (
        context.overtime_clause_classification_path.name
        == "MA000018_draft_overtime_clause_classification.json"
    )
    assert context.interpretation_path.name == "MA000018_draft_overtime_interpretation.md"
    assert (
        context.core_overtime_pseudocode_path.name
        == "MA000018_draft_core_overtime_pseudocode.md"
    )


def test_normalize_output_suffix_matches_pipeline_expectations():
    assert normalize_output_suffix(None) is None
    assert normalize_output_suffix(" draft copy ") == "draft_copy"

    try:
        normalize_output_suffix("...")
    except ValueError as exc:
        assert "at least one letter or digit" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid suffix")


def test_step_constants_cover_current_and_future_pipeline_shapes():
    assert DEFAULT_ACTIVE_PIPELINE_STEPS == ("1", "2.1", "2.2", "3", "3b")
    assert FUTURE_PIPELINE_STEP_IDS == ("1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1")
