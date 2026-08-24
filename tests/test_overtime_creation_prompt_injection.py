from pathlib import Path
import unittest

from src.common.overtime_clause_classification import OvertimeClauseClassification
from src.common.overtime_rules import OvertimeRule
from src.common.rule_inventory import RuleInventory, RuleRecord
from src.prompts.overtime_common_prompt_blocks import (
    OVERTIME_CREATION_COMMON_QUESTIONS,
)
from src.prompts.step_2_2_classify_overtime_clauses import (
    build_clause_classification_messages,
)
from src.prompts.step_3_1_generate_ruleset import (
    build_expert_comparison_messages,
    build_interpretation_messages,
)
from src.prompts.step_3_2_review_ruleset import (
    build_step_3_2_creator_user_prompt,
    build_step_3_2_evaluator_user_prompt,
)
from src.prompts.step_4_1_format_ruleset import build_messages as build_format_messages
from src.prompts.step_5_1_generate_pseudocode import (
    build_messages as build_pseudocode_messages,
    build_repair_messages as build_pseudocode_repair_messages,
)


def message_contains_expected_block(messages: list[dict[str, str]]) -> bool:
    for message in messages:
        if OVERTIME_CREATION_COMMON_QUESTIONS in message["content"]:
            return True

    return False


class OvertimeCreationPromptInjectionTests(unittest.TestCase):
    def test_step_2_2_classification_includes_creation_questions(self):
        messages = build_clause_classification_messages(
            {"21.1": {"text": "Ordinary hours are 38 per week."}},
        )

        self.assertTrue(message_contains_expected_block(messages))
        self.assertNotIn("classification.json", messages[1]["content"])
        self.assertIn(
            "treat that as an all-employees ordinary-hours boundary",
            messages[1]["content"],
        )
        user_prompt = messages[1]["content"]
        self.assertLess(
            user_prompt.index("Step 2.2 scope and classification instructions:"),
            user_prompt.index("Required output for every clause:"),
        )
        self.assertLess(
            user_prompt.index("Required output for every clause:"),
            user_prompt.index("Clauses:"),
        )

    def test_step_3_1_generation_includes_creation_questions(self):
        messages = build_interpretation_messages(
            "overtime_creation",
            "classification.json",
            [
                OvertimeClauseClassification(
                    clause_number="21.1",
                    classification="Ordinary Hours Boundary",
                    classifications=("Ordinary Hours Boundary",),
                    clause_text="Ordinary hours are 38 hours per week.",
                    explanation="Weekly ordinary hours boundary.",
                    employee_cohort="all",
                    work_arrangement="all",
                    other_scope_notes="",
                )
            ],
        )

        self.assertTrue(message_contains_expected_block(messages))
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        self.assertIn(
            "Authoritative project interpretation for overtime creation",
            system_prompt,
        )
        self.assertIn(
            "Any worked time outside an applicable ordinary-hours boundary is overtime",
            system_prompt,
        )
        self.assertIn(
            "This is the default interpretation for the ruleset, not an assumption",
            system_prompt,
        )
        self.assertIn(
            "Task: Build the overtime creation payroll ruleset from the source clauses below.",
            user_prompt,
        )
        self.assertIn("Step 3.1 subset-specific instructions:", user_prompt)
        self.assertNotIn("Source classification file:", user_prompt)
        self.assertIn("General guidance for the reusable checks below:", user_prompt)
        self.assertIn(
            "Do not say that work outside an applicable ordinary-hours boundary is merely overtime-eligible",
            user_prompt,
        )
        self.assertLess(
            user_prompt.index("Task: Build"),
            user_prompt.index("Step 3.1 subset-specific instructions:"),
        )

    def test_step_3_1_merge_includes_creation_questions(self):
        rule = OvertimeRule(
            rule_id="weekly-ordinary-hours-boundary",
            section_heading="All Employees",
            employee_scope=("full-time", "part-time", "casual"),
            employee_cohort="all",
            work_arrangement="all",
            other_scope_notes="",
            clause_references=("21.1",),
            rule_markdown="- Ordinary hours are 38 hours per week. [21.1]",
            rule_plain_text="Ordinary hours are 38 hours per week.",
            source_clause_numbers=("21.1",),
            source_classifications=("Ordinary Hours Boundary",),
        )

        messages = build_expert_comparison_messages(
            ruleset_key="overtime_creation",
            source_path=Path("classification.json"),
            overtime_creation_clauses=[
                OvertimeClauseClassification(
                    clause_number="21.1",
                    classification="Ordinary Hours Boundary",
                    classifications=("Ordinary Hours Boundary",),
                    clause_text="Ordinary hours are 38 hours per week.",
                    explanation="Weekly ordinary hours boundary.",
                    employee_cohort="all",
                    work_arrangement="all",
                    other_scope_notes="",
                )
            ],
            run_a_rules=[rule],
            run_b_rules=[rule],
        )

        self.assertTrue(message_contains_expected_block(messages))

    def test_step_3_2_review_includes_creation_questions(self):
        messages = build_step_3_2_evaluator_user_prompt(
            interpretation_path=Path("interpretation.md"),
            interpretation_markdown="# Draft\n\n- Ordinary hours are 38 hours per week. [21.1]",
            original_rules_artifact=None,
            classification_path=Path("classification.json"),
            payment_classification={
                "classified_clauses": {
                    "21.1": {
                        "tags": ["Ordinary Hours & Overtime"],
                        "text": "Ordinary hours are 38 hours per week.",
                    }
                }
            },
            overtime_clause_classification_path=Path("overtime.json"),
            overtime_clause_classification={
                "ruleset_key": "overtime_creation",
                "clauses": [
                    {
                        "clause_number": "21.1",
                        "classification": "Ordinary Hours Boundary",
                        "classifications": ["Ordinary Hours Boundary"],
                        "clause_text": "Ordinary hours are 38 hours per week.",
                        "explanation": "Weekly ordinary hours boundary.",
                        "employee_cohort": "all",
                        "work_arrangement": "all",
                        "other_scope_notes": "",
                    }
                ],
            },
            ruleset_key="overtime_creation",
        )

        self.assertIn(OVERTIME_CREATION_COMMON_QUESTIONS, messages)
        self.assertIn("Pipeline stages used in this review:", messages)
        self.assertIn("Step 2.1 payment classification:", messages)
        self.assertIn("Step 2.2 clause classification:", messages)
        self.assertIn("Step 3.1 ruleset generation:", messages)
        self.assertIn("validation_warnings", messages)
        self.assertIn("# Validation notes", messages)
        self.assertIn(
            "Authoritative project interpretation: any worked time outside an applicable ordinary-hours boundary is overtime",
            messages,
        )
        self.assertIn(
            "an express shiftworker override means the general span is a day-worker rule",
            messages,
        )

    def test_step_3_2_creator_includes_creation_questions(self):
        message = build_step_3_2_creator_user_prompt(
            interpretation_path=Path("interpretation.md"),
            interpretation_markdown="# Draft\n\n- Ordinary hours are 38 hours per week. [21.1]",
            relevant_clause_excerpt_markdown="Relevant clauses...",
            evaluator_feedback_markdown="Feedback...",
            creator_review_action_pack_json="{}",
            ruleset_key="overtime_creation",
        )

        self.assertIn(OVERTIME_CREATION_COMMON_QUESTIONS, message)
        self.assertIn(
            "Keep an express alternative work-arrangement rule separate",
            message,
        )

    def test_step_4_1_formatting_includes_creation_questions(self):
        messages = build_format_messages(
            interpretation_path=Path("interpretation.md"),
            interpretation_markdown="# Draft\n\n- Ordinary hours are 38 hours per week. [21.1]",
            template_path=Path("template.md"),
            template_markdown="# Template",
            ruleset_key="overtime_creation",
        )

        self.assertTrue(message_contains_expected_block(messages))
        user_prompt = messages[1]["content"]
        self.assertLess(
            user_prompt.index("Common clauses that may appear:"),
            user_prompt.index("Reviewed ruleset content:"),
        )
        self.assertLess(
            user_prompt.index("Step 4.1 subset-specific formatting instructions:"),
            user_prompt.index("Reviewed ruleset content:"),
        )
        self.assertIn(
            "Do not append a warning that the",
            user_prompt,
        )
        self.assertIn(
            "rule must be tested under a full-time, part-time, or casual trigger",
            user_prompt,
        )

    def test_step_5_1_pseudocode_includes_creation_questions(self):
        messages = build_pseudocode_messages(
            source_file="source.md",
            overtime_summary_markdown="# Summary\n\n- Ordinary hours are 38 hours per week. [21.1]",
        )

        self.assertTrue(message_contains_expected_block(messages))

    def test_step_5_1_repair_includes_creation_questions(self):
        inventory = RuleInventory(
            inventory_name="overtime",
            source_path="source.md",
            source_stage="step-5.1",
            domain="overtime",
            rules=(
                RuleRecord(
                    rule_id="weekly-ordinary-hours-boundary",
                    section_heading="All Employees",
                    rule_text="Ordinary hours are 38 hours per week.",
                    clause_references=("21.1",),
                    employee_scope=("full-time", "part-time", "casual"),
                    source_line_start=1,
                    source_line_end=1,
                ),
            ),
        )
        messages = build_pseudocode_repair_messages(
            source_file="source.md",
            overtime_summary_markdown="# Summary\n\n- Ordinary hours are 38 hours per week. [21.1]",
            source_inventory=inventory,
            initial_pseudocode_markdown="# Draft",
            validation_report_markdown="# Validation",
        )

        self.assertTrue(message_contains_expected_block(messages))
