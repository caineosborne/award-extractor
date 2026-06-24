import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_4a_summarize_overtime import DEFAULT_MODEL as DEFAULT_CREATOR_MODEL
from src.script_4b_review_overtime_entitlements import (
    DEFAULT_FORMATTER_MODEL,
    EVALUATOR_MODEL,
    OvertimeEntitlementReviewError,
    build_accuracy_evaluator_messages,
    build_formatting_messages,
    build_update_messages,
    final_answer_path_for_entitlements,
    initial_answer_path_for_entitlements,
    output_path_for_classification,
    parse_updated_answer,
    review_feedback_path_for_entitlements,
    review_overtime_entitlements,
    updated_answer_path_for_entitlements,
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


class FakeEvaluatorClient:
    def __init__(self, output_text):
        self.chat = FakeChat(output_text)


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeOpenAIClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class OvertimeEntitlementReviewTests(unittest.TestCase):
    def test_output_paths_for_entitlements(self):
        entitlements_path = Path(
            "data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md"
        )

        self.assertEqual(
            initial_answer_path_for_entitlements(entitlements_path),
            Path(
                "data/processed/4a_overtime_entitlements/"
                "MA000018_overtime_entitlements_initial_answer.md"
            ),
        )
        self.assertEqual(
            review_feedback_path_for_entitlements(entitlements_path),
            Path(
                "data/processed/4a_overtime_entitlements/"
                "MA000018_overtime_entitlements_review_feedback.md"
            ),
        )
        self.assertEqual(
            updated_answer_path_for_entitlements(entitlements_path),
            Path(
                "data/processed/4a_overtime_entitlements/"
                "MA000018_overtime_entitlements_updated_answer.md"
            ),
        )
        self.assertEqual(
            final_answer_path_for_entitlements(entitlements_path),
            Path(
                "data/processed/4a_overtime_entitlements/"
                "MA000018_overtime_entitlements_final.md"
            ),
        )

    def test_output_path_for_classification_returns_final_entitlements_path(self):
        self.assertEqual(
            output_path_for_classification(
                Path(
                    "data/processed/2_payment_clause_identifier/"
                    "MA000018_payment_classification.json"
                )
            ),
            Path(
                "data/processed/4a_overtime_entitlements/"
                "MA000018_overtime_entitlements_final.md"
            ),
        )

    def test_accuracy_evaluator_messages_include_source_context(self):
        messages = build_accuracy_evaluator_messages(
            entitlements_path="entitlements.md",
            entitlements_markdown="# Source Rules\n\nOvertime after 38 hours.",
            interpretation_path="interpretation.md",
            interpretation_markdown="# Interpretation\n\nClause 20.1 applies.",
            classification_path="classification.json",
            overtime_clauses={
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            },
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("supervisor", system_prompt)
        self.assertIn("accuracy", system_prompt)
        self.assertIn("entitlements.md", user_prompt)
        self.assertIn("interpretation.md", user_prompt)
        self.assertIn("classification.json", user_prompt)
        self.assertIn("# Source Rules", user_prompt)
        self.assertIn("# Interpretation", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn("The entitlement document was generated using this system prompt", user_prompt)

    def test_update_messages_include_feedback_and_required_tag(self):
        messages = build_update_messages(
            entitlements_path="entitlements.md",
            entitlements_markdown="# Original 4A",
            interpretation_path="interpretation.md",
            interpretation_markdown="# Interpretation",
            classification_path="classification.json",
            overtime_clauses={
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            },
            review_feedback_markdown="# Feedback\n\nMissing daily trigger.",
        )

        user_prompt = messages[1]["content"]

        self.assertIn("# Original 4A", user_prompt)
        self.assertIn("# Feedback", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn("<updated_answer>", user_prompt)

    def test_formatting_messages_exclude_source_context(self):
        messages = build_formatting_messages(
            "# Updated\n\nClause 20.1: overtime after ordinary hours."
        )

        combined_prompt = "\n".join(message["content"] for message in messages)

        self.assertIn("# Updated", combined_prompt)
        self.assertIn("wording and formatting only", combined_prompt)
        self.assertIn("Use only the supplied markdown", combined_prompt)
        self.assertNotIn("Filtered payment classification source", combined_prompt)
        self.assertNotIn("Overtime interpretation source", combined_prompt)
        self.assertNotIn("Only these clauses were tagged", combined_prompt)

    def test_parse_updated_answer_splits_required_section(self):
        updated_answer = parse_updated_answer(
            "<updated_answer>\n# Updated\n\nDaily trigger clarified.\n</updated_answer>"
        )

        self.assertEqual(updated_answer, "# Updated\n\nDaily trigger clarified.")

    def test_parse_updated_answer_accepts_plain_markdown(self):
        updated_answer = parse_updated_answer(
            "```markdown\n# Updated entitlement\n\nDaily trigger clarified.\n```"
        )

        self.assertEqual(updated_answer, "# Updated entitlement\n\nDaily trigger clarified.")

    def test_review_overtime_entitlements_writes_all_outputs(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                },
                "30.1": {
                    "tags": ["Penalty"],
                    "text": "Weekend penalty.",
                },
            }
        }
        evaluator_client = FakeEvaluatorClient(
            "# Overtime entitlement review feedback\n\n"
            "## Accuracy and completeness issues\n\n"
            "- Check daily overtime trigger."
        )
        creator_client = FakeOpenAIClient(
            "<updated_answer>\n"
            "# Updated entitlement\n\n"
            "Clause 20.1 daily overtime trigger clarified.\n"
            "</updated_answer>"
        )
        formatter_client = FakeOpenAIClient(
            "# Final entitlement\n\n"
            "- Clause 20.1 daily overtime trigger clarified."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entitlements_path = temp_path / "award_overtime_entitlements.md"
            classification_path = temp_path / "award_payment_classification.json"
            interpretation_path = temp_path / "award_overtime_interpretation_revised.md"

            entitlements_path.write_text(
                "# Source Rules\n\nOvertime after ordinary hours.",
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            interpretation_path.write_text(
                "# Overtime Interpretation\n\nClause 20.1 applies.",
                encoding="utf-8",
            )

            artifacts = review_overtime_entitlements(
                entitlements_path=entitlements_path,
                classification_path=classification_path,
                interpretation_path=interpretation_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
                formatter_client=formatter_client,
            )

            evaluator_prompt = evaluator_client.chat.completions.calls[0]["messages"][1][
                "content"
            ]
            creator_prompt = creator_client.responses.calls[0]["input"][1]["content"]
            formatter_prompt = formatter_client.responses.calls[0]["input"][1]["content"]
            archive_files = list((temp_path / "archive").glob("*.md"))

            initial_file_exists = artifacts.initial_answer_path.exists()
            feedback_file_exists = artifacts.review_feedback_path.exists()
            updated_file_exists = artifacts.updated_answer_path.exists()
            final_file_exists = artifacts.final_answer_path.exists()

        self.assertEqual(
            evaluator_client.chat.completions.calls[0]["model"],
            EVALUATOR_MODEL,
        )
        self.assertEqual(
            creator_client.responses.calls[0]["model"],
            DEFAULT_CREATOR_MODEL,
        )
        self.assertEqual(
            formatter_client.responses.calls[0]["model"],
            DEFAULT_FORMATTER_MODEL,
        )
        self.assertIn('"20.1"', evaluator_prompt)
        self.assertIn('"20.1"', creator_prompt)
        self.assertNotIn('"30.1"', evaluator_prompt)
        self.assertNotIn('"30.1"', creator_prompt)
        self.assertIn("# Updated entitlement", formatter_prompt)
        self.assertNotIn("classification.json", formatter_prompt)
        self.assertTrue(initial_file_exists)
        self.assertTrue(feedback_file_exists)
        self.assertTrue(updated_file_exists)
        self.assertTrue(final_file_exists)
        self.assertIn("daily overtime trigger", artifacts.updated_answer_markdown)
        self.assertIn("Final entitlement", artifacts.final_answer_markdown)
        self.assertEqual(len(archive_files), 4)

    def test_review_overtime_entitlements_keeps_initial_and_feedback_when_creator_fails(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                },
            }
        }
        evaluator_client = FakeEvaluatorClient(
            "# Overtime entitlement review feedback\n\n"
            "## Accuracy and completeness issues\n\n"
            "- Check daily overtime trigger."
        )
        creator_client = FakeOpenAIClient("")
        formatter_client = FakeOpenAIClient("# Final should not be called")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            entitlements_path = temp_path / "award_overtime_entitlements.md"
            classification_path = temp_path / "award_payment_classification.json"
            interpretation_path = temp_path / "award_overtime_interpretation_revised.md"

            entitlements_path.write_text(
                "# Source Rules\n\nOvertime after ordinary hours.",
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            interpretation_path.write_text(
                "# Overtime Interpretation\n\nClause 20.1 applies.",
                encoding="utf-8",
            )

            with self.assertRaises(OvertimeEntitlementReviewError):
                review_overtime_entitlements(
                    entitlements_path=entitlements_path,
                    classification_path=classification_path,
                    interpretation_path=interpretation_path,
                    evaluator_client=evaluator_client,
                    creator_client=creator_client,
                    formatter_client=formatter_client,
                )

            initial_path = temp_path / "award_overtime_entitlements_initial_answer.md"
            feedback_path = temp_path / "award_overtime_entitlements_review_feedback.md"
            updated_path = temp_path / "award_overtime_entitlements_updated_answer.md"
            final_path = temp_path / "award_overtime_entitlements_final.md"
            archive_files = list((temp_path / "archive").glob("*.md"))

            initial_file_exists = initial_path.exists()
            feedback_file_exists = feedback_path.exists()
            updated_file_exists = updated_path.exists()
            final_file_exists = final_path.exists()

        self.assertTrue(initial_file_exists)
        self.assertTrue(feedback_file_exists)
        self.assertFalse(updated_file_exists)
        self.assertFalse(final_file_exists)
        self.assertEqual(len(archive_files), 2)


if __name__ == "__main__":
    unittest.main()
