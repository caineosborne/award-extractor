import json
import inspect
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import sentinel

import pytest

from src.prompts.step_2_2_classify_overtime_clauses import (
    build_clause_classification_messages as build_ruleset_clause_classification_messages,
)
from src.prompts.step_3_1_generate_ruleset import (
    build_expert_comparison_messages as build_ruleset_expert_comparison_messages,
    build_interpretation_messages as build_ruleset_interpretation_messages,
)
from src.prompts.step_3_2_review_ruleset import (
    build_review_creator_messages,
    build_review_evaluator_messages,
)
from streamlit_review.app import (
    PIPELINE_STEP_LABELS as APP_PIPELINE_STEP_LABELS,
    award_code_for_artifact_paths,
    available_award_code_index,
    candidate_clause_keys,
    clause_hover_text,
    build_review_decision_rows,
    combine_pipeline_logs,
    json_expander_widget_key,
    manual_ruleset_editor_widget_key,
    move_selected_index,
    overtime_clause_text_widget_key,
    pipeline_run_label,
    recommendation_not_implemented,
    render_pipeline_run_controls,
    render_creator_commentary_panel,
    render_evaluator_feedback_panel,
    review_decision_concerns,
    run_pipeline_for_award,
    summarize_review_decision_rows,
    validate_award_code_input,
)
from streamlit_review.pipeline_runs import (
    PIPELINE_STEP_LABELS as BACKGROUND_PIPELINE_STEP_LABELS,
    pipeline_run_label as background_pipeline_run_label,
    run_pipeline_for_award as background_run_pipeline_for_award,
)
from streamlit_review.output_data import (
    ArtifactPaths,
    RulesetArtifactPaths,
    artifact_paths_for_award,
    clamp_index,
    delete_processed_files_matching_prefix,
    discover_award_codes,
    format_last_modified_for_display,
    l1_clause_keys,
    l1_record,
    l2_clause_keys,
    l2_record,
    next_index,
    overtime_classification_keys,
    overtime_classification_record,
    previous_index,
    processed_files_matching_prefix,
    read_text_file,
    ruleset_artifact_paths_for_award,
    source_path_for_core_overtime_pseudocode,
    source_path_for_manual_ruleset_editor,
    source_path_for_ruleset_core_overtime_pseudocode,
    source_path_for_ruleset_manual_ruleset_editor,
    write_text_file,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)
from src.common.overtime_rules import OvertimeRule
from src.step_2_2_classify_overtime_clauses.core import OvertimeClauseClassification
from src.common.active_pipeline_paths import (
    ruleset_clause_classification_output_path_for_classification,
    ruleset_output_path_for_classification,
)
from src.step_3_1_generate_ruleset.run import generate_ruleset_from_clause_classification
from src.common.award_sources import (
    SOURCE_TYPE_LOCAL_PDF,
    can_run_pipeline_for_award,
    register_local_pdf_source,
    source_record_for_award,
)


def test_discover_award_codes_from_payment_classification_files(tmp_path):
    (tmp_path / "MA000018").mkdir()
    (tmp_path / "MA000018" / "2_1_payment_classification.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (tmp_path / "MA000002").mkdir()
    (tmp_path / "MA000002" / "2_1_payment_classification.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "MA000120_payment_classification.json").write_text(
        "{}",
        encoding="utf-8",
    )

    assert discover_award_codes(tmp_path) == ["MA000002", "MA000018"]


def test_artifact_paths_for_award():
    paths = artifact_paths_for_award("MA000018")

    assert paths.payment_classification.name == "2_1_payment_classification.json"
    assert paths.overtime_clause_classification.name == "2_2_OT_creation_clause_classification.json"
    assert paths.original_overtime_interpretation.name == "3_1_OT_creation_ruleset.md"
    assert (
        paths.original_overtime_interpretation_expert_a.name
        == "3_1_OT_creation_ruleset_expert_a.md"
    )
    assert (
        paths.original_overtime_interpretation_expert_b.name
        == "3_1_OT_creation_ruleset_expert_b.md"
    )
    assert (
        paths.original_overtime_interpretation_comparison.name
        == "3_1_OT_creation_ruleset_comparison.json"
    )
    assert paths.evaluator_feedback.name == "3_2_OT_creation_review.md"
    assert paths.creator_response.name == "3_2_OT_creation_creator_response.md"
    assert paths.revised_overtime_interpretation.name == "3_2_OT_creation_revised_ruleset.md"
    assert paths.overtime_entitlements.name == "4_1_OT_creation_formatted_ruleset.md"
    assert (
        paths.manual_ruleset_path.name
        == "3_2_OT_creation_revised_ruleset_manual.md"
    )
    assert paths.core_overtime_pseudocode.name == "5_1_OT_creation_pseudocode.md"
    assert paths.core_overtime_validation_json.name == "5_1_OT_creation_pseudocode_validation.json"
    assert (
        paths.core_overtime_validation_markdown.name
        == "5_1_OT_creation_pseudocode_validation.md"
    )


def test_award_code_for_artifact_paths_uses_payment_classification_stem():
    paths = artifact_paths_for_award("MA000018")

    assert award_code_for_artifact_paths(paths) == "MA000018"


def test_ruleset_artifact_paths_for_award():
    paths = ruleset_artifact_paths_for_award("MA000018", OVERTIME_CONSEQUENCE_RULESET)

    assert paths.clause_classification.name == "2_2_OT_creation_clause_classification.json"
    assert paths.expert_a_markdown.name == "3_1_OT_consequence_ruleset_expert_a.md"
    assert paths.expert_b_markdown.name == "3_1_OT_consequence_ruleset_expert_b.md"
    assert paths.comparison_json.name == "3_1_OT_consequence_ruleset_comparison.json"
    assert paths.combined_markdown.name == "3_1_OT_consequence_ruleset.md"
    assert paths.combined_json.name == "3_1_OT_consequence_ruleset.json"
    assert paths.evaluator_feedback.name == "3_2_OT_consequence_review.md"
    assert paths.creator_response.name == "3_2_OT_consequence_creator_response.md"
    assert paths.revised_markdown.name == "3_2_OT_consequence_revised_ruleset.md"
    assert paths.formatted_markdown.name == "4_1_OT_consequence_formatted_ruleset.md"
    assert paths.manual_ruleset_markdown.name == "3_2_OT_consequence_revised_ruleset_manual.md"
    assert paths.pseudocode_markdown.name == "5_1_OT_consequence_pseudocode.md"


def test_creation_ruleset_artifact_paths_for_award_are_canonical():
    paths = ruleset_artifact_paths_for_award("MA000120", OVERTIME_CREATION_RULESET)

    assert paths.clause_classification.name == "2_2_OT_creation_clause_classification.json"
    assert paths.expert_a_markdown.name == "3_1_OT_creation_ruleset_expert_a.md"
    assert paths.expert_b_markdown.name == "3_1_OT_creation_ruleset_expert_b.md"
    assert paths.comparison_json.name == "3_1_OT_creation_ruleset_comparison.json"
    assert paths.combined_markdown.name == "3_1_OT_creation_ruleset.md"
    assert paths.combined_json.name == "3_1_OT_creation_ruleset.json"
    assert paths.evaluator_feedback.name == "3_2_OT_creation_review.md"
    assert paths.creator_response.name == "3_2_OT_creation_creator_response.md"
    assert paths.revised_markdown.name == "3_2_OT_creation_revised_ruleset.md"
    assert paths.formatted_markdown.name == "4_1_OT_creation_formatted_ruleset.md"
    assert paths.manual_ruleset_markdown.name == "3_2_OT_creation_revised_ruleset_manual.md"
    assert paths.pseudocode_markdown.name == "5_1_OT_creation_pseudocode.md"


def test_phase_1_prompt_builders_live_under_prompts_folder():
    prompt_builders = [
        build_ruleset_clause_classification_messages,
        build_ruleset_interpretation_messages,
        build_ruleset_expert_comparison_messages,
        build_review_evaluator_messages,
        build_review_creator_messages,
    ]

    for prompt_builder in prompt_builders:
        prompt_source = inspect.getsourcefile(prompt_builder)
        assert prompt_source is not None
        assert "/src/prompts/" in prompt_source


def test_step_3_1_prompt_distinguishes_clauses_from_operational_rules():
    messages = build_ruleset_interpretation_messages(
        OVERTIME_CREATION_RULESET,
        "classification.json",
        [
            OvertimeClauseClassification(
                clause_number="21.3",
                classification="Ordinary Hours Boundary",
                classifications=["Ordinary Hours Boundary"],
                clause_text=(
                    "21.3: Ordinary hours may be worked between 6.00 am and 6.30 pm. "
                    "Where broken shifts are worked the spread of hours can be no greater "
                    "than 12 hours per day."
                ),
                explanation="Contains ordinary-hours span and broken-shift spread limits.",
                employee_cohort="all",
                work_arrangement="all",
                other_scope_notes="",
            )
        ],
    )

    user_prompt = messages[1]["content"]

    assert "A clause and a ruleset item are not the same thing." in user_prompt
    assert "A single clause may contain multiple distinct operational overtime rules." in user_prompt
    assert "A single operational overtime rule may rely on multiple clauses" in user_prompt
    assert "Treat each returned rule as one operational overtime rule in the ruleset." in user_prompt


def test_step_3_1_merge_prompt_is_reconciliation_led():
    clause = OvertimeClauseClassification(
        clause_number="22.2",
        classification="Ordinary Hours Boundary",
        classifications=("Ordinary Hours Boundary",),
        clause_text=(
            "22.2(a): The ordinary hours of work for a day worker will be worked between "
            "6.00 am and 6.00 pm Monday to Friday. 22.2(b): A shiftworker is an employee "
            "who is regularly rostered to work ordinary hours outside clause 22.2(a)."
        ),
        explanation="Contains a day-worker span and linked shiftworker definition.",
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="",
    )
    run_a_rule = OvertimeRule(
        rule_id="day-worker-span",
        section_heading="General ordinary hours boundary",
        employee_scope=("full-time", "part-time", "casual"),
        employee_cohort="all",
        work_arrangement="day-worker",
        other_scope_notes="",
        clause_references=("22.2(a)",),
        rule_markdown="- Day-worker ordinary hours are between 6.00 am and 6.00 pm Monday to Friday. [22.2(a)]",
        rule_plain_text="Day-worker ordinary hours are between 6.00 am and 6.00 pm Monday to Friday.",
        source_clause_numbers=("22.2(a)",),
        source_classifications=("Ordinary Hours Boundary",),
    )
    run_b_rule = OvertimeRule(
        rule_id="shiftworker-definition",
        section_heading="Shiftworkers",
        employee_scope=("full-time", "part-time", "casual"),
        employee_cohort="all",
        work_arrangement="shiftworker",
        other_scope_notes="",
        clause_references=("22.2(b)",),
        rule_markdown="- A shiftworker is regularly rostered to work ordinary hours outside the day-worker span. [22.2(b)]",
        rule_plain_text="A shiftworker is regularly rostered to work ordinary hours outside the day-worker span.",
        source_clause_numbers=("22.2(b)",),
        source_classifications=("Ordinary Hours Boundary",),
    )

    messages = build_ruleset_expert_comparison_messages(
        ruleset_key=OVERTIME_CREATION_RULESET,
        source_path=Path("classification.json"),
        overtime_creation_clauses=[clause],
        run_a_rules=[run_a_rule],
        run_b_rules=[run_b_rule],
    )

    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "Your role is to reconcile Expert A and Expert B, not to perform a fresh extraction." in system_prompt
    assert "Err on the side of inclusion where clause coverage is uncertain." in system_prompt
    assert "prefer preserving distinct operational rules over collapsing them" in system_prompt
    assert "If neither expert fully captures a shortlisted clause, prefer a conservative merged rule grounded in the clause text rather than omitting the clause." in system_prompt
    assert "Use merge_explanations to explain every dropped expert rule" in user_prompt
    assert "If one expert captured a shortlisted clause and the other did not, say which expert supplied the surviving coverage." in user_prompt


def test_step_3_1_final_warnings_use_merged_comparison_only(monkeypatch, tmp_path):
    captured_validation_warnings = {}
    source_path = tmp_path / "classification.json"
    clause_classification_path = tmp_path / "2_2.json"
    destination = tmp_path / "3_1.md"
    json_destination = tmp_path / "3_1.json"
    clause = OvertimeClauseClassification(
        clause_number="22.2",
        classification="Ordinary Hours Boundary",
        classifications=("Ordinary Hours Boundary",),
        clause_text="22.2 clause text",
        explanation="22.2 explanation",
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="",
    )
    expert_rule = OvertimeRule(
        rule_id="expert-rule",
        section_heading="General ordinary hours boundary",
        employee_scope=("full-time", "part-time", "casual"),
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="",
        clause_references=("22.2",),
        rule_markdown="- Expert rule. [22.2]",
        rule_plain_text="Expert rule.",
        source_clause_numbers=("22.2",),
        source_classifications=("Ordinary Hours Boundary",),
    )

    def fake_resolve_generation_inputs(**_kwargs):
        return SimpleNamespace(
            source_path=source_path,
            clause_classification_path=clause_classification_path,
            destination=destination,
            json_destination=json_destination,
            overtime_creation_clauses=[clause],
            ruleset_key=OVERTIME_CREATION_RULESET,
        )

    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.resolve_generation_inputs",
        fake_resolve_generation_inputs,
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.selected_models",
        lambda **_kwargs: ("draft-model", "merge-model"),
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.load_openai_client",
        lambda: sentinel.client,
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.draft_expert_a",
        lambda **_kwargs: ([expert_rule], ["expert a warning"]),
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.draft_expert_b",
        lambda **_kwargs: ([expert_rule], ["expert b warning"]),
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.write_expert_draft",
        lambda **_kwargs: {"label": "expert", "json_path": "a.json", "markdown_path": "a.md"},
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.merge_expert_drafts",
        lambda **_kwargs: (
            [expert_rule],
            {"comparison_summary_markdown": "", "merge_explanations": []},
            ["merged warning"],
        ),
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.write_merged_comparison",
        lambda **_kwargs: None,
    )

    def fake_write_merged_ruleset(**kwargs):
        captured_validation_warnings["value"] = kwargs["validation_warnings"]
        return "rendered markdown"

    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.run.write_merged_ruleset",
        fake_write_merged_ruleset,
    )

    result = generate_ruleset_from_clause_classification(
        classification_path=source_path,
        ruleset_key=OVERTIME_CREATION_RULESET,
        expert_run_count=2,
        client=sentinel.client,
    )

    assert result == "rendered markdown"
    assert captured_validation_warnings["value"] == ["merged warning"]


def test_candidate_clause_keys_include_parent_variants():
    assert candidate_clause_keys("22.2(a)") == ["22.2(a)", "22.2", "22"]
    assert candidate_clause_keys("23.1(b)(ii)") == [
        "23.1(b)(ii)",
        "23.1",
        "23",
    ]


def test_clause_hover_text_falls_back_to_parent_clause():
    clause_index = {
        "22.2": {
            "clause_number": "22.2",
            "classification": "Ordinary Hours Boundary",
            "explanation": "Contains day-worker span and shiftworker linkage.",
            "clause_text": "22.2(a) day worker span. 22.2(b) shiftworker definition.",
        }
    }

    hover_text = clause_hover_text("22.2(a)", clause_index)

    assert hover_text is not None
    assert "Clause 22.2" in hover_text
    assert "Ordinary Hours Boundary" in hover_text
    assert "22.2(a) day worker span." in hover_text


def test_l1_payment_records_preserve_json_key_order():
    payment_classification = {
        "top_level_clauses": {
            "1": {
                "title": "Title",
                "payment_relevant": False,
                "definition_relevant": False,
                "requires_l2_classification": False,
                "reason": "Heading only.",
            },
            "2": {
                "title": "Commencement",
                "payment_relevant": True,
                "definition_relevant": False,
                "requires_l2_classification": True,
                "reason": "Affects payments.",
            },
        }
    }

    assert l1_clause_keys(payment_classification) == ["1", "2"]
    assert l1_record(payment_classification, "2")["title"] == "Commencement"


def test_l2_payment_records_preserve_json_key_order():
    payment_classification = {
        "classified_clauses": {
            "10.2": {
                "tags": ["Definition"],
                "reason": "Defines full-time employee.",
            },
            "22.1": {
                "tags": ["Ordinary Hours & Overtime"],
                "reason": "Defines ordinary hours.",
            },
        }
    }

    assert l2_clause_keys(payment_classification) == ["10.2", "22.1"]
    assert l2_record(payment_classification, "22.1")["tags"] == [
        "Ordinary Hours & Overtime"
    ]


def test_overtime_classification_records_use_clause_numbers():
    overtime_classification = {
        "clauses": [
            {
                "clause_number": "22.1",
                "classification": "Ordinary Hours Boundary",
                "explanation": "Defines ordinary hours.",
            },
            {
                "clause_number": "25.1",
                "classification": "Overtime Consequence",
                "explanation": "Defines overtime rates.",
            },
        ]
    }

    assert overtime_classification_keys(overtime_classification) == ["22.1", "25.1"]
    assert (
        overtime_classification_record(overtime_classification, "25.1")["classification"]
        == "Overtime Consequence"
    )


def test_overtime_clause_text_widget_key_changes_with_selected_clause():
    first_key = overtime_clause_text_widget_key("screen_one", "22.1")
    second_key = overtime_clause_text_widget_key("screen_one", "25.1")

    assert first_key != second_key
    assert first_key == "screen_one_overtime_clause_text_22.1"


def test_json_expander_widget_key_changes_with_panel_suffix():
    rendered_json = '{"rule_id": "R1"}'

    first_key = json_expander_widget_key(
        label="Structured overtime rules JSON",
        rendered_json=rendered_json,
        key_suffix="screen_one_/tmp/example.json",
    )
    second_key = json_expander_widget_key(
        label="Structured overtime rules JSON",
        rendered_json=rendered_json,
        key_suffix="screen_two_/tmp/example.json",
    )

    assert first_key != second_key
    assert first_key.startswith("Structured overtime rules JSON_screen_one_")


def test_manual_ruleset_editor_widget_key_uses_output_path_stem():
    output_path = Path("data/processed/MA000018/3_2_OT_creation_revised_ruleset_manual.md")

    assert (
        manual_ruleset_editor_widget_key("screen_one", output_path)
        == "screen_one_manual_ruleset_editor_3_2_OT_creation_revised_ruleset_manual"
    )


def test_manual_ruleset_editor_prefers_existing_saved_update_then_revised_source(tmp_path):
    original_path = tmp_path / "3_1_OT_creation_ruleset.md"
    revised_path = tmp_path / "3_2_OT_creation_revised_ruleset.md"
    overtime_entitlements_path = tmp_path / "4_1_OT_creation_formatted_ruleset.md"
    manual_ruleset_path = tmp_path / "3_2_OT_creation_revised_ruleset_manual.md"

    artifact_paths = ArtifactPaths(
        payment_classification=tmp_path / "2_1_payment_classification.json",
        overtime_clause_classification=tmp_path / "2_2_OT_creation_clause_classification.json",
        original_overtime_interpretation=original_path,
        original_overtime_interpretation_expert_a=tmp_path / "3_1_OT_creation_ruleset_expert_a.md",
        original_overtime_interpretation_expert_b=tmp_path / "3_1_OT_creation_ruleset_expert_b.md",
        original_overtime_interpretation_comparison=tmp_path / "3_1_OT_creation_ruleset_comparison.json",
        evaluator_feedback=tmp_path / "feedback" / "3_2_OT_creation_review.md",
        creator_response=tmp_path / "feedback" / "3_2_OT_creation_creator_response.md",
        revised_overtime_interpretation=revised_path,
        overtime_entitlements=overtime_entitlements_path,
        manual_ruleset_path=manual_ruleset_path,
        core_overtime_pseudocode=tmp_path / "5_1_OT_creation_pseudocode.md",
        core_overtime_validation_json=tmp_path / "5_1_OT_creation_pseudocode_validation.json",
        core_overtime_validation_markdown=tmp_path / "5_1_OT_creation_pseudocode_validation.md",
    )

    assert source_path_for_manual_ruleset_editor(artifact_paths) == original_path

    revised_path.write_text("# Revised 3.2", encoding="utf-8")
    assert source_path_for_manual_ruleset_editor(artifact_paths) == revised_path

    overtime_entitlements_path.write_text("# 4A", encoding="utf-8")
    assert source_path_for_manual_ruleset_editor(artifact_paths) == overtime_entitlements_path

    manual_ruleset_path.write_text("# Saved manual ruleset", encoding="utf-8")
    assert source_path_for_manual_ruleset_editor(artifact_paths) == manual_ruleset_path


def test_core_overtime_pseudocode_prefers_existing_manual_ruleset_then_4_1_then_revised_source(tmp_path):
    original_path = tmp_path / "3_1_OT_creation_ruleset.md"
    revised_path = tmp_path / "3_2_OT_creation_revised_ruleset.md"
    overtime_entitlements_path = tmp_path / "4_1_OT_creation_formatted_ruleset.md"
    manual_ruleset_path = tmp_path / "3_2_OT_creation_revised_ruleset_manual.md"

    artifact_paths = ArtifactPaths(
        payment_classification=tmp_path / "2_1_payment_classification.json",
        overtime_clause_classification=tmp_path / "2_2_OT_creation_clause_classification.json",
        original_overtime_interpretation=original_path,
        original_overtime_interpretation_expert_a=tmp_path / "3_1_OT_creation_ruleset_expert_a.md",
        original_overtime_interpretation_expert_b=tmp_path / "3_1_OT_creation_ruleset_expert_b.md",
        original_overtime_interpretation_comparison=tmp_path / "3_1_OT_creation_ruleset_comparison.json",
        evaluator_feedback=tmp_path / "feedback" / "3_2_OT_creation_review.md",
        creator_response=tmp_path / "feedback" / "3_2_OT_creation_creator_response.md",
        revised_overtime_interpretation=revised_path,
        overtime_entitlements=overtime_entitlements_path,
        manual_ruleset_path=manual_ruleset_path,
        core_overtime_pseudocode=tmp_path / "5_1_OT_creation_pseudocode.md",
        core_overtime_validation_json=tmp_path / "5_1_OT_creation_pseudocode_validation.json",
        core_overtime_validation_markdown=tmp_path / "5_1_OT_creation_pseudocode_validation.md",
    )

    assert source_path_for_core_overtime_pseudocode(artifact_paths) == original_path

    overtime_entitlements_path.write_text("# 4A", encoding="utf-8")
    assert source_path_for_core_overtime_pseudocode(artifact_paths) == overtime_entitlements_path

    revised_path.write_text("# Revised 3.2", encoding="utf-8")
    assert source_path_for_core_overtime_pseudocode(artifact_paths) == overtime_entitlements_path

    manual_ruleset_path.write_text("# Saved manual ruleset", encoding="utf-8")
    assert source_path_for_core_overtime_pseudocode(artifact_paths) == manual_ruleset_path


def test_ruleset_manual_ruleset_editor_prefers_existing_saved_update_then_revised_source(tmp_path):
    combined_path = tmp_path / "3_1_OT_creation_ruleset.md"
    revised_path = tmp_path / "3_2_OT_creation_revised_ruleset.md"
    formatted_path = tmp_path / "4_1_OT_creation_formatted_ruleset.md"
    manual_ruleset_path = tmp_path / "3_2_OT_creation_revised_ruleset_manual.md"

    ruleset_artifact_paths = RulesetArtifactPaths(
        ruleset_key=OVERTIME_CREATION_RULESET,
        clause_classification=tmp_path / "2_2_OT_creation_clause_classification.json",
        expert_a_markdown=tmp_path / "3_1_OT_creation_ruleset_expert_a.md",
        expert_b_markdown=tmp_path / "3_1_OT_creation_ruleset_expert_b.md",
        comparison_json=tmp_path / "3_1_OT_creation_ruleset_comparison.json",
        combined_markdown=combined_path,
        combined_json=tmp_path / "3_1_OT_creation_ruleset.json",
        evaluator_feedback=tmp_path / "feedback" / "3_2_OT_creation_review.md",
        evaluator_feedback_json=tmp_path / "feedback" / "3_2_OT_creation_review.json",
        creator_response=tmp_path / "feedback" / "3_2_OT_creation_creator_response.md",
        creator_response_json=tmp_path / "feedback" / "3_2_OT_creation_creator_response.json",
        revised_markdown=revised_path,
        revised_json=tmp_path / "3_2_OT_creation_revised_ruleset.json",
        formatted_markdown=formatted_path,
        manual_ruleset_markdown=manual_ruleset_path,
        pseudocode_markdown=tmp_path / "5_1_OT_creation_pseudocode.md",
        pseudocode_validation_json=tmp_path / "5_1_OT_creation_pseudocode_validation.json",
        pseudocode_validation_markdown=tmp_path / "5_1_OT_creation_pseudocode_validation.md",
    )

    assert source_path_for_ruleset_manual_ruleset_editor(ruleset_artifact_paths) == combined_path

    revised_path.write_text("# Revised 3B", encoding="utf-8")
    assert source_path_for_ruleset_manual_ruleset_editor(ruleset_artifact_paths) == revised_path

    formatted_path.write_text("# 4A", encoding="utf-8")
    assert source_path_for_ruleset_manual_ruleset_editor(ruleset_artifact_paths) == formatted_path

    manual_ruleset_path.write_text("# Saved manual ruleset", encoding="utf-8")
    assert source_path_for_ruleset_manual_ruleset_editor(ruleset_artifact_paths) == manual_ruleset_path


def test_ruleset_core_overtime_pseudocode_prefers_ruleset_manual_ruleset_then_4_1_then_revised_source(
    tmp_path,
):
    combined_path = tmp_path / "3_1_OT_creation_ruleset.md"
    revised_path = tmp_path / "3_2_OT_creation_revised_ruleset.md"
    formatted_path = tmp_path / "4_1_OT_creation_formatted_ruleset.md"
    manual_ruleset_path = tmp_path / "3_2_OT_creation_revised_ruleset_manual.md"

    ruleset_artifact_paths = RulesetArtifactPaths(
        ruleset_key=OVERTIME_CREATION_RULESET,
        clause_classification=tmp_path / "2_2_OT_creation_clause_classification.json",
        expert_a_markdown=tmp_path / "3_1_OT_creation_ruleset_expert_a.md",
        expert_b_markdown=tmp_path / "3_1_OT_creation_ruleset_expert_b.md",
        comparison_json=tmp_path / "3_1_OT_creation_ruleset_comparison.json",
        combined_markdown=combined_path,
        combined_json=tmp_path / "3_1_OT_creation_ruleset.json",
        evaluator_feedback=tmp_path / "feedback" / "3_2_OT_creation_review.md",
        evaluator_feedback_json=tmp_path / "feedback" / "3_2_OT_creation_review.json",
        creator_response=tmp_path / "feedback" / "3_2_OT_creation_creator_response.md",
        creator_response_json=tmp_path / "feedback" / "3_2_OT_creation_creator_response.json",
        revised_markdown=revised_path,
        revised_json=tmp_path / "3_2_OT_creation_revised_ruleset.json",
        formatted_markdown=formatted_path,
        manual_ruleset_markdown=manual_ruleset_path,
        pseudocode_markdown=tmp_path / "5_1_OT_creation_pseudocode.md",
        pseudocode_validation_json=tmp_path / "5_1_OT_creation_pseudocode_validation.json",
        pseudocode_validation_markdown=tmp_path / "5_1_OT_creation_pseudocode_validation.md",
    )

    assert source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifact_paths) == combined_path

    revised_path.write_text("# Revised 3.2", encoding="utf-8")
    assert source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifact_paths) == revised_path

    formatted_path.write_text("# 4A", encoding="utf-8")
    assert (
        source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifact_paths)
        == formatted_path
    )

    manual_ruleset_path.write_text("# Saved manual ruleset", encoding="utf-8")
    assert (
        source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifact_paths)
        == manual_ruleset_path
    )


def test_missing_text_file_returns_status_without_exception(tmp_path):
    missing_path = tmp_path / "missing.md"

    file_content = read_text_file(missing_path)

    assert file_content.path == missing_path
    assert file_content.exists is False
    assert file_content.text == ""


def test_write_text_file_updates_current_file_without_creating_archive(tmp_path):
    target_path = tmp_path / "MA000018" / "3_2_OT_creation_revised_ruleset_manual.md"

    write_text_file(target_path, "# Updated")

    assert target_path.read_text(encoding="utf-8") == "# Updated"
    assert (target_path.parent / "archive").exists() is False


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.markdown_calls: list[str] = []
        self.write_calls: list[str] = []
        self.code_calls: list[tuple[str, str | None]] = []

    def markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def write(self, text: str) -> None:
        self.write_calls.append(text)

    def code(self, text: str, language: str | None = None) -> None:
        self.code_calls.append((text, language))

    def divider(self) -> None:
        return None

    def warning(self, text: str) -> None:
        self.write_calls.append(text)

    def expander(self, _label: str, expanded: bool = False):
        return _FakeExpander()


def test_render_evaluator_feedback_panel_keeps_structured_sections_when_markdown_exists(
    tmp_path,
    monkeypatch,
):
    markdown_path = tmp_path / "award_overtime_interpretation_evaluator_feedback.md"
    markdown_path.write_text("# Feedback\n\nSummary.", encoding="utf-8")
    json_path = markdown_path.with_suffix(".json")
    json_data = {
        "summary_markdown": "# Feedback\n\nSummary.",
        "rule_reviews": [
            {
                "rule_id": "rule-1",
                "recommendation": "modify",
                "rationale": "Clarify scope.",
            }
        ],
        "new_rules": [
            {
                "rule_id": "rule-2",
                "rule_markdown": "- Add this rule.",
            }
        ],
    }
    json_path.write_text(json.dumps(json_data), encoding="utf-8")

    fake_streamlit = _FakeStreamlit()
    json_expanders: list[str] = []

    monkeypatch.setattr("streamlit_review.app.st", fake_streamlit)
    monkeypatch.setattr("streamlit_review.app.render_file_details", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "streamlit_review.app.render_json_expander",
        lambda label, value, **kwargs: json_expanders.append(label),
    )

    render_evaluator_feedback_panel(markdown_path)

    assert "# Feedback\n\nSummary." in fake_streamlit.markdown_calls
    assert "##### rule-1 (modify)" in fake_streamlit.markdown_calls
    assert "##### rule-2" in fake_streamlit.markdown_calls
    assert "Evaluator feedback JSON" in json_expanders


def test_render_creator_commentary_panel_keeps_structured_json_when_markdown_exists(
    tmp_path,
    monkeypatch,
):
    markdown_path = tmp_path / "award_overtime_interpretation_creator_response.md"
    markdown_path.write_text("Accepted the structured review.", encoding="utf-8")
    json_path = markdown_path.with_suffix(".json")
    json_data = {
        "decision_record_markdown": "Accepted the structured review.",
        "rule_updates": [],
        "new_rule_reviews": [],
    }
    json_path.write_text(json.dumps(json_data), encoding="utf-8")

    fake_streamlit = _FakeStreamlit()
    json_expanders: list[str] = []

    monkeypatch.setattr("streamlit_review.app.st", fake_streamlit)
    monkeypatch.setattr("streamlit_review.app.render_file_details", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "streamlit_review.app.render_json_expander",
        lambda label, value, **kwargs: json_expanders.append(label),
    )

    render_creator_commentary_panel(markdown_path)

    assert "Accepted the structured review." in fake_streamlit.markdown_calls
    assert "Creator commentary JSON" in json_expanders


def test_recommendation_not_implemented_flags_rejected_additions():
    assert recommendation_not_implemented(
        evaluator_recommendation="add",
        creator_decision="reject",
        final_decision="rejected",
    )
    assert not recommendation_not_implemented(
        evaluator_recommendation="add",
        creator_decision="accept",
        final_decision="accepted",
    )


def test_build_review_decision_rows_surfaces_rejected_new_rules():
    evaluator_feedback_data = {
        "rule_reviews": [
            {
                "rule_id": "rule-1",
                "recommendation": "modify",
                "rationale": "Clarify the existing rule.",
            }
        ],
        "new_rules": [
            {
                "rule_id": "rule-2",
                "rule_markdown": "- Add this missing rule. [15.1(c)(ii)]",
            }
        ],
    }
    creator_response_data = {
        "rule_updates": [
            {
                "rule_id": "rule-1",
                "decision": "keep",
                "reason": "Left unchanged.",
                "updated_rule": None,
            }
        ],
        "new_rule_reviews": [
            {
                "rule_id": "rule-2",
                "decision": "reject",
                "reason": "Rejected as duplicate.",
                "updated_rule": None,
            }
        ],
    }
    revised_rules_data = {
        "review_decisions": [
            {
                "rule_id": "rule-1",
                "evaluator_recommendation": "modify",
                "creator_decision": "keep",
                "final_decision": "kept",
                "reason": "Left unchanged.",
            },
            {
                "rule_id": "rule-2",
                "evaluator_recommendation": "add",
                "creator_decision": "reject",
                "final_decision": "rejected",
                "reason": "Rejected as duplicate.",
            },
        ],
        "rules": [
            {
                "rule_id": "rule-1",
                "rule_markdown": "- Existing final rule. [10.1]",
                "clause_references": ["10.1"],
            }
        ],
    }

    rows = build_review_decision_rows(
        evaluator_feedback_data=evaluator_feedback_data,
        creator_response_data=creator_response_data,
        revised_rules_data=revised_rules_data,
    )

    assert len(rows) == 2
    rejected_row = rows[1]
    assert rejected_row["rule_id"] == "rule-2"
    assert rejected_row["proposed_rule_markdown"] == "- Add this missing rule. [15.1(c)(ii)]"
    assert rejected_row["creator_reason"] == "Rejected as duplicate."
    assert rejected_row["is_concern"] is True

    concerns = review_decision_concerns(rows)
    assert [row["rule_id"] for row in concerns] == ["rule-1", "rule-2"]

    summary = summarize_review_decision_rows(rows)
    assert summary["total"] == 2
    assert summary["rejected"] == 1
    assert summary["kept"] == 1
    assert summary["not_implemented"] == 2


def test_index_navigation_wraps_and_clamps():
    assert clamp_index(-4, 3) == 0
    assert clamp_index(8, 3) == 2
    assert previous_index(0, 3) == 2
    assert next_index(2, 3) == 0


def test_format_last_modified_for_display_returns_exact_timestamp(tmp_path):
    output_path = tmp_path / "award.md"
    output_path.write_text("content", encoding="utf-8")

    expected_timestamp = datetime(2026, 6, 23, 10, 11, 12).timestamp()
    output_path.touch()
    output_path.chmod(0o644)
    import os

    os.utime(output_path, (expected_timestamp, expected_timestamp))

    assert format_last_modified_for_display(output_path) == "2026-06-23 10:11:12"


def test_processed_files_matching_prefix_excludes_archive_files(tmp_path):
    keep_archive_path = tmp_path / "3_overtime_interpretations" / "archive"
    keep_archive_path.mkdir(parents=True)
    archived_file = keep_archive_path / "MA000018_overtime_interpretation_20260623_101112.md"
    archived_file.write_text("archive", encoding="utf-8")

    matching_file = tmp_path / "3_overtime_interpretations" / "MA000018_overtime_interpretation.md"
    matching_file.parent.mkdir(parents=True, exist_ok=True)
    matching_file.write_text("latest", encoding="utf-8")

    non_matching_file = tmp_path / "3_overtime_interpretations" / "MA000099_overtime_interpretation.md"
    non_matching_file.write_text("other", encoding="utf-8")

    assert processed_files_matching_prefix("MA000018", processed_root=tmp_path) == [
        matching_file
    ]


def test_processed_files_matching_prefix_includes_award_first_directory_contents(tmp_path):
    award_dir = tmp_path / "MA000018"
    feedback_dir = award_dir / "feedback"
    feedback_dir.mkdir(parents=True)

    main_file = award_dir / "2_1_payment_classification.json"
    main_file.write_text("{}", encoding="utf-8")
    feedback_file = feedback_dir / "3_2_OT_creation_creator_response.md"
    feedback_file.write_text("# feedback", encoding="utf-8")
    archived_file = award_dir / "archive" / "2_1_payment_classification_20260623_101112.json"
    archived_file.parent.mkdir(parents=True)
    archived_file.write_text("{}", encoding="utf-8")

    assert processed_files_matching_prefix("MA000018", processed_root=tmp_path) == [
        main_file,
        feedback_file,
    ]


def test_delete_processed_files_matching_prefix_deletes_only_non_archive_matches(tmp_path):
    latest_file = tmp_path / "2_payment_clause_identifier" / "MA000018_payment_classification.json"
    latest_file.parent.mkdir(parents=True)
    latest_file.write_text("{}", encoding="utf-8")

    second_latest_file = tmp_path / "5b_generate_overtime_pseudocode" / "MA000018_core_overtime_pseudocode.md"
    second_latest_file.parent.mkdir(parents=True)
    second_latest_file.write_text("# Pseudocode", encoding="utf-8")

    archive_file = tmp_path / "5b_generate_overtime_pseudocode" / "archive" / "MA000018_core_overtime_pseudocode_20260623_101112.md"
    archive_file.parent.mkdir(parents=True)
    archive_file.write_text("# Archived", encoding="utf-8")

    other_file = tmp_path / "5b_generate_overtime_pseudocode" / "MA000099_core_overtime_pseudocode.md"
    other_file.write_text("# Other", encoding="utf-8")

    deleted_paths = delete_processed_files_matching_prefix("MA000018", processed_root=tmp_path)

    assert deleted_paths == [latest_file, second_latest_file]
    assert latest_file.exists() is False
    assert second_latest_file.exists() is False
    assert archive_file.exists() is True
    assert other_file.exists() is True


def test_delete_processed_files_matching_prefix_deletes_award_first_directory_contents(tmp_path):
    award_dir = tmp_path / "MA000018"
    feedback_dir = award_dir / "feedback"
    feedback_dir.mkdir(parents=True)

    main_file = award_dir / "2_1_payment_classification.json"
    main_file.write_text("{}", encoding="utf-8")
    feedback_file = feedback_dir / "3_2_OT_creation_creator_response.md"
    feedback_file.write_text("# feedback", encoding="utf-8")
    archive_file = award_dir / "archive" / "2_1_payment_classification_20260623_101112.json"
    archive_file.parent.mkdir(parents=True)
    archive_file.write_text("{}", encoding="utf-8")

    deleted_paths = delete_processed_files_matching_prefix("MA000018", processed_root=tmp_path)

    assert deleted_paths == [main_file, feedback_file]
    assert main_file.exists() is False
    assert feedback_file.exists() is False
    assert archive_file.exists() is True
    assert award_dir.exists() is True


def test_pipeline_run_label_formats_full_and_step_runs():
    assert pipeline_run_label(None) == "Active pipeline run"
    assert pipeline_run_label("3.2") == "Review overtime ruleset"
    assert pipeline_run_label("4.1") == "Format overtime guide"


def test_streamlit_and_background_pipeline_step_labels_stay_identical():
    assert APP_PIPELINE_STEP_LABELS == BACKGROUND_PIPELINE_STEP_LABELS


def test_background_pipeline_run_label_includes_ruleset_when_provided():
    assert background_pipeline_run_label(None) == "Active pipeline run"
    assert (
        background_pipeline_run_label("3.1", OVERTIME_CONSEQUENCE_RULESET)
        == "Generate overtime consequence ruleset"
    )
    assert (
        background_pipeline_run_label("3.2", OVERTIME_CONSEQUENCE_RULESET)
        == "Review overtime consequence ruleset"
    )
    assert (
        background_pipeline_run_label("4.1", OVERTIME_CONSEQUENCE_RULESET)
        == "Format overtime consequence ruleset"
    )
    assert (
        background_pipeline_run_label("5.1", OVERTIME_CONSEQUENCE_RULESET)
        == "Generate overtime consequence pseudocode"
    )
    assert (
        background_pipeline_run_label(None, OVERTIME_CONSEQUENCE_RULESET)
        == "overtime consequence pipeline run"
    )


@pytest.mark.parametrize(
    ("trigger_key", "expected_step"),
    [
        ("run_full_MA000120", None),
        ("run_step_3_2_MA000120", "3.2"),
        ("run_step_4_1_MA000120", "4.1"),
        ("run_step_5_1_MA000120", "5.1"),
    ],
)
def test_render_pipeline_run_controls_passes_selected_ruleset_for_ruleset_runs(
    monkeypatch,
    trigger_key: str,
    expected_step: str | None,
):
    calls: list[tuple[str, str | None, str | None]] = []

    class DummyColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_button(_label: str, *, key: str, **_kwargs) -> bool:
        return key == trigger_key

    monkeypatch.setattr("streamlit_review.app.normalized_status_for_award", lambda _award: None)
    monkeypatch.setattr("streamlit_review.app.render_pipeline_run_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("streamlit_review.app.execute_pipeline_run", lambda award_code, step, ruleset_key=None: calls.append((award_code, step, ruleset_key)))
    monkeypatch.setattr("streamlit_review.app.st.button", fake_button)
    monkeypatch.setattr(
        "streamlit_review.app.st.columns",
        lambda count, gap="small": tuple(DummyColumn() for _ in range(count)),
    )

    render_pipeline_run_controls(
        selected_award_code="MA000120",
        controls_disabled=False,
        ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
    )

    assert calls == [("MA000120", expected_step, OVERTIME_CONSEQUENCE_RULESET)]


def test_available_award_code_index_prefers_current_selection_when_present():
    award_codes = ["MA000002", "MA000018", "ColesRetailEnterpriseAgreement2024"]

    assert available_award_code_index(award_codes, "ma000018") == 1
    assert available_award_code_index(award_codes, "ColesRetailEnterpriseAgreement2024") == 2
    assert available_award_code_index(award_codes, "MA999999") == 0


def test_validate_award_code_input_accepts_existing_output_sets_or_standard_codes():
    existing_output_sets = [
        "ColesRetailEnterpriseAgreement2024",
        "EBA-Woolworths-2024-F",
    ]

    assert validate_award_code_input(" ma000018 ") == ("MA000018", None)
    assert validate_award_code_input(
        "ColesRetailEnterpriseAgreement2024",
        existing_output_sets=existing_output_sets,
    ) == ("ColesRetailEnterpriseAgreement2024", None)
    assert validate_award_code_input(
        "EBA-Woolworths-2024-F",
        existing_output_sets=existing_output_sets,
    ) == ("EBA-Woolworths-2024-F", None)
    assert validate_award_code_input("") == (None, "Enter an award code to review or run.")
    assert validate_award_code_input(
        "MA00003",
        existing_output_sets=existing_output_sets,
    ) == (None, "Select an existing output set or enter an award code like `MA000002`.")


def test_source_record_for_award_reads_registered_local_pdf(tmp_path):
    registry_path = tmp_path / "source_registry.json"
    pdf_path = tmp_path / "ColesRetailEnterpriseAgreement2024.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")

    register_local_pdf_source(
        award_code="ColesRetailEnterpriseAgreement2024",
        pdf_path=pdf_path,
        display_name="Coles Retail Enterprise Agreement 2024",
        registry_path=registry_path,
    )

    record = source_record_for_award(
        "ColesRetailEnterpriseAgreement2024",
        registry_path=registry_path,
    )

    assert record["source_type"] == SOURCE_TYPE_LOCAL_PDF
    assert record["source_path"] == str(pdf_path)
    assert can_run_pipeline_for_award(
        "ColesRetailEnterpriseAgreement2024",
        registry_path=registry_path,
    ) is True


def test_combine_pipeline_logs_keeps_stdout_and_stderr_sections():
    combined = combine_pipeline_logs("stdout line\n", "stderr line\n")

    assert combined == "stdout line\n\nstderr line"


def test_move_selected_index_updates_index_and_widget_selection(monkeypatch):
    session_state: dict[str, object] = {"panel_l1_index": 0}
    monkeypatch.setattr("streamlit_review.app.st.session_state", session_state)

    move_selected_index(
        "panel_l1_index",
        "panel_l1_index_selected_value",
        "panel_l1_index_selector",
        ["1", "2", "3"],
        1,
    )

    assert session_state["panel_l1_index"] == 1
    assert session_state["panel_l1_index_selected_value"] == "2"
    assert session_state["panel_l1_index_selector"] == "2"


def test_run_pipeline_for_award_calls_selected_step(monkeypatch):
    calls: list[tuple[str, object]] = []

    def fake_source_record_for_award(award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", award_code))
        return {
            "source_type": "fair_work_html",
            "source_url": "https://example.com/MA000002.html",
        }

    def fake_build_paths(award_code: str, suffix, url: str):
        calls.append(("build_paths", award_code, suffix, url))
        return sentinel.paths

    def fake_run_selected_step(paths, step: str) -> None:
        calls.append(("run_selected_step", paths, step))
        print("step output")

    monkeypatch.setattr(
        "streamlit_review.app.source_record_for_award",
        fake_source_record_for_award,
    )
    monkeypatch.setattr("streamlit_review.app.build_paths", fake_build_paths)
    monkeypatch.setattr("streamlit_review.app.run_selected_step", fake_run_selected_step)

    result = run_pipeline_for_award("MA000002", "3.1")

    assert result["success"] is True
    assert "step output" in result["log"]
    assert calls == [
        ("source_record_for_award", "MA000002"),
        ("build_paths", "MA000002", None, "https://example.com/MA000002.html"),
        ("run_selected_step", sentinel.paths, "3.1"),
    ]


def test_run_pipeline_for_award_calls_step_4_formatter(monkeypatch):
    calls: list[tuple[str, object]] = []
    artifact_paths = SimpleNamespace(
        revised_overtime_interpretation=sentinel.revised_path,
        overtime_entitlements=sentinel.entitlements_path,
    )

    def fake_source_record_for_award(award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", award_code))
        return {
            "source_type": "fair_work_html",
            "source_url": "https://example.com/MA000002.html",
        }

    def fake_build_paths(award_code: str, suffix, url: str):
        calls.append(("build_paths", award_code, suffix, url))
        return sentinel.paths

    def fake_artifact_paths_for_award(award_code: str):
        calls.append(("artifact_paths_for_award", award_code))
        return artifact_paths

    def fake_summarize_overtime_entitlements(*, interpretation_path, output_path) -> None:
        calls.append(("summarize_overtime_entitlements", interpretation_path, output_path))
        print("step 4 output")

    monkeypatch.setattr(
        "streamlit_review.app.source_record_for_award",
        fake_source_record_for_award,
    )
    monkeypatch.setattr("streamlit_review.app.build_paths", fake_build_paths)
    monkeypatch.setattr(
        "streamlit_review.app.artifact_paths_for_award",
        fake_artifact_paths_for_award,
    )
    monkeypatch.setattr(
        "streamlit_review.app.summarize_overtime_entitlements",
        fake_summarize_overtime_entitlements,
    )

    result = run_pipeline_for_award("MA000002", "4.1")

    assert result["success"] is True
    assert "step 4 output" in result["log"]
    assert calls == [
        ("source_record_for_award", "MA000002"),
        ("build_paths", "MA000002", None, "https://example.com/MA000002.html"),
        ("artifact_paths_for_award", "MA000002"),
        (
            "summarize_overtime_entitlements",
            sentinel.revised_path,
            sentinel.entitlements_path,
        ),
    ]


def test_run_pipeline_for_award_calls_full_pipeline(monkeypatch):
    calls: list[tuple[str, object]] = []

    def fake_source_record_for_award(award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", award_code))
        return {
            "source_type": "fair_work_html",
            "source_url": f"https://example.com/{award_code}.html",
        }

    def fake_build_paths(award_code: str, suffix, url: str):
        calls.append(("build_paths", award_code, suffix, url))
        return sentinel.paths

    def fake_run_default_pipeline(paths) -> None:
        calls.append(("run_default_pipeline", paths))
        print("full output")

    monkeypatch.setattr(
        "streamlit_review.app.source_record_for_award",
        fake_source_record_for_award,
    )
    monkeypatch.setattr("streamlit_review.app.build_paths", fake_build_paths)
    monkeypatch.setattr("streamlit_review.app.run_default_pipeline", fake_run_default_pipeline)

    result = run_pipeline_for_award("MA000002", None)

    assert result["success"] is True
    assert "full output" in result["log"]
    assert calls == [
        ("source_record_for_award", "MA000002"),
        ("build_paths", "MA000002", None, "https://example.com/MA000002.html"),
        ("run_default_pipeline", sentinel.paths),
    ]


def test_run_pipeline_for_award_uses_registered_local_pdf_for_step_1(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    award = {"Sample Agreement": {"_content": [], "1": {"_content": ["Title"]}}}

    def fake_source_record_for_award(award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", award_code))
        return {
            "source_type": "local_pdf",
            "source_path": str(pdf_path),
        }

    def fake_build_paths(award_code: str, suffix, url: str):
        calls.append(("build_paths", award_code, suffix, url))
        return SimpleNamespace(
            award_json_path=tmp_path / "processed" / "Sample" / "Sample.json",
            raw_html_path=tmp_path / "processed" / "Sample" / "raw" / "Sample.html",
            output_stem="Sample",
        )

    def fake_artifact_paths_for_award(award_code: str):
        calls.append(("artifact_paths_for_award", award_code))
        return SimpleNamespace(
            revised_overtime_interpretation=sentinel.revised_path,
            overtime_entitlements=sentinel.entitlements_path,
        )

    def fake_extract_pdf_to_award(path):
        calls.append(("extract_pdf_to_award", path))
        return "# markdown", award, {"Appendix": {"_content": []}}, [{"reference": "1"}]

    def fake_write_pdf_outputs(**kwargs):
        calls.append(("write_pdf_outputs", kwargs["pdf_path"], kwargs["output_stem_value"]))

    monkeypatch.setattr("streamlit_review.app.source_record_for_award", fake_source_record_for_award)
    monkeypatch.setattr("streamlit_review.app.build_paths", fake_build_paths)
    monkeypatch.setattr("streamlit_review.app.artifact_paths_for_award", fake_artifact_paths_for_award)
    monkeypatch.setattr("streamlit_review.app.extract_pdf_to_award", fake_extract_pdf_to_award)
    monkeypatch.setattr("streamlit_review.app.write_pdf_outputs", fake_write_pdf_outputs)

    result = run_pipeline_for_award("Sample", "1")

    assert result["success"] is True
    assert calls == [
        ("source_record_for_award", "Sample"),
        ("build_paths", "Sample", None, ""),
        ("artifact_paths_for_award", "Sample"),
        ("extract_pdf_to_award", pdf_path),
        ("write_pdf_outputs", pdf_path, "Sample"),
    ]


def test_background_run_pipeline_reports_progress_and_writes_live_log(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []
    status_updates: list[dict[str, object]] = []
    live_log_path = tmp_path / "pipeline.log"

    def fake_source_record_for_award(award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", award_code))
        return {
            "source_type": "fair_work_html",
            "source_url": "https://example.com/MA000002.html",
        }

    def fake_build_paths(award_code: str, suffix, url: str):
        calls.append(("build_paths", award_code, suffix, url))
        return sentinel.paths

    def fake_artifact_paths_for_award(award_code: str):
        calls.append(("artifact_paths_for_award", award_code))
        return SimpleNamespace(
            revised_overtime_interpretation=sentinel.revised_path,
            overtime_entitlements=sentinel.entitlements_path,
        )

    def fake_run_selected_step(paths, step: str) -> None:
        calls.append(("run_selected_step", paths, step))
        print(f"output from {step}")

    def fake_summarize_overtime_entitlements(*, interpretation_path, output_path) -> None:
        calls.append(("summarize_overtime_entitlements", interpretation_path, output_path))
        print("output from 4")

    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.source_record_for_award",
        fake_source_record_for_award,
    )
    monkeypatch.setattr("streamlit_review.pipeline_runs.build_paths", fake_build_paths)
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.artifact_paths_for_award",
        fake_artifact_paths_for_award,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.run_selected_step",
        fake_run_selected_step,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.summarize_overtime_entitlements",
        fake_summarize_overtime_entitlements,
    )

    result = background_run_pipeline_for_award(
        "MA000002",
        None,
        status_callback=status_updates.append,
        log_path=live_log_path,
    )

    assert result["success"] is True
    assert result["completed_steps"] == 7
    assert result["total_steps"] == 7
    assert "Starting step 1 of 7: Retrieve award" in live_log_path.read_text(encoding="utf-8")
    assert "output from 5.1" in live_log_path.read_text(encoding="utf-8")
    assert status_updates[0]["total_steps"] == 7
    assert status_updates[0]["current_step"] == "1"
    assert status_updates[-1]["progress_fraction"] == 1.0
    assert calls == [
        ("source_record_for_award", "MA000002"),
        ("build_paths", "MA000002", None, "https://example.com/MA000002.html"),
        ("artifact_paths_for_award", "MA000002"),
        ("run_selected_step", sentinel.paths, "1"),
        ("run_selected_step", sentinel.paths, "2.1"),
        ("run_selected_step", sentinel.paths, "2.2"),
        ("run_selected_step", sentinel.paths, "3.1"),
        ("run_selected_step", sentinel.paths, "3.2"),
        (
            "summarize_overtime_entitlements",
            sentinel.revised_path,
            sentinel.entitlements_path,
        ),
        ("run_selected_step", sentinel.paths, "5.1"),
    ]


def test_background_run_pipeline_uses_selected_ruleset_for_full_ruleset_run(
    monkeypatch,
    tmp_path,
):
    calls: list[tuple[str, object]] = []
    award_code = "MA000120"
    classification_path = tmp_path / award_code / "2_1_payment_classification.json"
    classification_path.parent.mkdir(parents=True, exist_ok=True)
    classification_path.write_text("{}", encoding="utf-8")

    combined_markdown = ruleset_output_path_for_classification(
        classification_path,
        OVERTIME_CONSEQUENCE_RULESET,
    )
    combined_json = combined_markdown.with_suffix(".json")
    revised_markdown = combined_markdown.with_name("3_2_OT_consequence_revised_ruleset.md")
    revised_json = revised_markdown.with_suffix(".json")
    formatted_markdown = combined_markdown.with_name("4_1_OT_consequence_formatted_ruleset.md")
    manual_ruleset_markdown = combined_markdown.with_name("3_2_OT_consequence_revised_ruleset_manual.md")
    pseudocode_markdown = combined_markdown.with_name("5_1_OT_consequence_pseudocode.md")
    combined_markdown.parent.mkdir(parents=True, exist_ok=True)
    combined_markdown.write_text("# Combined", encoding="utf-8")
    combined_json.write_text("{}", encoding="utf-8")

    ruleset_artifacts = SimpleNamespace(
        revised_markdown=revised_markdown,
        revised_json=revised_json,
        combined_markdown=combined_markdown,
        combined_json=combined_json,
        formatted_markdown=formatted_markdown,
        manual_ruleset_markdown=manual_ruleset_markdown,
        pseudocode_markdown=pseudocode_markdown,
    )

    def fake_source_record_for_award(selected_award_code: str) -> dict[str, str]:
        calls.append(("source_record_for_award", selected_award_code))
        return {
            "source_type": "fair_work_html",
            "source_url": f"https://example.com/{selected_award_code}.html",
        }

    def fake_build_paths(selected_award_code: str, suffix, url: str):
        calls.append(("build_paths", selected_award_code, suffix, url))
        return SimpleNamespace(classification_path=classification_path)

    def fake_artifact_paths_for_award(selected_award_code: str):
        calls.append(("artifact_paths_for_award", selected_award_code))
        return sentinel.legacy_artifacts

    def fake_ruleset_artifact_paths_for_award(selected_award_code: str, ruleset_key: str):
        calls.append(("ruleset_artifact_paths_for_award", selected_award_code, ruleset_key))
        return ruleset_artifacts

    def fake_run_selected_step(paths, step: str) -> None:
        calls.append(("run_selected_step", paths.classification_path, step))

    def fake_generate_overtime_ruleset(*, classification_path: Path, ruleset_key: str) -> None:
        calls.append(("generate_overtime_ruleset", classification_path, ruleset_key))

    def fake_review_overtime_interpretation(**kwargs) -> None:
        calls.append(
            (
                "review_overtime_interpretation",
                kwargs["interpretation_path"],
                kwargs["overtime_clause_classification_path"],
                kwargs["ruleset_key"],
            )
        )
        kwargs["revised_output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["revised_output_path"].write_text("# Revised", encoding="utf-8")

    def fake_summarize_overtime_entitlements(*, interpretation_path, output_path) -> None:
        calls.append(("summarize_overtime_entitlements", interpretation_path, output_path))
        output_path.write_text("# Formatted", encoding="utf-8")

    def fake_generate_core_overtime_pseudocode(*, summary_path, output_path) -> None:
        calls.append(("generate_core_overtime_pseudocode", summary_path, output_path))

    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.source_record_for_award",
        fake_source_record_for_award,
    )
    monkeypatch.setattr("streamlit_review.pipeline_runs.build_paths", fake_build_paths)
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.artifact_paths_for_award",
        fake_artifact_paths_for_award,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.ruleset_artifact_paths_for_award",
        fake_ruleset_artifact_paths_for_award,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.run_selected_step",
        fake_run_selected_step,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.generate_overtime_ruleset",
        fake_generate_overtime_ruleset,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.review_overtime_interpretation",
        fake_review_overtime_interpretation,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.summarize_overtime_entitlements",
        fake_summarize_overtime_entitlements,
    )
    monkeypatch.setattr(
        "streamlit_review.pipeline_runs.generate_core_overtime_pseudocode",
        fake_generate_core_overtime_pseudocode,
    )

    result = background_run_pipeline_for_award(
        award_code,
        None,
        ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
    )

    assert result["success"] is True
    assert calls == [
        ("source_record_for_award", award_code),
        ("build_paths", award_code, None, f"https://example.com/{award_code}.html"),
        ("artifact_paths_for_award", award_code),
        ("run_selected_step", classification_path, "1"),
        ("run_selected_step", classification_path, "2.1"),
        ("run_selected_step", classification_path, "2.2"),
        (
            "generate_overtime_ruleset",
            classification_path,
            OVERTIME_CONSEQUENCE_RULESET,
        ),
        (
            "review_overtime_interpretation",
            combined_markdown,
            ruleset_clause_classification_output_path_for_classification(
                classification_path,
                OVERTIME_CONSEQUENCE_RULESET,
            ),
            OVERTIME_CONSEQUENCE_RULESET,
        ),
        (
            "ruleset_artifact_paths_for_award",
            award_code,
            OVERTIME_CONSEQUENCE_RULESET,
        ),
        (
            "summarize_overtime_entitlements",
            revised_markdown,
            formatted_markdown,
        ),
        (
            "ruleset_artifact_paths_for_award",
            award_code,
            OVERTIME_CONSEQUENCE_RULESET,
        ),
        (
            "generate_core_overtime_pseudocode",
            formatted_markdown,
            pseudocode_markdown,
        ),
    ]
