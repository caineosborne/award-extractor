import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_4a_generate_overtime_clause import generate_overtime_clause_artifacts


class SequentialFakeResponses:
    def __init__(self, output_texts):
        self.output_texts = list(output_texts)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output_text = self.output_texts.pop(0)
        return SimpleNamespace(output_text=output_text)


class SequentialFakeClient:
    def __init__(self, output_texts):
        self.responses = SequentialFakeResponses(output_texts)


class OvertimeClauseGeneratorTests(unittest.TestCase):
    def test_generate_overtime_clause_artifacts_writes_interpretation_and_entitlements(self):
        data = {
            "classified_clauses": {
                "25.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime applies after 10 hours in a day.",
                    "reason": "Creates overtime entitlement.",
                }
            }
        }
        interpretation_markdown = (
            "## All Employees\n\n"
            "- The hours will be overtime after 10 hours in a day. [25.1]"
        )
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "25.1",
                        "classification": "Overtime Trigger",
                        "clause_text": "Overtime applies after 10 hours in a day.",
                        "explanation": "Directly creates overtime.",
                    }
                ]
            }
        )
        entitlements_markdown = (
            "# Overtime entitlements\n\n"
            "- Overtime - for working in excess of daily hours: Applies after 10 hours. [25.1]"
        )
        fake_client = SequentialFakeClient(
            [classification_json, interpretation_markdown, entitlements_markdown]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            artifacts = generate_overtime_clause_artifacts(
                classification_path=input_path,
                model="gpt-5.4",
                client=fake_client,
            )

            interpretation_file = artifacts.interpretation_path.read_text(encoding="utf-8")
            entitlement_file = artifacts.entitlements_path.read_text(encoding="utf-8")

        self.assertEqual(interpretation_file.strip(), interpretation_markdown)
        self.assertEqual(entitlement_file, entitlements_markdown)
        self.assertEqual(fake_client.responses.calls[0]["model"], "gpt-5.4")
        self.assertEqual(fake_client.responses.calls[1]["model"], "gpt-5.4")
        self.assertEqual(fake_client.responses.calls[2]["model"], "gpt-5.4")
        self.assertEqual(len(fake_client.responses.calls), 3)
        self.assertEqual(artifacts.interpretation_markdown.strip(), interpretation_markdown)


if __name__ == "__main__":
    unittest.main()
