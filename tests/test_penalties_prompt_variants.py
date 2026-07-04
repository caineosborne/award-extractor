from pathlib import Path

from src.common.overtime_rules import OvertimeRule
from src.common.overtime_rulesets import PENALTIES_RULESET
from src.prompts.overtime_common_prompt_blocks import common_overtime_question_block
from src.prompts.step_2_2_classify_overtime_clauses import build_clause_classification_messages
from src.prompts.step_3_1_generate_ruleset import (
    build_expert_comparison_messages,
    build_interpretation_messages,
)
from src.prompts.step_3_2_prompt_config import step_3_2_prompt_subset_config
from src.step_2_2_classify_overtime_clauses.core import OvertimeClauseClassification


def test_penalties_common_question_block_includes_agreed_examples():
    question_block = common_overtime_question_block(PENALTIES_RULESET)

    assert "shift commences at a particular time" in question_block
    assert "specific hours" in question_block
    assert "public holiday" in question_block
    assert "the entire shift" in question_block
    assert "200% payment consequence plus paid release" in question_block
    assert "still in scope even when they do not create any separate payment outcome" in question_block


def test_step_3_2_penalties_subset_config_uses_penalties_scope_notes():
    config = step_3_2_prompt_subset_config(PENALTIES_RULESET)

    assert config.ruleset_key == PENALTIES_RULESET
    assert config.display_name == "Penalties"
    assert "penalties" in config.review_question.lower()
    assert any("break-gap" in note for note in config.subset_scope_notes)
    assert any("overtime-only drafting drift" in note for note in config.subset_scope_notes)


def test_step_2_2_penalties_prompt_context_is_available_for_review_rebuilds():
    messages = build_clause_classification_messages(
        {"26.1": {"text": "Night shift is paid at 115%."}},
        PENALTIES_RULESET,
    )

    assert "penalties subset" in messages[1]["content"]
    assert "downstream handling is deterministic" in messages[1]["content"]
    assert "all shortlisted clauses are treated as `Penalty Rule`" in messages[1]["content"]


def test_step_3_1_penalties_prompt_uses_penalties_specific_scope():
    messages = build_interpretation_messages(
        PENALTIES_RULESET,
        "classification.json",
        [
            OvertimeClauseClassification(
                clause_number="26.1",
                classification="Penalty Rule",
                classifications=["Penalty Rule"],
                clause_text=(
                    "Employees working afternoon or night shift will be paid percentages "
                    "in addition to the ordinary rate for such shift."
                ),
                explanation="Shift commencement penalty bands for afternoon and night shift.",
                employee_cohort="all",
                work_arrangement="shiftworker",
                other_scope_notes="",
            )
        ],
    )

    assert "Supporting break-between-work-period rules remain in scope" in messages[0]["content"]
    assert (
        "What penalty, shift allowance, or break-between-work-period rule applies"
        in messages[1]["content"]
    )
    assert "Keep shift commencement rules separate" in messages[1]["content"]
    assert "Do not invent a financial consequence" in messages[1]["content"]
    assert "# Penalties Clauses" in messages[1]["content"]
    assert "A single clause may contain multiple distinct operational rules." in messages[1]["content"]
    assert "A single operational rule may rely on multiple clauses" in messages[1]["content"]


def test_step_3_1_penalties_merge_prompt_preserves_supporting_rules():
    clause = OvertimeClauseClassification(
        clause_number="27.1",
        classification="Penalty Rule",
        classifications=("Penalty Rule",),
        clause_text="An employee must have a minimum break of 10 hours between shifts.",
        explanation="Supporting break-gap rule with no separate premium outcome in this clause.",
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="",
    )
    supporting_rule = OvertimeRule(
        rule_id="minimum-break-between-shifts",
        section_heading="Breaks Between Work Periods",
        employee_scope=("full-time", "part-time", "casual"),
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="",
        clause_references=("27.1",),
        rule_markdown="- Employees must receive a minimum 10-hour break between shifts. [27.1]",
        rule_plain_text="Employees must receive a minimum 10-hour break between shifts.",
        source_clause_numbers=("27.1",),
        source_classifications=("Penalty Rule",),
    )

    messages = build_expert_comparison_messages(
        ruleset_key=PENALTIES_RULESET,
        source_path=Path("classification.json"),
        overtime_creation_clauses=[clause],
        run_a_rules=[supporting_rule],
        run_b_rules=[supporting_rule],
    )

    assert (
        "Do not convert a supporting non-financial break-gap rule into an invented multiplier"
        in messages[1]["content"]
    )
    assert (
        "Distinguish rules that apply to an entire shift from rules that apply only to qualifying hours."
        in messages[1]["content"]
    )
