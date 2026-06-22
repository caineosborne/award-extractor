import json
from pathlib import Path

from streamlit_review.app import overtime_clause_text_widget_key
from streamlit_review.output_data import (
    artifact_paths_for_award,
    clamp_index,
    discover_award_codes,
    l1_clause_keys,
    l1_record,
    l2_clause_keys,
    l2_record,
    next_index,
    overtime_classification_keys,
    overtime_classification_record,
    previous_index,
    read_text_file,
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
