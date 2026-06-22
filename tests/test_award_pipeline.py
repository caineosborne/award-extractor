from pathlib import Path
from unittest.mock import patch

from src.award_pipeline import (
    AwardPipelineError,
    build_paths,
    main,
    output_stem_for_award,
    parse_args,
    run_selected_step,
)
from src.common.active_pipeline_paths import PROJECT_ROOT


def test_parse_args_defaults_to_active_pipeline_through_3b():
    args = parse_args(["MA000018"])

    assert args.award_code == "MA000018"
    assert args.step is None
    assert args.suffix is None


def test_build_paths_covers_step_3b_artifacts():
    paths = build_paths(
        award_code="MA000018",
        suffix="draft",
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    assert paths.output_stem == output_stem_for_award("MA000018", "draft")
    assert paths.classification_path.name == "MA000018_draft_payment_classification.json"
    assert paths.overtime_clause_classification_path.name == (
        "MA000018_draft_overtime_clause_classification.json"
    )
    assert paths.evaluator_feedback_path.name == (
        "MA000018_draft_overtime_interpretation_evaluator_feedback.md"
    )
    assert paths.creator_response_path.name == (
        "MA000018_draft_overtime_interpretation_creator_response.md"
    )


def test_run_selected_step_rejects_unknown_step():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    try:
        run_selected_step(paths, "4a")
    except AwardPipelineError as exc:
        assert "Unknown step" in str(exc)
    else:
        raise AssertionError("Expected AwardPipelineError for unsupported step")


def test_main_runs_default_pipeline_through_step_3b():
    with patch("src.award_pipeline.run_default_pipeline") as run_default_pipeline:
        main(["MA000018"])

    run_default_pipeline.assert_called_once()
    passed_paths = run_default_pipeline.call_args.args[0]
    assert passed_paths.interpretation_path == PROJECT_ROOT / Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"
    )


def test_main_runs_selected_active_step():
    with patch("src.award_pipeline.run_selected_step") as run_selected_step_mock:
        main(["MA000018", "3b"])

    run_selected_step_mock.assert_called_once()
    passed_paths, passed_step = run_selected_step_mock.call_args.args
    assert passed_step == "3b"
    assert passed_paths.revised_interpretation_path == PROJECT_ROOT / Path(
        "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md"
    )
