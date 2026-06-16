import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.overtime_entitlement_summary import (
    DEFAULT_MODEL,
    build_messages,
    filter_overtime_clauses,
    output_path_for_classification,
    summarize_overtime_entitlements,
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


class OvertimeEntitlementSummaryTests(unittest.TestCase):
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
                Path("data/processed/MA000018_payment_classification.json")
            ),
            Path("data/processed/MA000018_overtime_entitlements.md"),
        )

    def test_build_messages_includes_glossary_and_clause_references(self):
        messages = build_messages(
            "classification.json",
            {"20.1": {"tags": ["Ordinary Hours & Overtime"], "text": "Paid overtime."}},
        )

        self.assertIn("ordinary hours", messages[0]["content"])
        self.assertIn("overtime", messages[0]["content"])
        self.assertIn("Overtime - for working in excess of fortnightly hours", messages[0]["content"])
        self.assertIn("Overtime - for working in excess of daily hours", messages[0]["content"])
        self.assertIn("Overtime - for working outside the span of hours", messages[0]["content"])
        self.assertIn("must begin exactly with these labels, in this order", messages[0]["content"])
        self.assertIn("Do not write \"All employees\"", messages[0]["content"])
        self.assertIn('"20.1"', messages[1]["content"])

    def test_summarize_overtime_entitlements_writes_markdown_with_mocked_client(self):
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
        fake_client = FakeClient("# Overtime\n- Overtime applies after ordinary hours. (20.1)")

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            output_path = Path(temp_dir) / "award_overtime_entitlements.md"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            result = summarize_overtime_entitlements(
                classification_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")

        self.assertEqual(result, written)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()
