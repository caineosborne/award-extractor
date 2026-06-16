import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.overtime_clause_generator import generate_overtime_clause_artifacts


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
    def test_generate_overtime_clause_artifacts_writes_two_markdown_files(self):
        data = {
            "classified_clauses": {
                "25.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime applies after 10 hours in a day.",
                    "reason": "Creates overtime entitlement.",
                }
            }
        }
        entitlements_markdown = (
            "# Overtime entitlements\n\n"
            "- Overtime - for working in excess of daily hours: Applies after 10 hours. [25.1]"
        )
        pseudocode_markdown = "# Overtime pseudocode\n\n- Allocate excess daily hours."
        fake_client = SequentialFakeClient([entitlements_markdown, pseudocode_markdown])

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            artifacts = generate_overtime_clause_artifacts(
                classification_path=input_path,
                model="gpt-5.4",
                client=fake_client,
            )

            entitlement_file = artifacts.entitlements_path.read_text(encoding="utf-8")
            pseudocode_file = artifacts.pseudocode_path.read_text(encoding="utf-8")

        self.assertEqual(entitlement_file, entitlements_markdown)
        self.assertEqual(pseudocode_file, pseudocode_markdown)
        self.assertEqual(fake_client.responses.calls[0]["model"], "gpt-5.4")
        self.assertEqual(fake_client.responses.calls[1]["model"], "gpt-5.4")


if __name__ == "__main__":
    unittest.main()
