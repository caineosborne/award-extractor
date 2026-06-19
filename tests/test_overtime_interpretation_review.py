import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_3_interpret_overtime import DEFAULT_MODEL as DEFAULT_CREATOR_MODEL
from src.script_3b_review_overtime_interpretation import (
    EVALUATOR_MODEL,
    build_creator_messages,
    build_evaluator_messages,
    creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation,
    parse_creator_update,
    revised_output_path_for_interpretation,
    review_overtime_interpretation,
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


class FakeCreatorClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class OvertimeInterpretationReviewTests(unittest.TestCase):
    def test_output_paths_for_interpretation(self):
        interpretation_path = Path(
            "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"
        )

        self.assertEqual(
            evaluator_feedback_path_for_interpretation(interpretation_path),
            Path(
                "data/processed/3_overtime_interpretations/feedback/"
                "MA000018_overtime_interpretation_evaluator_feedback.md"
            ),
        )
        self.assertEqual(
            creator_response_path_for_interpretation(interpretation_path),
            Path(
                "data/processed/3_overtime_interpretations/feedback/"
                "MA000018_overtime_interpretation_creator_response.md"
            ),
        )
        self.assertEqual(
            revised_output_path_for_interpretation(interpretation_path),
            Path(
                "data/processed/3_overtime_interpretations/"
                "MA000018_overtime_interpretation_revised.md"
            ),
        )

    def test_build_evaluator_messages_include_filtered_clauses_and_prompt(self):
        messages = build_evaluator_messages(
            interpretation_path="interpretation.md",
            interpretation_markdown="# Overtime Interpretation Working Document",
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
        self.assertIn("interpretation.md", user_prompt)
        self.assertIn("classification.json", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn("Overtime after ordinary hours.", user_prompt)
        self.assertIn("OVERTIME", user_prompt.upper())
        self.assertIn("# Overtime Interpretation Working Document", user_prompt)

    def test_build_creator_messages_include_feedback_and_filtered_clauses(self):
        messages = build_creator_messages(
            interpretation_path="interpretation.md",
            interpretation_markdown="# Original",
            classification_path="classification.json",
            overtime_clauses={
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            },
            evaluator_feedback_markdown="# Feedback\n\nAsk about shiftworkers.",
        )

        user_prompt = messages[1]["content"]

        self.assertIn("# Original", user_prompt)
        self.assertIn("# Feedback", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn("<creator_response>", user_prompt)
        self.assertIn("<revised_interpretation>", user_prompt)

    def test_parse_creator_update_splits_required_sections(self):
        creator_response, revised_interpretation = parse_creator_update(
            "<creator_response>\nAccepted one issue.\n</creator_response>\n"
            "<revised_interpretation>\n# Revised\n</revised_interpretation>"
        )

        self.assertEqual(creator_response, "Accepted one issue.")
        self.assertEqual(revised_interpretation, "# Revised")

    def test_review_overtime_interpretation_filters_context_and_writes_outputs(self):
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
            "# Overtime interpretation supervisor feedback\n\n"
            "## Questions for the creator\n\n"
            "- Should clause 20.1 be clearer?"
        )
        creator_client = FakeCreatorClient(
            "<creator_response>\n"
            "# Creator response\n\nAccepted the clause 20.1 clarity question.\n"
            "</creator_response>\n"
            "<revised_interpretation>\n"
            "# Overtime Interpretation Working Document\n\n"
            "Clause 20.1 has been clarified.\n"
            "</revised_interpretation>"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_payment_classification.json"

            interpretation_path.write_text(
                "# Overtime Interpretation Working Document",
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")

            artifacts = review_overtime_interpretation(
                interpretation_path=interpretation_path,
                classification_path=classification_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
            )

            evaluator_prompt = evaluator_client.chat.completions.calls[0]["messages"][1][
                "content"
            ]
            creator_prompt = creator_client.responses.calls[0]["input"][1]["content"]
            feedback_archive_files = list(
                (temp_path / "feedback" / "archive").glob(
                    "award_overtime_interpretation_evaluator_feedback_*.md"
                )
            )
            creator_archive_files = list(
                (temp_path / "feedback" / "archive").glob(
                    "award_overtime_interpretation_creator_response_*.md"
                )
            )
            revised_archive_files = list(
                (temp_path / "archive").glob(
                    "award_overtime_interpretation_revised_*.md"
                )
            )
            feedback_file_exists = artifacts.evaluator_feedback_path.exists()
            creator_response_file_exists = artifacts.creator_response_path.exists()
            revised_file_exists = artifacts.revised_interpretation_path.exists()

        self.assertEqual(
            evaluator_client.chat.completions.calls[0]["model"],
            EVALUATOR_MODEL,
        )
        self.assertEqual(
            creator_client.responses.calls[0]["model"],
            DEFAULT_CREATOR_MODEL,
        )
        self.assertIn('"20.1"', evaluator_prompt)
        self.assertIn('"20.1"', creator_prompt)
        self.assertNotIn('"30.1"', evaluator_prompt)
        self.assertNotIn('"30.1"', creator_prompt)
        self.assertTrue(feedback_file_exists)
        self.assertTrue(creator_response_file_exists)
        self.assertTrue(revised_file_exists)
        self.assertIn("Accepted the clause 20.1", artifacts.creator_response_markdown)
        self.assertIn("Clause 20.1 has been clarified", artifacts.revised_interpretation_markdown)
        self.assertEqual(len(feedback_archive_files), 1)
        self.assertEqual(len(creator_archive_files), 1)
        self.assertEqual(len(revised_archive_files), 1)


if __name__ == "__main__":
    unittest.main()
