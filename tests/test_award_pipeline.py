from pathlib import Path
from unittest.mock import patch, sentinel

from src.award_pipeline import (
    AwardPipelineError,
    DEFAULT_PIPELINE_STEPS,
    build_paths,
    main,
    output_stem_for_award,
    parse_args,
    run_step_5b,
    run_selected_step,
    run_step_2_1,
)
from src.common.active_pipeline_paths import PROJECT_ROOT


def test_parse_args_defaults_to_active_pipeline_through_3b():
    args = parse_args(["MA000018"])

    assert args.award_code == "MA000018"
    assert args.step is None
    assert args.suffix is None
    assert DEFAULT_PIPELINE_STEPS == ("1", "2.1", "2.2", "3", "3b")


def test_build_paths_covers_step_5b_artifacts():
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
    assert paths.core_overtime_pseudocode_path.name == (
        "MA000018_draft_core_overtime_pseudocode.md"
    )
    assert paths.core_overtime_validation_json_path.name == (
        "MA000018_draft_core_overtime_pseudocode_validation.json"
    )
    assert paths.core_overtime_validation_markdown_path.name == (
        "MA000018_draft_core_overtime_pseudocode_validation.md"
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
        "data/processed/MA000018/MA000018_overtime_interpretation.md"
    )


def test_main_runs_selected_active_step():
    with patch("src.award_pipeline.run_selected_step") as run_selected_step_mock:
        main(["MA000018", "2.2"])

    run_selected_step_mock.assert_called_once()
    passed_paths, passed_step = run_selected_step_mock.call_args.args
    assert passed_step == "2.2"
    assert passed_paths.revised_interpretation_path == PROJECT_ROOT / Path(
        "data/processed/MA000018/MA000018_overtime_interpretation_revised.md"
    )


def test_run_step_2_2_uses_step_2_1_output_and_writes_step_2_2_artifact():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_overtime_clause_classification_step"
        ) as run_step_mock:
            from src.award_pipeline import run_step_2_2

            run_step_2_2(paths)

    require_existing_mock.assert_called_once_with(
        paths.classification_path,
        "2.2",
        "2.1",
    )
    run_step_mock.assert_called_once_with(
        classification_path=paths.classification_path,
        output_path=paths.overtime_clause_classification_path,
    )


def test_run_step_2_1_uses_step_1_output_and_writes_step_2_1_artifact():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch("src.award_pipeline.classify_payments") as classify_payments_mock:
            from src.award_pipeline import run_step_2_1

            run_step_2_1(paths)

    require_existing_mock.assert_called_once_with(
        paths.award_json_path,
        "2.1",
        "1",
    )
    classify_payments_mock.assert_called_once_with(
        award_path=paths.award_json_path,
        output_path=paths.classification_path,
    )


def test_run_step_1_uses_step_1_folder_runners():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.fetch_award_source") as fetch_award_source_mock:
        with patch("src.award_pipeline.write_html_outputs_for_paths") as write_outputs_mock:
            fetch_award_source_mock.return_value = type(
                "FetchResult",
                (),
                {"main_content": sentinel.main_content, "award": sentinel.award},
            )()
            from src.award_pipeline import run_step_1

            run_step_1(paths)

    fetch_award_source_mock.assert_called_once_with(paths.url)
    write_outputs_mock.assert_called_once_with(
        main_content=sentinel.main_content,
        award=sentinel.award,
        raw_html_path=paths.raw_html_path,
        award_json_path=paths.award_json_path,
    )


def test_run_step_5b_uses_award_code_for_source_selection():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.generate_core_overtime_pseudocode"
        ) as generate_core_overtime_pseudocode_mock:
            run_step_5b(paths)

    require_existing_mock.assert_called_once_with(
        paths.revised_interpretation_path,
        "5b",
        "3b",
    )
    generate_core_overtime_pseudocode_mock.assert_called_once_with(
        summary_path=paths.revised_interpretation_path,
        output_path=paths.core_overtime_pseudocode_path,
    )


def test_run_step_5b_prefers_manual_4b_when_present(tmp_path):
    revised_path = tmp_path / "MA000018_overtime_interpretation_revised.md"
    revised_path.write_text("# Revised", encoding="utf-8")
    manual_4b_path = tmp_path / "MA000018_overtime_interpretation_4b.md"
    manual_4b_path.write_text("# Manual 4B", encoding="utf-8")

    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )
    paths = paths.__class__(
        **{
            **paths.__dict__,
            "revised_interpretation_path": revised_path,
        }
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.generate_core_overtime_pseudocode"
        ) as generate_core_overtime_pseudocode_mock:
            run_step_5b(paths)

    require_existing_mock.assert_called_once_with(
        revised_path,
        "5b",
        "3b",
    )
    generate_core_overtime_pseudocode_mock.assert_called_once_with(
        summary_path=manual_4b_path,
        output_path=paths.core_overtime_pseudocode_path,
    )
