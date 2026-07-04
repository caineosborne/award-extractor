import json
import tempfile
from pathlib import Path

from src.common.overtime_rulesets import PENALTIES_RULESET
from src.step_2_2_classify_overtime_clauses.llm import (
    prepare_overtime_clause_classifications,
)


def test_prepare_penalties_clause_classifications_is_deterministic_and_inclusive():
    data = {
        "classified_clauses": {
            "26.1": {
                "tags": ["Penalty"],
                "text": "Employees working afternoon or night shift will be paid 10% extra.",
            },
            "27.1": {
                "tags": ["Breaks (Between Work Periods)"],
                "text": "An employee must have a minimum break of 10 hours between shifts.",
            },
            "28.1": {
                "tags": ["Breaks (Between Work Periods)"],
                "text": (
                    "If a shiftworker resumes work without 10 hours off duty, they will "
                    "be paid at 200% until released."
                ),
            },
            "99.1": {
                "tags": ["Ordinary Hours & Overtime"],
                "text": "Ordinary hours are worked Monday to Friday.",
            },
        }
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        classification_path = Path(temp_dir) / "2_1_payment_classification.json"
        output_path = Path(temp_dir) / "2_2_Penalties_clause_classification.json"
        classification_path.write_text(json.dumps(data), encoding="utf-8")

        classifications = prepare_overtime_clause_classifications(
            classification_path=classification_path,
            classification_output_path=output_path,
            ruleset_key=PENALTIES_RULESET,
        )

        assert [item.clause_number for item in classifications] == ["26.1", "27.1", "28.1"]
        assert all(item.classification == "Penalty Rule" for item in classifications)
        assert classifications[0].employee_cohort == "all"
        assert classifications[1].employee_cohort == "all"
        assert classifications[2].work_arrangement == "shiftworker"
        assert "Penalty" in classifications[0].explanation
        assert "Breaks (Between Work Periods)" in classifications[1].explanation

        written_artifact = json.loads(output_path.read_text(encoding="utf-8"))
        assert written_artifact["ruleset_key"] == PENALTIES_RULESET
        assert written_artifact["included_categories_for_interpretation"] == ["Penalty Rule"]
        assert [item["clause_number"] for item in written_artifact["clauses"]] == [
            "26.1",
            "27.1",
            "28.1",
        ]


def test_prepare_penalties_clause_classifications_sets_explicit_employee_cohort_only():
    data = {
        "classified_clauses": {
            "14.1": {
                "tags": ["Penalty"],
                "text": (
                    "For a full-time or part-time employee, Saturday hours are paid at "
                    "125% of the ordinary hourly rate."
                ),
            },
            "14.2": {
                "tags": ["Penalty"],
                "text": "For a casual employee, Sunday hours are paid at 175%.",
            },
        }
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        classification_path = Path(temp_dir) / "2_1_payment_classification.json"
        output_path = Path(temp_dir) / "2_2_Penalties_clause_classification.json"
        classification_path.write_text(json.dumps(data), encoding="utf-8")

        classifications = prepare_overtime_clause_classifications(
            classification_path=classification_path,
            classification_output_path=output_path,
            ruleset_key=PENALTIES_RULESET,
        )

        assert classifications[0].employee_cohort == "permanent"
        assert classifications[1].employee_cohort == "casual"
