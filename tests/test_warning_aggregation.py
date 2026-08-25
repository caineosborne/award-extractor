import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET
from streamlit_review import app
from streamlit_review.app import render_warning_register_screen
from streamlit_review.warning_aggregation import build_warning_register


def write_warning_artifact(path: Path, warnings: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"validation_warnings": warnings}),
        encoding="utf-8",
    )


def ruleset_artifacts(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        expert_a_markdown=tmp_path / "3_1_example_ruleset_expert_a.md",
        expert_b_markdown=tmp_path / "3_1_example_ruleset_expert_b.md",
        combined_json=tmp_path / "3_1_example_ruleset.json",
        revised_json=tmp_path / "3_2_example_revised_ruleset.json",
        formatted_markdown=tmp_path / "4_1_example_formatted_ruleset.md",
    )


def test_warning_register_collects_stage_warnings_in_pipeline_order(tmp_path: Path):
    artifacts = ruleset_artifacts(tmp_path)
    write_warning_artifact(
        artifacts.expert_a_markdown.with_suffix(".json"),
        ["Expert A warning."],
    )
    write_warning_artifact(artifacts.expert_b_markdown.with_suffix(".json"), [])
    write_warning_artifact(artifacts.combined_json, ["Combined warning."])
    write_warning_artifact(artifacts.revised_json, ["Revised warning."])
    write_warning_artifact(
        tmp_path / "4_1_example_formatted_ruleset_metadata.json",
        ["Formatted warning."],
    )

    register = build_warning_register(artifacts)

    assert [warning["warning"] for warning in register["warnings"]] == [
        "Expert A warning.",
        "Combined warning.",
        "Revised warning.",
        "Formatted warning.",
    ]
    assert [summary["stage_label"] for summary in register["stage_summaries"]] == [
        "3.1 Expert A",
        "3.1 Expert B",
        "3.1 Combined",
        "3.2 Revised",
        "4.1 Formatted",
    ]
    assert register["unique_warning_count"] == 4
    assert register["total_stage_occurrences"] == 4
    assert register["missing_artifacts"] == []


def test_warning_register_merges_exact_duplicates_and_keeps_stage_provenance(
    tmp_path: Path,
):
    artifacts = ruleset_artifacts(tmp_path)
    repeated_warning = "Clause 21.4 was not represented."
    write_warning_artifact(
        artifacts.expert_a_markdown.with_suffix(".json"),
        [repeated_warning],
    )
    write_warning_artifact(
        artifacts.expert_b_markdown.with_suffix(".json"),
        ["Clause 21.4  was not represented."],
    )
    write_warning_artifact(artifacts.combined_json, [])
    write_warning_artifact(artifacts.revised_json, [])
    write_warning_artifact(
        tmp_path / "4_1_example_formatted_ruleset_metadata.json",
        [],
    )

    register = build_warning_register(artifacts)

    assert register["unique_warning_count"] == 1
    assert register["total_stage_occurrences"] == 2
    assert register["warnings"] == [
        {
            "warning": repeated_warning,
            "stage_keys": ["3.1_expert_a", "3.1_expert_b"],
            "stage_labels": ["3.1 Expert A", "3.1 Expert B"],
        }
    ]


def test_warning_register_reports_missing_artifacts_separately(tmp_path: Path):
    artifacts = ruleset_artifacts(tmp_path)
    write_warning_artifact(artifacts.combined_json, [])

    register = build_warning_register(artifacts)

    assert register["warnings"] == []
    assert [artifact["stage_label"] for artifact in register["missing_artifacts"]] == [
        "3.1 Expert A",
        "3.1 Expert B",
        "3.2 Revised",
        "4.1 Formatted",
    ]
    combined_summary = register["stage_summaries"][2]
    assert combined_summary == {
        "stage_key": "3.1_combined",
        "stage_label": "3.1 Combined",
        "warning_count": 0,
        "artifact_available": True,
    }


def test_warning_register_screen_renders_clause_details(monkeypatch, tmp_path: Path):
    artifacts = ruleset_artifacts(tmp_path)
    artifacts.clause_classification = tmp_path / "2_2_example.json"
    warning_register = {
        "warnings": [
            {
                "warning": "Clause 21.4 was not represented.",
                "stage_keys": ["3.1_expert_a"],
                "stage_labels": ["3.1 Expert A"],
            }
        ],
        "unique_warning_count": 1,
        "total_stage_occurrences": 1,
        "stage_summaries": [
            {
                "stage_key": "3.1_expert_a",
                "stage_label": "3.1 Expert A",
                "warning_count": 1,
                "artifact_available": True,
            }
        ],
        "missing_artifacts": [],
    }
    rendered_clause_details: list[tuple[list[str], str]] = []

    monkeypatch.setattr(app, "award_code_for_artifact_paths", lambda _paths: "TEST")
    monkeypatch.setattr(
        app,
        "ruleset_artifact_paths_for_award",
        lambda _award_code, _ruleset_key: artifacts,
    )
    monkeypatch.setattr(app, "build_warning_register", lambda _artifacts: warning_register)
    monkeypatch.setattr(app, "load_clause_hover_index", lambda _path: {})
    monkeypatch.setattr(
        app,
        "render_clause_source_details",
        lambda references, _index, *, label_prefix: rendered_clause_details.append(
            (references, label_prefix)
        ),
    )
    monkeypatch.setattr(app.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        app.st,
        "columns",
        lambda *_args, **_kwargs: [SimpleNamespace(metric=lambda *_a, **_k: None)],
    )
    monkeypatch.setattr(app.st, "container", lambda *_args, **_kwargs: nullcontext())

    render_warning_register_screen(
        SimpleNamespace(),
        panel_key="warning_test",
        ruleset_key=OVERTIME_CREATION_RULESET,
    )

    assert rendered_clause_details == [(["21.4"], "Source clause")]
