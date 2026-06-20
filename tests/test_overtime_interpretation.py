import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_3_interpret_overtime import (
    DEFAULT_MODEL,
    OVERTIME_CREATION_CLASSIFICATIONS,
    OvertimeClauseClassification,
    build_messages,
    classification_output_path_for_classification,
    classification_response_json_schema,
    filter_overtime_creation_clauses,
    filter_overtime_clauses,
    format_clauses_for_prompt,
    generate_overtime_interpretation,
    output_path_for_classification,
)


class FakeResponses:
    def __init__(self, output_texts):
        self.output_texts = list(output_texts)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_texts.pop(0))


class FakeClient:
    def __init__(self, output_texts):
        self.responses = FakeResponses(output_texts)


class OvertimeInterpretationTests(unittest.TestCase):
    def test_filter_overtime_clauses_matches_requested_filter(self):
        data = {
            "classified_clauses": {
                "10.1": {"tags": ["Ordinary Hours & Overtime"], "text": "ordinary"},
                "20.1": {"tags": ["Ordinary Hours & Overtime"], "text": "overtime"},
                "30.1": {"tags": ["Penalty"], "text": "penalty"},
            }
        }

        results = filter_overtime_clauses(data)

        self.assertEqual(list(results), ["10.1", "20.1"])

    def test_output_path_for_classification(self):
        self.assertEqual(
            output_path_for_classification(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json")
            ),
            Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"),
        )

    def test_classification_output_path_for_classification(self):
        self.assertEqual(
            classification_output_path_for_classification(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json")
            ),
            Path(
                "data/processed/3_overtime_interpretations/"
                "MA000018_overtime_clause_classification.json"
            ),
        )

    def test_format_clauses_for_prompt_uses_plain_clause_sections(self):
        prompt_text = format_clauses_for_prompt(
            {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime applies after ordinary hours.",
                }
            }
        )

        self.assertIn("## Clause 20.1", prompt_text)
        self.assertIn("Overtime applies after ordinary hours.", prompt_text)

    def test_classification_response_schema_lists_allowed_categories(self):
        schema = classification_response_json_schema()
        classification_enum = schema["properties"]["clauses"]["items"]["properties"][
            "classification"
        ]["enum"]

        self.assertIn("Ordinary Hours Boundary", classification_enum)
        self.assertIn("Overtime Trigger", classification_enum)
        self.assertIn("Overtime Consequence", classification_enum)
        self.assertIn("Related Rule", classification_enum)
        self.assertIn("Not Relevant", classification_enum)

    def test_filter_overtime_creation_clauses_keeps_only_creation_categories(self):
        classifications = [
            OvertimeClauseClassification(
                clause_number="10.1",
                classification="Ordinary Hours Boundary",
                clause_text="Ordinary hours are 38 per week.",
                explanation="Defines ordinary hours.",
            ),
            OvertimeClauseClassification(
                clause_number="20.1",
                classification="Overtime Trigger",
                clause_text="Overtime applies after 10 hours.",
                explanation="Directly creates overtime.",
            ),
            OvertimeClauseClassification(
                clause_number="30.1",
                classification="Overtime Consequence",
                clause_text="Overtime is paid at 150%.",
                explanation="Explains payment after overtime exists.",
            ),
        ]

        results = filter_overtime_creation_clauses(classifications)

        self.assertEqual(
            [classification.classification for classification in results],
            list(OVERTIME_CREATION_CLASSIFICATIONS),
        )

    def test_build_messages_includes_required_working_document_sections(self):
        messages = build_messages(
            "classification.json",
            [
                OvertimeClauseClassification(
                    clause_number="20.1",
                    classification="Overtime Trigger",
                    clause_text="Paid overtime.",
                    explanation="Directly creates overtime.",
                )
            ],
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("expert payroll award interpretation assistant", system_prompt)
        self.assertIn("What circumstances increase Total Overtime Hours?", user_prompt)
        self.assertIn("Special Instructions:", user_prompt)
        self.assertIn("explicit and implicit triggers", user_prompt)
        self.assertIn("Do not include:", user_prompt)
        self.assertIn("specific employee segment section only when", user_prompt)
        self.assertIn("Do not repeat a general rule", user_prompt)
        self.assertIn("Avoid duplicate rules:", user_prompt)
        self.assertNotIn("What data is required", user_prompt)
        self.assertNotIn("What assumptions are being made", user_prompt)
        self.assertIn("## Clause 20.1", user_prompt)
        self.assertIn("Overtime Trigger", user_prompt)

    def test_generate_overtime_interpretation_writes_markdown_with_mocked_client(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
                "21.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime is paid at 150%.",
                    "reason": "Explains the overtime rate.",
                },
                "30.1": {
                    "tags": ["Penalty"],
                    "text": "Weekend penalty.",
                },
            }
        }
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "clause_text": "Employees are paid overtime after ordinary hours.",
                        "explanation": "Directly creates overtime.",
                    },
                    {
                        "clause_number": "21.1",
                        "classification": "Overtime Consequence",
                        "clause_text": "Overtime is paid at 150%.",
                        "explanation": "Explains payment after overtime exists.",
                    },
                ]
            }
        )
        fake_client = FakeClient(
            [
                classification_json,
                "## All Employees\n\n"
                "- The hours will be overtime after ordinary hours. [20.1]",
            ]
        )
        expected_markdown = (
            "## All Employees\n\n"
            "- The hours will be overtime after ordinary hours. [20.1]"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            output_path = Path(temp_dir) / "award_overtime_interpretation.md"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            result = generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")
            classification_path = Path(temp_dir) / (
                "3_overtime_interpretations/award_overtime_clause_classification.json"
            )
            classification_artifact = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_interpretation_*.md")
            )
            classification_archive_files = list(
                (Path(temp_dir) / "3_overtime_interpretations" / "archive").glob(
                    "award_overtime_clause_classification_*.json"
                )
            )

        self.assertEqual(result, written)
        self.assertEqual(written, expected_markdown)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(len(classification_archive_files), 1)
        self.assertEqual(
            classification_artifact["schema_version"],
            "overtime-clause-classification-v1",
        )
        self.assertEqual(len(classification_artifact["clauses"]), 2)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertEqual(fake_client.responses.calls[1]["model"], DEFAULT_MODEL)
        self.assertIn("## Clause 20.1", fake_client.responses.calls[0]["input"][1]["content"])
        self.assertIn(
            "Employees are paid overtime after ordinary hours.",
            fake_client.responses.calls[1]["input"][1]["content"],
        )
        self.assertNotIn(
            "Overtime is paid at 150%.",
            fake_client.responses.calls[1]["input"][1]["content"],
        )
        self.assertNotIn(
            "## Clause 30.1",
            fake_client.responses.calls[0]["input"][1]["content"],
        )

    def test_generate_overtime_interpretation_reuses_existing_clause_classification(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
                "21.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime is paid at 150%.",
                    "reason": "Explains the overtime rate.",
                },
            }
        }
        saved_classification = {
            "schema_version": "overtime-clause-classification-v1",
            "source_classification_file": "award_payment_classification.json",
            "included_categories_for_interpretation": [
                "Ordinary Hours Boundary",
                "Overtime Trigger",
            ],
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "clause_text": "Employees are paid overtime after ordinary hours.",
                    "explanation": "Directly creates overtime.",
                },
                {
                    "clause_number": "21.1",
                    "classification": "Overtime Consequence",
                    "clause_text": "Overtime is paid at 150%.",
                    "explanation": "Explains payment after overtime exists.",
                },
            ],
        }
        fake_client = FakeClient(
            [
                "## General\n\n"
                "- The hours will be overtime after ordinary hours. [20.1]",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "award_payment_classification.json"
            output_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_overtime_clause_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            classification_path.write_text(
                json.dumps(saved_classification),
                encoding="utf-8",
            )

            result = generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                classification_output_path=classification_path,
                client=fake_client,
            )

            archive_files = list(
                temp_path.glob("archive/award_overtime_clause_classification_*.json")
            )

        self.assertIn("## General", result)
        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertNotIn("text", fake_client.responses.calls[0])
        self.assertEqual(archive_files, [])


if __name__ == "__main__":
    unittest.main()
