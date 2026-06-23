from pathlib import Path

from src.common.rule_inventory import parse_rule_inventory_from_markdown
from src.script_5b_validate_overtime_pseudocode import (
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
