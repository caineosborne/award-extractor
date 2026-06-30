import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.common.overtime_rules import OvertimeRule, apply_review_decisions
from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET
from src.script_3_interpret_overtime import DEFAULT_MODEL as DEFAULT_CREATOR_MODEL
from src.script_3b_review_overtime_interpretation import (
    EVALUATOR_MODEL,
    build_relevant_clause_excerpt_markdown,
    build_creator_messages,
    build_evaluator_messages,
    creator_review_json_schema,
    creator_response_path_for_interpretation,
    evaluator_feedback_json_schema,
    evaluator_feedback_path_for_interpretation,
    extract_json_object_from_text,
    fallback_evaluator_feedback_markdown,
    fallback_creator_response_markdown,
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
        self.responses = FakeResponses(output_text)


class FakeResponses:
    def __init__(self, output_text):
        if isinstance(output_text, list):
            self.output_texts = list(output_text)
        else:
            self.output_texts = [output_text]
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_texts.pop(0))


class FakeCreatorClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class FakeResponseApiEvaluatorResponses:
    def __init__(self, response_payload):
        self.response_payload = response_payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response_payload


class FakeResponseApiEvaluatorClient:
    def __init__(self, response_payload):
        self.responses = FakeResponseApiEvaluatorResponses(response_payload)


class OvertimeInterpretationReviewTests(unittest.TestCase):
    def test_review_schemas_include_tracked_rule_arrays(self):
        self.assertEqual(
            evaluator_feedback_json_schema()["properties"]["new_rules"]["type"],
            "array",
        )
        self.assertEqual(
            creator_review_json_schema()["properties"]["new_rule_reviews"]["type"],
            "array",
        )

    def test_extract_json_object_from_text_accepts_fenced_json(self):
        parsed_data = extract_json_object_from_text(
            "```json\n"
            '{"summary_markdown": "# Feedback", "rule_reviews": [], "new_rules": []}\n'
            "```"
        )

        self.assertEqual(parsed_data["summary_markdown"], "# Feedback")

    def test_extract_json_object_from_text_repairs_multiline_string_values(self):
        parsed_data = extract_json_object_from_text(
            '{\n'
            '"summary_markdown": "# Feedback\\n\\nLine one.\nLine two.",\n'
            '"rule_reviews": [],\n'
            '"new_rules": []\n'
            "}"
        )

        self.assertIn("Line two.", parsed_data["summary_markdown"])

    def test_fallback_creator_response_markdown_renders_decision_record_when_json_is_present(self):
        markdown = fallback_creator_response_markdown(
            validation_error="Rule cannot be removed.",
            creator_output_text=json.dumps(
                {
                    "decision_record_markdown": "# Decision record\n\nAccepted one point.",
                    "rule_updates": [{"rule_id": "rule-1", "decision": "remove", "reason": "No."}],
                    "new_rule_reviews": [],
                }
            ),
        )

        self.assertIn("## Creator decision record", markdown)
        self.assertIn("# Decision record", markdown)
        self.assertIn("- Rule updates returned: 1", markdown)
        self.assertIn("- Evaluator-proposed new rule decisions returned: 0", markdown)
        self.assertIn("```json", markdown)

    def test_fallback_evaluator_feedback_markdown_renders_clean_manual_review_record(self):
        markdown = fallback_evaluator_feedback_markdown(
            validation_error="Expecting ',' delimiter",
            evaluator_output_text='{"summary_markdown":"Overall view","rule_reviews":[',
        )

        self.assertIn("# Evaluator feedback validation failure", markdown)
        self.assertIn("## Validation error", markdown)
        self.assertIn("## Raw evaluator response", markdown)
        self.assertIn("```text", markdown)

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
            interpretation_markdown="## All Employees",
            classification_path="classification.json",
            payment_classification={
                "classified_clauses": {
                    "20.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime after ordinary hours.",
                    },
                    "30.1": {
                        "tags": ["Other Payment"],
                        "text": "Possible missed overtime creation clause.",
                    },
                }
            },
            overtime_clause_classification_path="overtime_clause_classification.json",
            overtime_clause_classification={
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "explanation": "Directly creates overtime.",
                    }
                ]
            },
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("supervisor", system_prompt)
        self.assertIn("What circumstances increase total overtime hours?", system_prompt)
        self.assertIn("Presentation issues", system_prompt)
        self.assertIn("duplicate bullets", system_prompt)
        self.assertIn("clauses in the Script 3 classification", system_prompt)
        self.assertIn("interpretation.md", user_prompt)
        self.assertIn("classification.json", user_prompt)
        self.assertIn("overtime_clause_classification.json", user_prompt)
        self.assertIn('"20.1"', user_prompt)
        self.assertIn('"30.1"', user_prompt)
        self.assertIn("Overtime after ordinary hours.", user_prompt)
        self.assertIn("Possible missed overtime creation clause.", user_prompt)
        self.assertIn("Check both Script 3 steps", user_prompt)
        self.assertIn("Also review presentation", user_prompt)
        self.assertIn("avoid dragging in materially out-of-scope content", user_prompt)
        self.assertIn("Script 3 creator prompt context", user_prompt)
        self.assertIn("clause_classification_messages", user_prompt)
        self.assertIn("interpretation_messages", user_prompt)
        self.assertIn("Using the Ordinary Hours & Overtime clauses below", user_prompt)
        self.assertIn("## All Employees", user_prompt)

    def test_build_creator_messages_include_feedback_and_filtered_clauses(self):
        messages = build_creator_messages(
            interpretation_path="interpretation.md",
            interpretation_markdown="# Original",
            classification_path="classification.json",
            payment_classification={
                "classified_clauses": {
                    "20.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime after ordinary hours.",
                    },
                    "30.1": {
                        "tags": ["Other Payment"],
                        "text": "Possible missed overtime creation clause.",
                    },
                }
            },
            overtime_clause_classification_path="overtime_clause_classification.json",
            overtime_clause_classification={
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "explanation": "Directly creates overtime.",
                    }
                ]
            },
            evaluator_feedback_markdown="# Feedback\n\nAsk whether clause 20.1 should mention shiftworkers.",
            evaluator_feedback_data={
                "summary_markdown": "# Feedback\n\nAsk whether clause 20.1 should mention shiftworkers.",
                "rule_reviews": [
                    {
                        "rule_id": "all-employees_001",
                        "recommendation": "modify",
                        "rationale": "Clarify wording.",
                    }
                ],
                "new_rules": [],
            },
        )

        user_prompt = messages[1]["content"]

        self.assertIn("# Original", user_prompt)
        self.assertIn("# Feedback", user_prompt)
        self.assertIn("Authoritative evaluator review action pack", user_prompt)
        self.assertIn('"authoritative_review_contract"', user_prompt)
        self.assertIn('"rule_id": "all-employees_001"', user_prompt)
        self.assertIn("## Clause 20.1", user_prompt)
        self.assertNotIn('"30.1"', user_prompt)
        self.assertIn("What circumstances increase total overtime hours?", user_prompt)
        self.assertIn("accuracy", user_prompt)
        self.assertIn("presentation", user_prompt)
        self.assertIn("dedicated arrangement section", user_prompt)
        self.assertIn("still state the employee type affected", user_prompt)
        self.assertIn("Keep one overtime circumstance per bullet", user_prompt)
        self.assertIn("Keep clause references in the revised markdown bullets", user_prompt)
        self.assertIn("If a clause uses general wording such as \"employee\"", user_prompt)
        self.assertIn("Relevant clause excerpts", user_prompt)
        self.assertIn("Evaluator structured review JSON", user_prompt)
        self.assertNotIn("Script 3 creator prompt context", user_prompt)
        self.assertNotIn("clause_classification_messages", user_prompt)
        self.assertNotIn("interpretation_messages", user_prompt)
        self.assertIn("<creator_response>", user_prompt)
        self.assertIn("<revised_interpretation>", user_prompt)

    def test_build_evaluator_messages_support_consequence_ruleset_focus(self):
        messages = build_evaluator_messages(
            interpretation_path="award_overtime_consequence_ruleset.md",
            interpretation_markdown="## Overtime rates",
            classification_path="classification.json",
            payment_classification={
                "classified_clauses": {
                    "23.2": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime is paid at 150% for the first 2 hours and 200% after that.",
                    },
                }
            },
            overtime_clause_classification_path="award_overtime_consequence_clause_classification.json",
            overtime_clause_classification={
                "ruleset_key": OVERTIME_CONSEQUENCE_RULESET,
                "clauses": [
                    {
                        "clause_number": "23.2",
                        "classification": "Overtime Consequence",
                        "classifications": ["Overtime Consequence"],
                        "explanation": "Defines overtime rates after overtime already exists.",
                        "clause_text": "Overtime is paid at 150% for the first 2 hours and 200% after that.",
                    }
                ],
            },
            ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn(
            "What overtime consequence applies once hours are already overtime?",
            system_prompt,
        )
        self.assertIn("Review this overtime consequence working document.", user_prompt)
        self.assertIn("relevant to the selected ruleset", user_prompt)

    def test_build_creator_messages_prioritises_structured_review_clauses(self):
        messages = build_creator_messages(
            interpretation_path="interpretation.md",
            interpretation_markdown="# Original\n\n- Base rule. [20.1]",
            classification_path="classification.json",
            payment_classification={
                "classified_clauses": {
                    "20.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime after ordinary hours.",
                    },
                    "21.5": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Interrupted meal breaks create overtime.",
                    },
                }
            },
            overtime_clause_classification_path="overtime_clause_classification.json",
            overtime_clause_classification={
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "classifications": ["Overtime Trigger"],
                        "explanation": "Directly creates overtime.",
                        "clause_text": "Overtime after ordinary hours.",
                    },
                    {
                        "clause_number": "21.5",
                        "classification": "Overtime Trigger",
                        "classifications": ["Overtime Trigger"],
                        "explanation": "Creates overtime for interrupted meal breaks.",
                        "clause_text": "Interrupted meal breaks create overtime.",
                    },
                ]
            },
            evaluator_feedback_markdown="# Feedback\n\nGeneral concern with wording only.",
            evaluator_feedback_data={
                "summary_markdown": "# Feedback\n\nGeneral concern with wording only.",
                "rule_reviews": [
                    {
                        "rule_id": "all-employees_001",
                        "recommendation": "modify",
                        "rationale": "Clarify the existing rule.",
                    }
                ],
                "new_rules": [
                    {
                        "rule_id": "all-employees_002",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time", "part-time", "casual"],
                        "clause_references": ["21.5"],
                        "rule_markdown": "- If a meal break is interrupted, the time becomes overtime. [21.5]",
                        "rule_plain_text": "If a meal break is interrupted, the time becomes overtime.",
                        "source_clause_numbers": ["21.5"],
                        "source_classifications": ["Overtime Trigger"],
                    }
                ],
            },
            original_rules_artifact={
                "rules": [
                    {
                        "rule_id": "all-employees_001",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time", "part-time", "casual"],
                        "clause_references": ["20.1"],
                        "rule_markdown": "- Base rule. [20.1]",
                        "rule_plain_text": "Base rule.",
                        "source_clause_numbers": ["20.1"],
                        "source_classifications": ["Overtime Trigger"],
                    }
                ]
            },
        )

        user_prompt = messages[1]["content"]

        self.assertIn("## Clause 20.1", user_prompt)
        self.assertIn("## Clause 21.5", user_prompt)

    def test_build_relevant_clause_excerpt_markdown_uses_referenced_clauses_only(self):
        clause_excerpt_markdown = build_relevant_clause_excerpt_markdown(
            interpretation_markdown="# Original\n\n- Clause 20.1 applies.",
            payment_classification={
                "classified_clauses": {
                    "20.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Overtime after ordinary hours.",
                    },
                    "30.1": {
                        "tags": ["Other Payment"],
                        "text": "Possible missed overtime creation clause.",
                    },
                }
            },
            overtime_clause_classification={
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "classifications": ["Overtime Trigger"],
                        "explanation": "Directly creates overtime.",
                        "clause_text": "Overtime after ordinary hours.",
                    }
                ]
            },
            evaluator_feedback_markdown="# Feedback\n\nPlease revisit clause 20.1.",
        )

        self.assertIn("## Clause 20.1", clause_excerpt_markdown)
        self.assertNotIn("## Clause 30.1", clause_excerpt_markdown)

    def test_parse_creator_update_splits_required_sections(self):
        creator_response, revised_interpretation = parse_creator_update(
            "<creator_response>\nAccepted one issue.\n</creator_response>\n"
            "<revised_interpretation>\n# Revised\n</revised_interpretation>"
        )

        self.assertEqual(creator_response, "Accepted one issue.")
        self.assertEqual(revised_interpretation, "# Revised")

    def test_apply_review_decisions_allows_partial_modified_rule_payload(self):
        original_rule = OvertimeRule(
            rule_id="all-employees_001",
            section_heading="All employees",
            employee_scope=("full-time", "part-time", "casual"),
            clause_references=("20.1",),
            rule_markdown="- Original rule. [clause 20.1]",
            rule_plain_text="Original rule.",
            source_clause_numbers=("20.1",),
            source_classifications=("Overtime Trigger",),
        )

        result = apply_review_decisions(
            original_rules=[original_rule],
            evaluator_feedback={
                "rule_reviews": [
                    {
                        "rule_id": "all-employees_001",
                        "recommendation": "modify",
                        "rationale": "Clarify wording.",
                    }
                ]
            },
            creator_decision_data={
                "decision_record_markdown": "# Decision record",
                "rule_updates": [
                    {
                        "rule_id": "all-employees_001",
                        "decision": "modify",
                        "reason": "Clarified wording.",
                        "updated_rule": {
                            "rule_markdown": "- Updated rule. [clause 20.1]",
                            "rule_plain_text": "Updated rule.",
                        },
                    }
                ],
                "new_rule_reviews": [],
            },
        )

        updated_rule = result["rules"][0]
        self.assertEqual(updated_rule.rule_id, "all-employees_001")
        self.assertEqual(updated_rule.section_heading, "All employees")
        self.assertEqual(updated_rule.rule_markdown, "- Updated rule. [clause 20.1]")

    def test_apply_review_decisions_preserves_rule_when_modify_has_no_payload(self):
        original_rule = OvertimeRule(
            rule_id="all-employees_001",
            section_heading="All employees",
            employee_scope=("full-time", "part-time", "casual"),
            clause_references=("20.1",),
            rule_markdown="- Original rule. [clause 20.1]",
            rule_plain_text="Original rule.",
            source_clause_numbers=("20.1",),
            source_classifications=("Overtime Trigger",),
        )

        result = apply_review_decisions(
            original_rules=[original_rule],
            evaluator_feedback={
                "rule_reviews": [
                    {
                        "rule_id": "all-employees_001",
                        "recommendation": "modify",
                        "rationale": "Clarify wording.",
                    }
                ]
            },
            creator_decision_data={
                "decision_record_markdown": "# Decision record",
                "rule_updates": [
                    {
                        "rule_id": "all-employees_001",
                        "decision": "modify",
                        "reason": "Clarified wording.",
                    }
                ],
                "new_rule_reviews": [],
            },
        )

        preserved_rule = result["rules"][0]
        self.assertEqual(preserved_rule.rule_id, "all-employees_001")
        self.assertEqual(preserved_rule.rule_markdown, "- Original rule. [clause 20.1]")
        self.assertEqual(preserved_rule.review_status, "confirmed")

    def test_apply_review_decisions_only_adds_new_rules_when_evaluator_and_creator_agree(self):
        original_rule = OvertimeRule(
            rule_id="all-employees_001",
            section_heading="All employees",
            employee_scope=("full-time", "part-time", "casual"),
            clause_references=("23.1(a)",),
            rule_markdown="- Work outside ordinary hours is overtime. [23.1(a)]",
            rule_plain_text="Work outside ordinary hours is overtime.",
            source_clause_numbers=("23.1(a)",),
            source_classifications=("Overtime Trigger",),
        )

        result = apply_review_decisions(
            original_rules=[original_rule],
            evaluator_feedback={
                "rule_reviews": [
                    {
                        "rule_id": "all-employees_001",
                        "recommendation": "modify",
                        "rationale": "Split the rule.",
                    }
                ],
                "new_rules": [
                    {
                        "rule_id": "all-employees_002",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time", "part-time", "casual"],
                        "clause_references": ["22.1(b)"],
                        "rule_markdown": "- If a meal break is interrupted by the employer, overtime is paid until an uninterrupted break is taken. [22.1(b)]",
                        "rule_plain_text": "If a meal break is interrupted by the employer, overtime is paid until an uninterrupted break is taken.",
                        "source_clause_numbers": ["22.1(b)"],
                        "source_classifications": ["Overtime Trigger"],
                    }
                ],
            },
            creator_decision_data={
                "decision_record_markdown": "# Decision record",
                "rule_updates": [
                    {
                        "rule_id": "all-employees_001",
                        "decision": "modify",
                        "reason": "Keep the general trigger and add atomic rules.",
                        "updated_rule": {
                            "rule_markdown": "- Work outside an employee's ordinary hours is overtime. [23.1(a)]",
                            "rule_plain_text": "Work outside an employee's ordinary hours is overtime.",
                        },
                    }
                ],
                "new_rule_reviews": [
                    {
                        "rule_id": "all-employees_002",
                        "decision": "accept",
                        "reason": "Add the omitted meal-break overtime trigger.",
                        "updated_rule": None,
                    }
                ],
            },
        )

        self.assertEqual(len(result["rules"]), 2)
        self.assertEqual(result["rules"][1].rule_id, "all-employees_002")

    def test_review_overtime_interpretation_filters_context_and_writes_outputs(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                },
                "30.1": {
                    "tags": ["Other Payment"],
                    "text": "Possible missed overtime creation clause.",
                },
            }
        }
        overtime_clause_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger", "Overtime Consequence"],
                    "explanation": "Directly creates overtime.",
                    "clause_text": "Overtime after ordinary hours.",
                }
            ],
        }
        evaluator_client = FakeEvaluatorClient(
            json.dumps(
                {
                    "summary_markdown": (
                        "# Overtime interpretation supervisor feedback\n\n"
                        "## Questions for the creator\n\n"
                        "- Should clause 20.1 be clearer?"
                    ),
                    "rule_reviews": [
                        {
                            "rule_id": "all-employees_001",
                            "recommendation": "modify",
                            "rationale": "Clarify clause 20.1.",
                        }
                    ],
                    "new_rules": [],
                }
            )
        )
        creator_client = FakeCreatorClient(
            json.dumps(
                {
                    "decision_record_markdown": (
                        "# Creator response\n\nAccepted the clause 20.1 clarity question."
                    ),
                    "rule_updates": [
                        {
                            "rule_id": "all-employees_001",
                            "decision": "modify",
                            "reason": "Clarified clause 20.1.",
                            "updated_rule": {
                                "rule_markdown": "- Clause 20.1 has been clarified. [20.1]",
                                "rule_plain_text": "Clause 20.1 has been clarified.",
                            },
                        }
                    ],
                    "new_rule_reviews": [],
                }
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_payment_classification.json"
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )

            interpretation_path.write_text(
                "## All Employees",
                encoding="utf-8",
            )
            interpretation_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "schema_version": "overtime-rules-v1",
                        "source_classification_file": "award_payment_classification.json",
                        "source_clause_classification_file": "award_overtime_clause_classification.json",
                        "rendered_markdown": "## All Employees\n\n- Clause 20.1 is overtime. [20.1]\n",
                        "rules": [
                            {
                                "rule_id": "all-employees_001",
                                "section_heading": "All Employees",
                                "employee_scope": ["full-time", "part-time", "casual"],
                                "clause_references": ["20.1"],
                                "rule_markdown": "- Clause 20.1 is overtime. [20.1]",
                                "rule_plain_text": "Clause 20.1 is overtime.",
                                "source_clause_numbers": ["20.1"],
                                "source_classifications": ["Overtime Trigger"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            artifacts = review_overtime_interpretation(
                interpretation_path=interpretation_path,
                classification_path=classification_path,
                overtime_clause_classification_path=overtime_clause_classification_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
                inter_call_delay_seconds=0,
            )

            evaluator_prompt = evaluator_client.responses.calls[0]["input"][1][
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
            evaluator_client.responses.calls[0]["model"],
            EVALUATOR_MODEL,
        )
        self.assertEqual(
            creator_client.responses.calls[0]["model"],
            DEFAULT_CREATOR_MODEL,
        )
        self.assertEqual(
            evaluator_client.responses.calls[0]["text"]["format"]["type"],
            "json_schema",
        )
        self.assertEqual(
            creator_client.responses.calls[0]["text"]["format"]["type"],
            "json_schema",
        )
        self.assertIn('"20.1"', evaluator_prompt)
        self.assertIn('"30.1"', evaluator_prompt)
        self.assertIn("## Clause 20.1", creator_prompt)
        self.assertNotIn('"30.1"', creator_prompt)
        self.assertTrue(feedback_file_exists)
        self.assertTrue(creator_response_file_exists)
        self.assertTrue(revised_file_exists)
        self.assertIn("Accepted the clause 20.1", artifacts.creator_response_markdown)
        self.assertIn("Clause 20.1 has been clarified", artifacts.revised_interpretation_markdown)
        self.assertEqual(len(feedback_archive_files), 1)
        self.assertEqual(len(creator_archive_files), 1)
        self.assertEqual(len(revised_archive_files), 1)

    def test_review_overtime_interpretation_logs_token_budget_and_delay(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            }
        }
        overtime_clause_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "explanation": "Directly creates overtime.",
                    "clause_text": "Overtime after ordinary hours.",
                }
            ],
        }
        evaluator_client = FakeEvaluatorClient(
            json.dumps(
                {
                    "summary_markdown": "# Feedback\n\nReview clause 20.1.",
                    "rule_reviews": [
                        {
                            "rule_id": "all-employees_001",
                            "recommendation": "keep",
                            "rationale": "Review clause 20.1.",
                        }
                    ],
                    "new_rules": [],
                }
            )
        )
        creator_client = FakeCreatorClient(
            json.dumps(
                {
                    "decision_record_markdown": "# Creator response\n\nAccepted.",
                    "rule_updates": [
                        {
                            "rule_id": "all-employees_001",
                            "decision": "keep",
                            "reason": "Accepted.",
                        }
                    ],
                    "new_rule_reviews": [],
                }
            )
        )
        status_messages = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_payment_classification.json"
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )
            interpretation_path.write_text("## All Employees", encoding="utf-8")
            interpretation_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "schema_version": "overtime-rules-v1",
                        "source_classification_file": "award_payment_classification.json",
                        "source_clause_classification_file": "award_overtime_clause_classification.json",
                        "rendered_markdown": "## All Employees\n\n- Clause 20.1 is overtime. [20.1]\n",
                        "rules": [
                            {
                                "rule_id": "all-employees_001",
                                "section_heading": "All Employees",
                                "employee_scope": ["full-time", "part-time", "casual"],
                                "clause_references": ["20.1"],
                                "rule_markdown": "- Clause 20.1 is overtime. [20.1]",
                                "rule_plain_text": "Clause 20.1 is overtime.",
                                "source_clause_numbers": ["20.1"],
                                "source_classifications": ["Overtime Trigger"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            with patch("src.script_3b_review_overtime_interpretation.time.sleep") as sleep_mock:
                review_overtime_interpretation(
                    interpretation_path=interpretation_path,
                    classification_path=classification_path,
                    overtime_clause_classification_path=overtime_clause_classification_path,
                    evaluator_client=evaluator_client,
                    creator_client=creator_client,
                    inter_call_delay_seconds=1,
                    status_callback=status_messages.append,
                )

        self.assertEqual(sleep_mock.call_args.args[0], 1)
        self.assertTrue(
            any(
                "Token budget for script_3b_evaluator_review" in message
                for message in status_messages
            )
        )
        self.assertTrue(
            any(
                "Token budget for script_3b_creator_revision" in message
                for message in status_messages
            )
        )

    def test_review_overtime_interpretation_accepts_fenced_json_from_response_api_evaluator(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            }
        }
        overtime_clause_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "explanation": "Directly creates overtime.",
                    "clause_text": "Overtime after ordinary hours.",
                }
            ],
        }
        evaluator_response = SimpleNamespace(
            output=[
                {
                    "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    "```json\n"
                                '{"summary_markdown": "# Feedback", "rule_reviews": [{"rule_id": "all-employees_001", "recommendation": "keep", "rationale": "Keep the rule."}], "new_rules": []}\n'
                                    "```"
                                ),
                            }
                    ]
                }
            ]
        )
        evaluator_client = FakeResponseApiEvaluatorClient(evaluator_response)
        creator_client = FakeCreatorClient(
            json.dumps(
                {
                    "decision_record_markdown": "# Creator response\n\nAccepted.",
                    "rule_updates": [
                        {
                            "rule_id": "all-employees_001",
                            "decision": "keep",
                            "reason": "Accepted.",
                        }
                    ],
                    "new_rule_reviews": [],
                }
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_payment_classification.json"
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )
            interpretation_path.write_text("## All Employees", encoding="utf-8")
            interpretation_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "schema_version": "overtime-rules-v1",
                        "source_classification_file": "award_payment_classification.json",
                        "source_clause_classification_file": "award_overtime_clause_classification.json",
                        "rendered_markdown": "## All Employees\n\n- Clause 20.1 is overtime. [20.1]\n",
                        "rules": [
                            {
                                "rule_id": "all-employees_001",
                                "section_heading": "All Employees",
                                "employee_scope": ["full-time", "part-time", "casual"],
                                "clause_references": ["20.1"],
                                "rule_markdown": "- Clause 20.1 is overtime. [20.1]",
                                "rule_plain_text": "Clause 20.1 is overtime.",
                                "source_clause_numbers": ["20.1"],
                                "source_classifications": ["Overtime Trigger"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            artifacts = review_overtime_interpretation(
                interpretation_path=interpretation_path,
                classification_path=classification_path,
                overtime_clause_classification_path=overtime_clause_classification_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
                inter_call_delay_seconds=0,
            )

        self.assertIn("# Feedback", artifacts.evaluator_feedback_markdown)

    def test_review_overtime_interpretation_preserves_original_rules_after_creator_validation_failure(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime after ordinary hours.",
                }
            }
        }
        overtime_clause_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "explanation": "Directly creates overtime.",
                    "clause_text": "Overtime after ordinary hours.",
                }
            ],
        }
        evaluator_client = FakeEvaluatorClient(
            json.dumps(
                {
                    "summary_markdown": "# Feedback",
                    "rule_reviews": [
                        {
                            "rule_id": "all-employees_001",
                            "recommendation": "keep",
                            "rationale": "Keep the rule.",
                        }
                    ],
                    "new_rules": [],
                }
            )
        )
        creator_client = FakeCreatorClient(
            [
                json.dumps(
                    {
                    "decision_record_markdown": "# Decision",
                        "rule_updates": [
                            {
                                "rule_id": "all-employees_001",
                            "decision": "remove",
                            "reason": "Remove it.",
                        }
                    ],
                    "new_rule_reviews": [],
                }
            ),
            json.dumps(
                {
                        "decision_record_markdown": "# Still invalid",
                        "rule_updates": [
                            {
                                "rule_id": "all-employees_001",
                            "decision": "remove",
                            "reason": "Remove it.",
                        }
                    ],
                    "new_rule_reviews": [],
                }
            ),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            interpretation_path.write_text(
                "## All employees\n\n- Original rule. [20.1]",
                encoding="utf-8",
            )
            interpretation_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "schema_version": "overtime-rules-v1",
                        "source_classification_file": "award_payment_classification.json",
                        "source_clause_classification_file": "award_overtime_clause_classification.json",
                        "rendered_markdown": "## All employees\n\n- Original rule. [20.1]\n",
                        "rules": [
                            {
                                "rule_id": "all-employees_001",
                                "section_heading": "All employees",
                                "employee_scope": ["full-time", "part-time", "casual"],
                                "clause_references": ["20.1"],
                                "rule_markdown": "- Original rule. [20.1]",
                                "rule_plain_text": "Original rule.",
                                "source_clause_numbers": ["20.1"],
                                "source_classifications": ["Overtime Trigger"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            classification_path = temp_path / "award_payment_classification.json"
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            artifacts = review_overtime_interpretation(
                interpretation_path=interpretation_path,
                classification_path=classification_path,
                overtime_clause_classification_path=overtime_clause_classification_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
                inter_call_delay_seconds=0,
            )

            self.assertIn(
                "validation failure",
                artifacts.creator_response_markdown.lower(),
            )
            self.assertIn(
                "Original rule. [20.1]",
                artifacts.revised_interpretation_markdown,
            )

    def test_review_overtime_interpretation_records_dropped_clause_warning(self):
        classification = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Clause 20.1 text.",
                },
                "20.2": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Clause 20.2 text.",
                },
            }
        }
        overtime_clause_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "explanation": "Relevant.",
                    "clause_text": "Clause 20.1 text.",
                },
                {
                    "clause_number": "20.2",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "explanation": "Relevant.",
                    "clause_text": "Clause 20.2 text.",
                },
            ],
        }
        evaluator_client = FakeEvaluatorClient(
            json.dumps(
                {
                    "summary_markdown": "# Feedback",
                    "rule_reviews": [
                        {
                            "rule_id": "all-employees_001",
                            "recommendation": "remove",
                            "rationale": "Remove this rule.",
                        },
                        {
                            "rule_id": "all-employees_002",
                            "recommendation": "keep",
                            "rationale": "Keep this rule.",
                        },
                    ],
                    "new_rules": [],
                }
            )
        )
        creator_client = FakeCreatorClient(
            [
                json.dumps(
                    {
                        "decision_record_markdown": "# Decision",
                        "rule_updates": [
                            {
                                "rule_id": "all-employees_001",
                                "decision": "remove",
                                "reason": "Accepted removal.",
                            },
                        {
                            "rule_id": "all-employees_002",
                            "decision": "keep",
                            "reason": "Keep the supported rule.",
                        },
                    ],
                        "new_rule_reviews": [],
                    }
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            interpretation_path.write_text(
                "## All employees\n\n- Rule one. [20.2]\n- Rule two. [20.1]",
                encoding="utf-8",
            )
            interpretation_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "schema_version": "overtime-rules-v1",
                        "source_classification_file": "award_payment_classification.json",
                        "source_clause_classification_file": "award_overtime_clause_classification.json",
                        "rendered_markdown": "## All employees\n\n- Rule one. [20.2]\n- Rule two. [20.1]\n",
                        "rules": [
                            {
                                "rule_id": "all-employees_001",
                                "section_heading": "All employees",
                                "employee_scope": ["full-time"],
                                "clause_references": ["20.2"],
                                "rule_markdown": "- Rule one. [20.2]",
                                "rule_plain_text": "Rule one.",
                                "source_clause_numbers": ["20.2"],
                                "source_classifications": ["Overtime Trigger"],
                            },
                            {
                                "rule_id": "all-employees_002",
                                "section_heading": "All employees",
                                "employee_scope": ["full-time"],
                                "clause_references": ["20.1"],
                                "rule_markdown": "- Rule two. [20.1]",
                                "rule_plain_text": "Rule two.",
                                "source_clause_numbers": ["20.1"],
                                "source_classifications": ["Overtime Trigger"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            classification_path = temp_path / "award_payment_classification.json"
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            artifacts = review_overtime_interpretation(
                interpretation_path=interpretation_path,
                classification_path=classification_path,
                overtime_clause_classification_path=overtime_clause_classification_path,
                evaluator_client=evaluator_client,
                creator_client=creator_client,
                inter_call_delay_seconds=0,
            )
            revised_json = json.loads(
                artifacts.revised_interpretation_json_path.read_text(encoding="utf-8")
            )

        expected_warning = (
            "The earlier draft clause 20.2 was present before review but is not "
            "referenced after review."
        )
        self.assertIn("# Validation notes", artifacts.revised_interpretation_markdown)
        self.assertIn(expected_warning, artifacts.revised_interpretation_markdown)
        self.assertEqual(revised_json["validation_warnings"], [expected_warning])


if __name__ == "__main__":
    unittest.main()
