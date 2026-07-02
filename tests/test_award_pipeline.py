from pathlib import Path
from unittest.mock import patch, sentinel

from src.award_pipeline import (
    AwardPipelineError,
    CLI_DEFAULT_RULESET_KEYS,
    DEFAULT_PIPELINE_STEPS,
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    build_paths,
    main,
    output_stem_for_award,
    parse_args,
    resolve_cli_ruleset_keys,
    run_default_pipeline,
    run_step_3_1,
    run_step_5_1,
    run_selected_step,
    run_step_2_1,
)
from src.common.active_pipeline_paths import PROJECT_ROOT


def test_parse_args_defaults_to_active_pipeline_through_5_1():
    args = parse_args(["MA000018"])

    assert args.award_code == "MA000018"
    assert args.step is None
    assert args.suffix is None
    assert args.subset is None
    assert DEFAULT_PIPELINE_STEPS == ("1", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1")


def test_parse_args_accepts_ruleset_subset_ids():
    args = parse_args(["MA000018", "3.1", "--subset", "2", "1", "2"])

    assert args.award_code == "MA000018"
    assert args.step == "3.1"
    assert args.subset == ["2", "1", "2"]


def test_parse_args_rejects_invalid_ruleset_subset_id():
    try:
        parse_args(["MA000018", "--subset", "3"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected argparse to reject an unsupported subset id")


def test_resolve_cli_ruleset_keys_defaults_to_all_rulesets():
    assert resolve_cli_ruleset_keys(None) == list(CLI_DEFAULT_RULESET_KEYS)


def test_resolve_cli_ruleset_keys_deduplicates_and_preserves_order():
    assert resolve_cli_ruleset_keys(["2", "1", "2"]) == [
        OVERTIME_CONSEQUENCE_RULESET,
        OVERTIME_CREATION_RULESET,
    ]


def test_build_paths_covers_step_5_1_artifacts():
    paths = build_paths(
        award_code="MA000018",
        suffix="draft",
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    assert paths.output_stem == output_stem_for_award("MA000018", "draft")
    assert paths.classification_path.name == "2_1_payment_classification.json"
    assert paths.overtime_clause_classification_path.name == (
        "2_2_OT_creation_clause_classification.json"
    )
    assert paths.evaluator_feedback_path.name == (
        "3_2_OT_creation_review.md"
    )
    assert paths.creator_response_path.name == (
        "3_2_OT_creation_creator_response.md"
    )
    assert paths.core_overtime_pseudocode_path.name == (
        "5_1_OT_creation_pseudocode.md"
    )
    assert paths.core_overtime_validation_json_path.name == (
        "5_1_OT_creation_pseudocode_validation.json"
    )
    assert paths.core_overtime_validation_markdown_path.name == (
        "5_1_OT_creation_pseudocode_validation.md"
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


def test_main_runs_default_pipeline_through_step_5_1():
    with patch("src.award_pipeline.run_default_pipeline") as run_default_pipeline:
        main(["MA000018"])

    run_default_pipeline.assert_called_once()
    passed_paths, passed_ruleset_keys = run_default_pipeline.call_args.args
    assert passed_paths.interpretation_path == PROJECT_ROOT / Path(
        "data/processed/MA000018/3_1_OT_creation_ruleset.md"
    )
    assert passed_ruleset_keys == [
        OVERTIME_CREATION_RULESET,
        OVERTIME_CONSEQUENCE_RULESET,
    ]


def test_main_runs_selected_active_step():
    with patch("src.award_pipeline.run_selected_step") as run_selected_step_mock:
        main(["MA000018", "2.2", "--subset", "2"])

    run_selected_step_mock.assert_called_once()
    passed_paths, passed_step, passed_ruleset_keys = run_selected_step_mock.call_args.args
    assert passed_step == "2.2"
    assert passed_ruleset_keys == [OVERTIME_CONSEQUENCE_RULESET]
    assert passed_paths.revised_interpretation_path == PROJECT_ROOT / Path(
        "data/processed/MA000018/3_2_OT_creation_revised_ruleset.md"
    )


def test_main_allows_ruleset_subset_for_shared_step_without_changing_shared_artifact_contract():
    with patch("src.award_pipeline.run_selected_step") as run_selected_step_mock:
        main(["MA000018", "2.2", "--subset", "1", "2"])

    passed_paths, passed_step, passed_ruleset_keys = run_selected_step_mock.call_args.args
    assert passed_step == "2.2"
    assert passed_ruleset_keys == [
        OVERTIME_CREATION_RULESET,
        OVERTIME_CONSEQUENCE_RULESET,
    ]
    assert passed_paths.overtime_clause_classification_path.name == (
        "2_2_OT_creation_clause_classification.json"
    )


def test_run_step_2_2_uses_step_2_1_output_and_writes_step_2_2_artifact():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_2_2_classify_overtime_clauses"
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
        with patch("src.award_pipeline.run_step_2_1_classify") as classify_payments_mock:
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


def test_run_step_3_1_uses_step_2_outputs_and_writes_step_3_1_artifact():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_3_1_generate_ruleset"
        ) as generate_ruleset_mock:
            run_step_3_1(paths)

    assert require_existing_mock.call_args_list == [
        ((paths.classification_path, "3.1", "2.1"),),
        ((paths.overtime_clause_classification_path, "3.1", "2.2"),),
    ]
    generate_ruleset_mock.assert_called_once_with(
        classification_path=paths.classification_path,
        output_path=paths.interpretation_path,
        classification_output_path=paths.overtime_clause_classification_path,
        expert_run_count=2,
        ruleset_key="overtime_creation",
    )


def test_run_step_3_1_supports_consequence_ruleset_artifact_paths():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_3_1_generate_ruleset"
        ) as generate_ruleset_mock:
            run_step_3_1(paths, OVERTIME_CONSEQUENCE_RULESET)

    assert require_existing_mock.call_args_list == [
        ((paths.classification_path, "3.1", "2.1"),),
        ((paths.overtime_clause_classification_path, "3.1", "2.2"),),
    ]
    generate_ruleset_mock.assert_called_once_with(
        classification_path=paths.classification_path,
        output_path=paths.revised_interpretation_path.with_name(
            "3_1_OT_consequence_ruleset.md"
        ),
        classification_output_path=paths.overtime_clause_classification_path,
        expert_run_count=2,
        ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
    )


def test_run_step_1_uses_step_1_folder_runners():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.run_step_1_1_fetch") as fetch_award_source_mock:
        with patch("src.award_pipeline.run_step_1_2_parse_award") as write_outputs_mock:
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


def test_run_step_5_1_uses_award_code_for_source_selection():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_5_1_generate_pseudocode"
        ) as generate_core_overtime_pseudocode_mock:
            run_step_5_1(paths)

    require_existing_mock.assert_called_once_with(
        paths.revised_interpretation_path,
        "5.1",
        "3.2",
    )
    generate_core_overtime_pseudocode_mock.assert_called_once_with(
        summary_path=paths.revised_interpretation_path,
        output_path=paths.core_overtime_pseudocode_path,
    )


def test_run_step_5_1_prefers_manual_ruleset_when_present(tmp_path):
    revised_path = tmp_path / "3_2_OT_creation_revised_ruleset.md"
    revised_path.write_text("# Revised", encoding="utf-8")
    manual_ruleset_path = tmp_path / "3_2_OT_creation_revised_ruleset_manual.md"
    manual_ruleset_path.write_text("# Manual ruleset", encoding="utf-8")

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
            "src.award_pipeline.run_step_5_1_generate_pseudocode"
        ) as generate_core_overtime_pseudocode_mock:
            run_step_5_1(paths)

    require_existing_mock.assert_called_once_with(
        revised_path,
        "5.1",
        "3.2",
    )
    generate_core_overtime_pseudocode_mock.assert_called_once_with(
        summary_path=manual_ruleset_path,
        output_path=paths.core_overtime_pseudocode_path,
    )


def test_run_default_pipeline_with_rulesets_runs_shared_steps_once_then_ruleset_steps():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )
    calls: list[tuple[str, str | None]] = []

    fake_step_runners = {
        "1": lambda current_paths: calls.append(("1", None)),
        "2.1": lambda current_paths: calls.append(("2.1", None)),
        "2.2": lambda current_paths: calls.append(("2.2", None)),
        "3.1": lambda current_paths, ruleset_key=None: calls.append(("3.1", ruleset_key)),
        "3.2": lambda current_paths, ruleset_key=None: calls.append(("3.2", ruleset_key)),
        "4.1": lambda current_paths, ruleset_key=None: calls.append(("4.1", ruleset_key)),
        "5.1": lambda current_paths, ruleset_key=None: calls.append(("5.1", ruleset_key)),
    }

    with patch.dict("src.award_pipeline.STEP_RUNNERS", fake_step_runners, clear=True):
        run_default_pipeline(
            paths,
            [
                OVERTIME_CREATION_RULESET,
                OVERTIME_CONSEQUENCE_RULESET,
            ],
        )

    assert calls == [
        ("1", None),
        ("2.1", None),
        ("2.2", None),
        ("3.1", OVERTIME_CREATION_RULESET),
        ("3.2", OVERTIME_CREATION_RULESET),
        ("4.1", OVERTIME_CREATION_RULESET),
        ("5.1", OVERTIME_CREATION_RULESET),
        ("3.1", OVERTIME_CONSEQUENCE_RULESET),
        ("3.2", OVERTIME_CONSEQUENCE_RULESET),
        ("4.1", OVERTIME_CONSEQUENCE_RULESET),
        ("5.1", OVERTIME_CONSEQUENCE_RULESET),
    ]


def test_run_selected_step_runs_ruleset_specific_step_for_selected_rulesets():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )
    calls: list[str] = []

    fake_step_runners = {
        "3.1": lambda current_paths, ruleset_key=None: calls.append(str(ruleset_key))
    }

    with patch.dict("src.award_pipeline.STEP_RUNNERS", fake_step_runners, clear=True):
        run_selected_step(
            paths,
            "3.1",
            [OVERTIME_CONSEQUENCE_RULESET, OVERTIME_CREATION_RULESET],
        )

    assert calls == [
        OVERTIME_CONSEQUENCE_RULESET,
        OVERTIME_CREATION_RULESET,
    ]


def test_run_selected_step_ignores_ruleset_list_for_shared_step():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )
    calls: list[tuple[object, ...]] = []

    fake_step_runners = {
        "2.2": lambda current_paths: calls.append((current_paths,))
    }

    with patch.dict("src.award_pipeline.STEP_RUNNERS", fake_step_runners, clear=True):
        run_selected_step(paths, "2.2", [OVERTIME_CONSEQUENCE_RULESET])

    assert calls == [(paths,)]


def test_run_step_3_1_with_explicit_ruleset_uses_ruleset_specific_paths():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_3_1_generate_ruleset"
        ) as generate_ruleset_mock:
            run_step_3_1(paths, OVERTIME_CONSEQUENCE_RULESET)

    assert require_existing_mock.call_args_list == [
        ((paths.classification_path, "3.1", "2.1"),),
        ((paths.overtime_clause_classification_path, "3.1", "2.2"),),
    ]
    generate_ruleset_mock.assert_called_once_with(
        classification_path=paths.classification_path,
        output_path=PROJECT_ROOT
        / Path(
            "data/processed/MA000018/3_1_OT_consequence_ruleset.md"
        ),
        classification_output_path=paths.overtime_clause_classification_path,
        expert_run_count=2,
        ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
    )


def test_run_step_5_1_with_explicit_ruleset_uses_ruleset_specific_outputs():
    paths = build_paths(
        award_code="MA000018",
        suffix=None,
        url="https://awards.fairwork.gov.au/MA000018.html",
    )

    with patch("src.award_pipeline.require_existing") as require_existing_mock:
        with patch(
            "src.award_pipeline.run_step_5_1_generate_pseudocode"
        ) as generate_core_overtime_pseudocode_mock:
            run_step_5_1(paths, OVERTIME_CONSEQUENCE_RULESET)

    require_existing_mock.assert_called_once_with(
        PROJECT_ROOT / Path("data/processed/MA000018/3_2_OT_consequence_revised_ruleset.md"),
        "5.1",
        "3.2",
    )
    generate_core_overtime_pseudocode_mock.assert_called_once_with(
        summary_path=PROJECT_ROOT / Path("data/processed/MA000018/3_2_OT_consequence_revised_ruleset.md"),
        output_path=PROJECT_ROOT / Path("data/processed/MA000018/5_1_OT_consequence_pseudocode.md"),
        ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
    )
