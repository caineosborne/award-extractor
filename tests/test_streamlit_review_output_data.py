import json
from datetime import datetime
from pathlib import Path

from streamlit_review.app import (
    manual_4b_editor_widget_key,
    overtime_clause_text_widget_key,
)
from streamlit_review.output_data import (
    ArtifactPaths,
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
    source_path_for_core_overtime_pseudocode,
    source_path_for_manual_4b_editor,
)


def test_discover_award_codes_from_payment_classification_files(tmp_path):
    (tmp_path / "MA000018_payment_classification.json").write_text("{}", encoding="utf-8")
    (tmp_path / "MA000002_payment_classification.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ignore.json").write_text("{}", encoding="utf-8")

    assert discover_award_codes(tmp_path) == ["MA000002", "MA000018"]


def test_artifact_paths_for_award():
    paths = artifact_paths_for_award("MA000018")

    assert paths.payment_classification.name == "MA000018_payment_classification.json"
    assert (
        paths.overtime_clause_classification.name
        == "MA000018_overtime_clause_classification.json"
    )
    assert paths.original_overtime_interpretation.name == "MA000018_overtime_interpretation.md"
    assert (
        paths.agentic_review_conversation.name
        == "MA000018_overtime_interpretation_agentic_review_conversation.md"
    )
    assert (
        paths.evaluator_feedback.name
        == "MA000018_overtime_interpretation_evaluator_feedback.md"
    )
    assert (
        paths.creator_response.name
        == "MA000018_overtime_interpretation_creator_response.md"
    )
    assert (
        paths.revised_overtime_interpretation.name
        == "MA000018_overtime_interpretation_revised.md"
    )
    assert (
        paths.manual_4b_overtime_interpretation.name
        == "MA000018_overtime_interpretation_4b.md"
    )
    assert paths.core_overtime_pseudocode.name == "MA000018_core_overtime_pseudocode.md"


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


def test_manual_4b_editor_widget_key_uses_output_path_stem():
    output_path = Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_4b.md")

    assert (
        manual_4b_editor_widget_key("screen_one", output_path)
        == "screen_one_manual_4b_editor_MA000018_overtime_interpretation_4b"
    )


def test_manual_4b_editor_prefers_existing_saved_update_then_revised_source(tmp_path):
    original_path = tmp_path / "award_overtime_interpretation.md"
    revised_path = tmp_path / "award_overtime_interpretation_revised.md"
    manual_4b_path = tmp_path / "award_overtime_interpretation_4b.md"

    artifact_paths = ArtifactPaths(
        payment_classification=tmp_path / "award_payment_classification.json",
        overtime_clause_classification=tmp_path / "award_overtime_clause_classification.json",
        original_overtime_interpretation=original_path,
        agentic_review_conversation=tmp_path
        / "award_overtime_interpretation_agentic_review_conversation.md",
        evaluator_feedback=tmp_path / "award_overtime_interpretation_evaluator_feedback.md",
        creator_response=tmp_path / "award_overtime_interpretation_creator_response.md",
        revised_overtime_interpretation=revised_path,
        manual_4b_overtime_interpretation=manual_4b_path,
        core_overtime_pseudocode=tmp_path / "award_core_overtime_pseudocode.md",
    )

    assert source_path_for_manual_4b_editor(artifact_paths) == original_path

    revised_path.write_text("# Revised 3B", encoding="utf-8")
    assert source_path_for_manual_4b_editor(artifact_paths) == revised_path

    manual_4b_path.write_text("# Saved 4B", encoding="utf-8")
    assert source_path_for_manual_4b_editor(artifact_paths) == manual_4b_path


def test_core_overtime_pseudocode_prefers_existing_4b_then_revised_source(tmp_path):
    original_path = tmp_path / "award_overtime_interpretation.md"
    revised_path = tmp_path / "award_overtime_interpretation_revised.md"
    manual_4b_path = tmp_path / "award_overtime_interpretation_4b.md"

    artifact_paths = ArtifactPaths(
        payment_classification=tmp_path / "award_payment_classification.json",
        overtime_clause_classification=tmp_path / "award_overtime_clause_classification.json",
        original_overtime_interpretation=original_path,
        agentic_review_conversation=tmp_path
        / "award_overtime_interpretation_agentic_review_conversation.md",
        evaluator_feedback=tmp_path / "award_overtime_interpretation_evaluator_feedback.md",
        creator_response=tmp_path / "award_overtime_interpretation_creator_response.md",
        revised_overtime_interpretation=revised_path,
        manual_4b_overtime_interpretation=manual_4b_path,
        core_overtime_pseudocode=tmp_path / "award_core_overtime_pseudocode.md",
    )

    assert source_path_for_core_overtime_pseudocode(artifact_paths) == original_path

    revised_path.write_text("# Revised 3B", encoding="utf-8")
    assert source_path_for_core_overtime_pseudocode(artifact_paths) == revised_path

    manual_4b_path.write_text("# Saved 4B", encoding="utf-8")
    assert source_path_for_core_overtime_pseudocode(artifact_paths) == manual_4b_path


def test_missing_text_file_returns_status_without_exception(tmp_path):
    missing_path = tmp_path / "missing.md"

    file_content = read_text_file(missing_path)

    assert file_content.path == missing_path
    assert file_content.exists is False
    assert file_content.text == ""


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
