import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_3_interpret_overtime import (
    DEFAULT_MODEL,
    build_messages,
    filter_overtime_clauses,
    generate_overtime_interpretation,
    output_path_for_classification,
)


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


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

    def test_build_messages_includes_required_working_document_sections(self):
        messages = build_messages(
            "classification.json",
            {"20.1": {"tags": ["Ordinary Hours & Overtime"], "text": "Paid overtime."}},
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("# Overtime Interpretation Working Document", system_prompt)
        self.assertIn("## Relevant Rules", system_prompt)
        self.assertIn("## When does overtime occur?", system_prompt)
        self.assertIn("## What happens when overtime occurs?", system_prompt)
        self.assertIn("## What extra consequences exist?", system_prompt)
        self.assertIn("## What data is required?", system_prompt)
        self.assertIn("## What assumptions are being made?", system_prompt)
        self.assertIn("Ordinary Hours & Overtime", user_prompt)
        self.assertIn('"20.1"', user_prompt)

    def test_generate_overtime_interpretation_writes_markdown_with_mocked_client(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
                "30.1": {"tags": ["Penalty"], "text": "Weekend penalty."},
            }
        }
        fake_client = FakeClient(
            "# Overtime Interpretation Working Document\n\n"
            "## When does overtime occur?\n\n"
            "Overtime applies after ordinary hours. [20.1]"
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
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_interpretation_*.md")
            )

        self.assertEqual(result, written)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn('"20.1"', fake_client.responses.calls[0]["input"][1]["content"])
        self.assertNotIn('"30.1"', fake_client.responses.calls[0]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
