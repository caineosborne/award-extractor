import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.overtime_quality_evaluator import (
    DEFAULT_MODEL,
    build_messages,
    evaluate_overtime_artifact_quality,
    output_path_for_pseudocode,
)


class FakeCompletions:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.output_text)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeChat:
    def __init__(self, output_text):
        self.completions = FakeCompletions(output_text)


class FakeClient:
    def __init__(self, output_text):
        self.chat = FakeChat(output_text)


class OvertimeQualityEvaluatorTests(unittest.TestCase):
    def test_output_path_for_pseudocode(self):
        self.assertEqual(
            output_path_for_pseudocode(
                Path("data/processed/overtime_entitlements/MA000018_core_overtime_pseudocode.md")
            ),
            Path("data/processed/overtime_review/MA000018_overtime_quality_review.md"),
        )

    def test_build_messages_include_artifacts_and_generation_prompts(self):
        messages = build_messages(
            classification_path="classification.json",
            classification_data={
                "classified_clauses": {
                    "20.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime after ordinary hours.",
                    }
                }
            },
            entitlements_path="entitlements.md",
            entitlements_markdown="# Overtime entitlements",
            pseudocode_path="pseudocode.md",
            pseudocode_markdown="# Overtime pseudocode",
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("quality reviewer", system_prompt)
        self.assertIn("classification.json", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn("# Overtime entitlements", user_prompt)
        self.assertIn("# Overtime pseudocode", user_prompt)
        self.assertIn("The overtime entitlement markdown was generated using this system prompt", user_prompt)
        self.assertIn("The core overtime pseudocode markdown was generated using this system prompt", user_prompt)
        self.assertIn("Required additional inputs", user_prompt)

    def test_evaluate_overtime_artifact_quality_writes_markdown_with_mocked_client(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                    "reason": "Creates an overtime rule.",
                }
            }
        }
        fake_client = FakeClient("# Overtime artifact quality review\n\nNo issues found.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            classification_path = temp_path / "award_payment_classification.json"
            entitlements_path = temp_path / "award_overtime_entitlements.md"
            pseudocode_path = temp_path / "award_core_overtime_pseudocode.md"
            output_path = temp_path / "award_overtime_quality_review.md"

            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            entitlements_path.write_text("# Overtime entitlements", encoding="utf-8")
            pseudocode_path.write_text("# Overtime pseudocode", encoding="utf-8")

            result = evaluate_overtime_artifact_quality(
                classification_path=classification_path,
                entitlements_path=entitlements_path,
                pseudocode_path=pseudocode_path,
                output_path=output_path,
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_quality_review_*.md")
            )

        self.assertEqual(result, written)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(fake_client.chat.completions.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn(
            "# Overtime entitlements",
            fake_client.chat.completions.calls[0]["messages"][1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
