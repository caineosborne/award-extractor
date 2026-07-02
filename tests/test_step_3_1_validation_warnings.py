from src.common.overtime_rules import (
    HIGH_IMPACT_VALIDATION_SECTION,
    HIDDEN_DIAGNOSTIC_VALIDATION_SECTION,
    OvertimeRule,
    REVIEW_NOTES_VALIDATION_SECTION,
    categorize_validation_warnings,
    prepend_validation_warnings,
    review_decision_change_warnings,
)
from src.step_2_2_classify_overtime_clauses.core import OvertimeClauseClassification
from src.step_3_1_generate_ruleset.core import (
    missing_shortlisted_clause_warning,
    scope_validation_warnings_for_rule,
)


def test_scope_validation_warnings_keep_one_to_one_employee_scope_mismatch():
    rule = OvertimeRule(
        rule_id="part-time-rule",
        section_heading="Part-time employees",
        employee_scope=("part-time",),
        employee_cohort="part-time",
        work_arrangement="all",
        other_scope_notes="",
        clause_references=("10.4",),
        rule_markdown="Part-time employees create overtime after 8 hours. [10.4]",
        rule_plain_text="Part-time employees create overtime after 8 hours.",
        source_clause_numbers=("10.4",),
        source_classifications=("Overtime Trigger",),
    )
    classification = OvertimeClauseClassification(
        clause_number="10.4",
        classification="Overtime Trigger",
        classifications=("Overtime Trigger",),
        clause_text="Part-time employees are paid overtime after 8 hours.",
        explanation="Applies only to part-time employees.",
        employee_cohort="all",
        work_arrangement="all",
        other_scope_notes="Applies to part-time employees only.",
    )

    warnings = scope_validation_warnings_for_rule(rule, [classification])

    assert warnings == [
        "Rule 'part-time-rule' draws on clause 10.4, which is classified as applying to all employees, but the rule is written as applying to part-time employees."
    ]


def test_scope_validation_warnings_hide_multi_clause_scope_noise():
    rule = OvertimeRule(
        rule_id="full-time-ordinary-hours-average-38-per-week",
        section_heading="Full-time employees",
        employee_scope=("full-time",),
        employee_cohort="full-time",
        work_arrangement="all",
        other_scope_notes="This is the ordinary-hours boundary for full-time employment.",
        clause_references=("10.3", "21.1", "23.1"),
        rule_markdown="Full-time employees create overtime outside ordinary hours. [10.3, 21.1, 23.1]",
        rule_plain_text="Full-time employees create overtime outside ordinary hours.",
        source_clause_numbers=("10.3", "21.1", "23.1"),
        source_classifications=("Ordinary Hours Boundary", "Overtime Trigger"),
    )
    classifications = [
        OvertimeClauseClassification(
            clause_number="10.3",
            classification="Ordinary Hours Boundary",
            classifications=("Ordinary Hours Boundary",),
            clause_text="Definition applies to full-time employees only.",
            explanation="Definition applies to full-time employees only.",
            employee_cohort="full-time",
            work_arrangement="all",
            other_scope_notes="Definition applies to full-time employees only.",
        ),
        OvertimeClauseClassification(
            clause_number="21.1",
            classification="Ordinary Hours Boundary",
            classifications=("Ordinary Hours Boundary",),
            clause_text="Applies to full-time employees and establishes the averaging period.",
            explanation="Applies to full-time employees and establishes the averaging period.",
            employee_cohort="full-time",
            work_arrangement="all",
            other_scope_notes="Applies to full-time employees and establishes the averaging period.",
        ),
        OvertimeClauseClassification(
            clause_number="23.1",
            classification="Overtime Trigger",
            classifications=("Overtime Trigger",),
            clause_text="Operative overtime entitlement clause for all employee cohorts covered.",
            explanation="Operative overtime entitlement clause for all employee cohorts covered.",
            employee_cohort="all",
            work_arrangement="all",
            other_scope_notes="Operative overtime entitlement clause for all employee cohorts covered.",
        ),
    ]

    warnings = scope_validation_warnings_for_rule(rule, classifications)

    assert warnings == []


def test_missing_shortlisted_clause_warning_remains_visible():
    warning = missing_shortlisted_clause_warning(
        "21.9",
        ruleset_label="draft ruleset before review",
    )

    assert warning == (
        "Clause 21.9 was identified as relevant to overtime, "
        "but it is not present in the draft ruleset before review."
    )


def test_categorize_validation_warnings_groups_by_reviewer_impact():
    validation_warnings = [
        "Clause 21.9 was identified as relevant to overtime, but it is not present in the draft ruleset before review.",
        "Rule 'full-time-rule' draws on clause 10.3, which is classified as applying to full-time employees, but the rule is written as applying to all employees.",
        "Rule 'part-time-rule' draws on clause 10.4, which is classified as applying to all employees, but the rule is written as applying to part-time employees.",
        "Interpretation output returned duplicate rule_id `rule-1`. Rule 2 was renamed to `rule-1-2`.",
    ]

    categorized_warnings = categorize_validation_warnings(validation_warnings)

    assert categorized_warnings[HIGH_IMPACT_VALIDATION_SECTION] == [
        "Clause 21.9 was identified as relevant to overtime, but it is not present in the draft ruleset before review.",
        "Rule 'full-time-rule' draws on clause 10.3, which is classified as applying to full-time employees, but the rule is written as applying to all employees.",
    ]
    assert categorized_warnings[REVIEW_NOTES_VALIDATION_SECTION] == [
        "Rule 'part-time-rule' draws on clause 10.4, which is classified as applying to all employees, but the rule is written as applying to part-time employees."
    ]
    assert categorized_warnings[HIDDEN_DIAGNOSTIC_VALIDATION_SECTION] == [
        "Interpretation output returned duplicate rule_id `rule-1`. Rule 2 was renamed to `rule-1-2`."
    ]


def test_prepend_validation_warnings_renders_grouped_sections():
    rendered_markdown = prepend_validation_warnings(
        "## All employees\n\n- After 38 hours per week. [20.1]\n",
        [
            "Clause 21.9 was identified as relevant to overtime, but it is not present in the draft ruleset before review.",
            "Rule 'part-time-rule' draws on clause 10.4, which is classified as applying to all employees, but the rule is written as applying to part-time employees.",
            "Interpretation output returned duplicate rule_id `rule-1`. Rule 2 was renamed to `rule-1-2`.",
        ],
    )

    assert "# Validation notes" in rendered_markdown
    assert "## Action required" in rendered_markdown
    assert "## Review notes" in rendered_markdown
    assert "## Hidden diagnostic details" in rendered_markdown
    assert "## All employees" in rendered_markdown


def test_categorize_validation_warnings_keeps_review_loop_changes_visible():
    validation_warnings = [
        "The earlier draft clause 21.3 was present before review but is not referenced after review.",
        "The review removed original rule 'general-ordinary-hours-time-span-6am-to-630pm' from the revised ruleset. Original clause references: 21.3.",
        "The review rejected evaluator-proposed new rule 'replacement-rule'.",
    ]

    categorized_warnings = categorize_validation_warnings(validation_warnings)

    assert categorized_warnings[HIGH_IMPACT_VALIDATION_SECTION] == [
        "The earlier draft clause 21.3 was present before review but is not referenced after review."
    ]
    assert categorized_warnings[REVIEW_NOTES_VALIDATION_SECTION] == [
        "The review removed original rule 'general-ordinary-hours-time-span-6am-to-630pm' from the revised ruleset. Original clause references: 21.3.",
        "The review rejected evaluator-proposed new rule 'replacement-rule'.",
    ]


def test_review_decision_change_warnings_report_removed_and_rejected_rules():
    original_rules = [
        OvertimeRule(
            rule_id="general-ordinary-hours-time-span-6am-to-630pm",
            section_heading="General ordinary hours boundary",
            employee_scope=("full-time", "part-time", "casual"),
            employee_cohort="all",
            work_arrangement="all",
            other_scope_notes="",
            clause_references=("21.3",),
            rule_markdown="- Ordinary hours may only be worked between 6.00 am and 6.30 pm. [21.3]",
            rule_plain_text="Ordinary hours may only be worked between 6.00 am and 6.30 pm.",
            source_clause_numbers=("21.3",),
            source_classifications=("Ordinary Hours Boundary",),
        )
    ]
    review_decisions = [
        {
            "rule_id": "general-ordinary-hours-time-span-6am-to-630pm",
            "evaluator_recommendation": "remove",
            "creator_decision": "remove",
            "final_decision": "removed",
            "reason": "Removed during review.",
        },
        {
            "rule_id": "replacement-rule",
            "evaluator_recommendation": "add",
            "creator_decision": "reject",
            "final_decision": "rejected",
            "reason": "Rejected during review.",
        },
    ]

    warnings = review_decision_change_warnings(
        original_rules=original_rules,
        review_decisions=review_decisions,
    )

    assert warnings == [
        "The review removed original rule 'general-ordinary-hours-time-span-6am-to-630pm' from the revised ruleset. Original clause references: 21.3.",
        "The review rejected evaluator-proposed new rule 'replacement-rule'.",
    ]
