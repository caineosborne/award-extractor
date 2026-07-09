from pathlib import Path

from src.common.rule_inventory import (
    extract_clause_references,
    parse_rule_inventory_from_markdown,
)
from src.step_5_1_generate_pseudocode.step_3_validate_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
    validate_overtime_pseudocode_against_inventory,
)


def test_validate_overtime_pseudocode_flags_missing_source_rule():
    source_markdown = """## Casual employees

- **Any time worked in excess of 38 ordinary hours per week will be overtime.** Clause **11.1(a)**.
- **Where the casual employee works in accordance with a roster, any time worked in excess of 38 ordinary hours per week averaged over the course of the roster cycle will be overtime.** Clause **11.1(b)**.
"""

    pseudocode_markdown = """# Overtime pseudocode

## Derived Fields

None

## Required additional inputs

- None

## Rule priority

1. Time worked in excess of 38 ordinary hours per week averaged over the roster cycle

## Pseudocode

- If the employee is casual and works in accordance with a roster, and average ordinary hours over the roster cycle exceed 38 hours per week, allocate the excess hours to `Overtime_Hours`.
  - # Source: Clause 11.1(b)
"""

    inventory = parse_rule_inventory_from_markdown(
        source_markdown,
        source_path=Path("source.md"),
        inventory_name="reviewed_overtime_rules",
        source_stage="3b",
        domain="overtime",
    )

    report = validate_overtime_pseudocode_against_inventory(
        inventory,
        pseudocode_markdown,
        target_path=Path("target.md"),
    )

    assert report.overall_status == "failed"
    assert report.passed_rule_count == 1
    assert report.failed_rule_count == 1
    assert report.rule_results[0].status == "failed"
    assert "No matching clause references" in report.rule_results[0].message


def test_validate_overtime_pseudocode_flags_priority_without_rule():
    source_markdown = """## Full-time employees

- **Any time worked after the employee's rostered finish time on any day will be overtime.** Clause **20.2(c)**.
"""

    pseudocode_markdown = """# Overtime pseudocode

## Derived Fields

None

## Required additional inputs

- None

## Rule priority

1. Time worked outside the ordinary hours of work

## Pseudocode

- If `Shift_End` is after `Roster_End`, allocate the hours worked after `Roster_End` to `Overtime_Hours`.
  - # Source: Clauses 20.2(c)
"""

    inventory = parse_rule_inventory_from_markdown(
        source_markdown,
        source_path=Path("source.md"),
        inventory_name="reviewed_overtime_rules",
        source_stage="3b",
        domain="overtime",
    )

    report = validate_overtime_pseudocode_against_inventory(
        inventory,
        pseudocode_markdown,
        target_path=Path("target.md"),
    )

    assert any(issue.issue_type == "priority_without_rule" for issue in report.issues)


def test_validation_paths_use_pseudocode_stem():
    pseudocode_path = Path("data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md")

    assert (
        validation_json_path_for_pseudocode(pseudocode_path).name
        == "MA000018_core_overtime_pseudocode_validation.json"
    )
    assert (
        validation_markdown_path_for_pseudocode(pseudocode_path).name
        == "MA000018_core_overtime_pseudocode_validation.md"
    )


def test_validate_overtime_pseudocode_matches_source_comments_without_clause_word():
    source_markdown = """## All employees

- The hours will be overtime if work is performed outside the ordinary span. [21.3]
"""

    pseudocode_markdown = """# Overtime pseudocode

## Derived Fields

None

## Required additional inputs

- None

## Rule priority

1. Work outside ordinary span

## Pseudocode

- If `Shift_Start` is before 6:00 am, or `Shift_End` is after 6:30 pm:
  - Allocate the hours worked outside the ordinary span to `Overtime_Hours`
  - # Source: 21.3
"""

    inventory = parse_rule_inventory_from_markdown(
        source_markdown,
        source_path=Path("source.md"),
        inventory_name="reviewed_overtime_rules",
        source_stage="3b",
        domain="overtime",
    )

    report = validate_overtime_pseudocode_against_inventory(
        inventory,
        pseudocode_markdown,
        target_path=Path("target.md"),
    )

    assert report.overall_status == "passed"
    assert report.passed_rule_count == 1


def test_extract_clause_references_supports_step_5_1_inline_comment_style():
    rule_text = (
        "- **Emergency roster change outside employer control** "
        "`// 21.7(b)(ii), 21.7(b)(iv), 10.4(d)(iii), 10.4(d)(iv), 23.2(c)`"
    )

    assert extract_clause_references(rule_text) == (
        "21.7(b)(ii)",
        "21.7(b)(iv)",
        "10.4(d)(iii)",
        "10.4(d)(iv)",
        "23.2(c)",
    )


def test_extract_clause_references_does_not_treat_plain_times_as_clause_references():
    rule_text = "- Treat ordinary hours as Monday-Friday within 6:00 am to 6:30 pm."

    assert extract_clause_references(rule_text) == ()


def test_validate_overtime_pseudocode_treats_explicit_exclusion_as_unresolved():
    source_markdown = """## All employees

- Employees must be released after overtime where the clause requires immediate release and managerial direction. [21.8]
"""

    pseudocode_markdown = """# Overtime consequence pseudocode

## Derived Fields

None

## Required additional inputs

- None

## Rule priority

1. Apply direct overtime payment rules before commentary-only conditions

## Pseudocode

- If overtime is worked on Sunday, apply the Sunday overtime multiplier. # Source: 20.1

## Conditions not considered by the pseudocode

- Clause 21.8 is not modelled because it depends on managerial judgement about immediate release rather than a stable code-definable condition.

## Implementation notes

- None
"""

    inventory = parse_rule_inventory_from_markdown(
        source_markdown,
        source_path=Path("source.md"),
        inventory_name="reviewed_overtime_rules",
        source_stage="3b",
        domain="overtime",
    )

    report = validate_overtime_pseudocode_against_inventory(
        inventory,
        pseudocode_markdown,
        target_path=Path("target.md"),
    )

    assert report.overall_status == "unresolved"
    assert report.failed_rule_count == 0
    assert report.unresolved_rule_count == 1
    assert report.rule_results[0].status == "unresolved"
    assert "explicitly excluded" in report.rule_results[0].message


def test_validate_overtime_pseudocode_fails_exclusion_without_reason():
    source_markdown = """## All employees

- Employees must be released after overtime where the clause requires immediate release and managerial direction. [21.8]
"""

    pseudocode_markdown = """# Overtime consequence pseudocode

## Derived Fields

None

## Required additional inputs

- None

## Rule priority

1. Apply direct overtime payment rules before commentary-only conditions

## Pseudocode

- If overtime is worked on Sunday, apply the Sunday overtime multiplier. # Source: 20.1

## Conditions not considered by the pseudocode

- Clause 21.8

## Implementation notes

- None
"""

    inventory = parse_rule_inventory_from_markdown(
        source_markdown,
        source_path=Path("source.md"),
        inventory_name="reviewed_overtime_rules",
        source_stage="3b",
        domain="overtime",
    )

    report = validate_overtime_pseudocode_against_inventory(
        inventory,
        pseudocode_markdown,
        target_path=Path("target.md"),
    )

    assert report.overall_status == "failed"
    assert any(
        issue.issue_type == "excluded_condition_missing_reason"
        for issue in report.issues
    )
