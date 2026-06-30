import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_5b_generate_overtime_pseudocode import (
    DEFAULT_MODEL,
    PSEUDOCODE_FIELDS,
    build_messages,
    build_repair_messages,
    default_overtime_interpretation_path,
    first_top_level_bullets,
    generate_core_overtime_pseudocode,
    load_overtime_interpretation,
    output_path_for_summary,
    overtime_rule_bullets,
    select_overtime_interpretation_path,
)
from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET
from src.script_5b_validate_overtime_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


class FakeResponses:
    def __init__(self, output_text):
        if isinstance(output_text, list):
            self.output_texts = output_text
        else:
            self.output_texts = [output_text]
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output_index = min(len(self.calls) - 1, len(self.output_texts) - 1)
        return SimpleNamespace(output_text=self.output_texts[output_index])


class FakeClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class CoreOvertimePseudocodeTests(unittest.TestCase):
    def test_first_top_level_bullets_keeps_nested_breakdowns(self):
        markdown = """# Overtime

- First bullet.
- Second bullet:
  - nested a
  - nested b
- Third bullet.
- Fourth bullet.
- Fifth bullet.
- Sixth bullet.
"""

        selected = first_top_level_bullets(markdown, count=5)

        self.assertIn("- First bullet.", selected)
        self.assertIn("  - nested a", selected)
        self.assertIn("- Fifth bullet.", selected)
        self.assertNotIn("- Sixth bullet.", selected)

    def test_output_path_for_summary(self):
        self.assertEqual(
            output_path_for_summary(
                Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md")
            ),
            Path("data/processed/MA000018/MA000018_core_overtime_pseudocode.md"),
        )

    def test_output_path_for_summary_uses_4b_source_when_present(self):
        self.assertEqual(
            output_path_for_summary(
                Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_4b.md")
            ),
            Path("data/processed/MA000018/MA000018_core_overtime_pseudocode.md"),
        )

    def test_output_path_for_summary_keeps_ruleset_isolation(self):
        self.assertEqual(
            output_path_for_summary(
                Path(
                    "data/processed/MA000018/MA000018_overtime_consequence_ruleset_overtime_entitlements.md"
                )
            ),
            Path(
                "data/processed/MA000018/MA000018_overtime_consequence_ruleset_core_overtime_pseudocode.md"
            ),
        )

    def test_overtime_rule_bullets_selects_only_overtime_labelled_rules(self):
        markdown = """# Overtime entitlements

## Plain-English overtime rules

- Overtime - for working in excess of fortnightly hours: Applies to part-time and casual employees. [25.1]
- Overtime - for working in excess of daily hours: Applies after 10 hours.
  - This keeps related detail with the rule.
- Ordinary hours note that should not be converted.

## Clause interpretation table
"""

        selected = overtime_rule_bullets(markdown)

        self.assertIn("for working in excess of fortnightly hours", selected)
        self.assertIn("This keeps related detail", selected)
        self.assertNotIn("Ordinary hours note", selected)

    def test_build_messages_include_available_fields_and_constraints(self):
        summary_markdown = (
            "# Overtime entitlements\n\n"
            "## Plain-English overtime triggers\n\n"
            "- Daily excess rule: Part-time employees...\n\n"
            "## Clause interpretation table\n\n"
            "| Clause | Relevance |\n"
            "|---|---|\n"
            "| 25.1 | Overtime trigger |\n"
        )
        messages = build_messages(
            "summary.md",
            summary_markdown,
        )

        for field, description in PSEUDOCODE_FIELDS.items():
            self.assertIn(field, messages[0]["content"])
            self.assertIn(description, messages[0]["content"])
        self.assertIn("any hours that are not ordinary hours are overtime", messages[0]["content"])
        self.assertIn("even if headings or bullet formatting have been edited", messages[0]["content"])
        self.assertIn(
            "Do not rely on an exact markdown heading or bullet label",
            messages[0]["content"],
        )
        self.assertIn("Required additional inputs", messages[0]["content"])
        self.assertIn(
            "Do not list a derived field that is just a renamed component of an existing field",
            messages[0]["content"],
        )
        self.assertIn(
            "Do not list straightforward calculations as separate derived fields",
            messages[0]["content"],
        )
        self.assertIn(
            "Treat `Required additional inputs` narrowly",
            messages[0]["content"],
        )
        self.assertIn("Complete reviewed source markdown to convert", messages[1]["content"])
        self.assertIn("Daily excess rule", messages[1]["content"])
        self.assertIn("Clause interpretation table", messages[1]["content"])

    def test_build_messages_supports_consequence_ruleset_mode(self):
        summary_markdown = (
            "# Overtime Consequences\n\n"
            "## Casual Employees\n\n"
            "- Casual employees are paid overtime at 175% for the first 2 hours. [23.2(b)]\n"
        )

        messages = build_messages(
            "summary.md",
            summary_markdown,
            ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
        )

        self.assertIn(
            "Determine what overtime consequence applies once hours are already overtime.",
            messages[0]["content"],
        )
        self.assertIn(
            "Treat this as overtime consequence mode.",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not rebuild overtime creation logic unless a source rule expressly needs it as a condition.",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not use `Ordinary_Hours` and `Overtime_Hours` as the primary outputs",
            messages[0]["content"],
        )
        self.assertIn(
            "Include exact source clause references in comments",
            messages[0]["content"],
        )

    def test_build_repair_messages_include_validation_report_and_initial_draft(self):
        summary_markdown = "# Overtime\n\n- Rule one. Clause **11.1(a)**."
        initial_pseudocode = "# Overtime pseudocode\n\n## Pseudocode\n\n- Incomplete."
        validation_report = "# 5B validation report\n\n- Failed rules: `1`"

        from src.common.rule_inventory import parse_rule_inventory_from_markdown

        inventory = parse_rule_inventory_from_markdown(
            summary_markdown,
            source_path="summary.md",
            inventory_name="reviewed_overtime_rules",
            source_stage="3b",
            domain="overtime",
        )

        messages = build_repair_messages(
            source_file="summary.md",
            overtime_summary_markdown=summary_markdown,
            source_inventory=inventory,
            initial_pseudocode_markdown=initial_pseudocode,
            validation_report_markdown=validation_report,
        )

        self.assertIn("failed deterministic validation", messages[1]["content"])
        self.assertIn("Initial pseudocode draft to repair", messages[1]["content"])
        self.assertIn("Validation report describing the missing", messages[1]["content"])
        self.assertIn("Rule ID", messages[1]["content"])
        self.assertIn("Failed rules", messages[1]["content"])
        self.assertIn("Carry the relevant source clause references into comments", messages[1]["content"])
        self.assertIn("Keep this in overtime creation mode.", messages[1]["content"])

    def test_select_overtime_interpretation_path_falls_back_from_4b_to_revised(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            manual_4b_path = source_dir / "award_overtime_interpretation_4b.md"
            entitlement_path = source_dir / "award_overtime_entitlements.md"
            revised_path = source_dir / "award_overtime_interpretation_revised.md"
            entitlement_path.write_text("# 4A", encoding="utf-8")
            revised_path.write_text("# Revised", encoding="utf-8")

            selected_path = select_overtime_interpretation_path(manual_4b_path)

        self.assertEqual(selected_path, entitlement_path)

    def test_select_overtime_interpretation_path_accepts_award_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            award_dir = project_root / "data" / "processed" / "MA000003"
            award_dir.mkdir(parents=True)
            entitlement_path = award_dir / "MA000003_overtime_entitlements.md"
            entitlement_path.write_text("# 4A", encoding="utf-8")

            from unittest.mock import patch

            with patch(
                "src.script_5b_generate_overtime_pseudocode.PROJECT_ROOT",
                project_root,
            ):
                selected_path = select_overtime_interpretation_path("MA000003")

        self.assertEqual(selected_path, entitlement_path)

    def test_select_overtime_interpretation_path_accepts_ruleset_award_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            award_dir = project_root / "data" / "processed" / "MA000003"
            award_dir.mkdir(parents=True)
            entitlement_path = (
                award_dir / "MA000003_overtime_consequence_ruleset_overtime_entitlements.md"
            )
            entitlement_path.write_text("# 4A", encoding="utf-8")

            from unittest.mock import patch

            with patch(
                "src.script_5b_generate_overtime_pseudocode.PROJECT_ROOT",
                project_root,
            ):
                selected_path = select_overtime_interpretation_path(
                    "MA000003",
                    OVERTIME_CONSEQUENCE_RULESET,
                )

        self.assertEqual(selected_path, entitlement_path)

    def test_load_overtime_interpretation_prefers_existing_4b(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            manual_4b_path = source_dir / "award_overtime_interpretation_4b.md"
            revised_path = source_dir / "award_overtime_interpretation_revised.md"
            manual_4b_path.write_text("# Manual 4B", encoding="utf-8")
            revised_path.write_text("# Revised", encoding="utf-8")

            selected_text = load_overtime_interpretation(manual_4b_path)

        self.assertEqual(selected_text, "# Manual 4B")

    def test_generate_core_overtime_pseudocode_writes_markdown_with_mocked_client(self):
        summary = """# Overtime entitlements

- Overtime - for working in excess of rostered ordinary hours: Full-time rule.
- Overtime - for working in excess of fortnightly hours: Part-time rule:
  - over 38 hours
- Overtime - for working in excess of daily hours: Casual rule.
- Overtime - for working outside the span of hours: Day worker span rule.
- Overtime - for recall to work: Recall rule.
- Meal break note that is not an overtime-labelled rule.
"""
        fake_client = FakeClient("# Core overtime pseudocode\n- Split Unallocated_Hours.")

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_overtime_entitlements.md"
            output_path = Path(temp_dir) / "award_core_overtime_pseudocode.md"
            input_path.write_text(summary, encoding="utf-8")

            result = generate_core_overtime_pseudocode(
                summary_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_core_overtime_pseudocode_*.md")
            )
            validation_json_exists = validation_json_path_for_pseudocode(output_path).exists()
            validation_markdown_exists = validation_markdown_path_for_pseudocode(output_path).exists()

        self.assertEqual(result, written)
        self.assertEqual(len(archive_files), 2)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn(
            "Meal break note",
            fake_client.responses.calls[0]["input"][1]["content"],
        )
        self.assertTrue(validation_json_exists)
        self.assertTrue(validation_markdown_exists)

    def test_generate_core_overtime_pseudocode_repairs_missing_rule_once(self):
        summary = """## Casual employees

- **Any time worked in excess of 38 ordinary hours per week will be overtime.** Clause **11.1(a)**.
- **Where the casual employee works in accordance with a roster, any time worked in excess of 38 ordinary hours per week averaged over the course of the roster cycle will be overtime.** Clause **11.1(b)**.
"""
        initial_output = """# Overtime pseudocode

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
        repaired_output = """# Overtime pseudocode

## Derived Fields

None

## Required additional inputs

- Whether the casual employee works in accordance with a roster

## Rule priority

1. Time worked in excess of 38 ordinary hours per week
2. Time worked in excess of 38 ordinary hours per week averaged over the roster cycle

## Pseudocode

- If the employee is casual and total ordinary hours worked in the week exceed 38 hours, allocate the excess hours to `Overtime_Hours`.
  - # Source: Clause 11.1(a)

- If the employee is casual and works in accordance with a roster, and average ordinary hours over the roster cycle exceed 38 hours per week, allocate the excess hours to `Overtime_Hours`.
  - # Source: Clause 11.1(b)
"""
        fake_client = FakeClient([initial_output, repaired_output])

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_overtime_interpretation_revised.md"
            output_path = Path(temp_dir) / "award_core_overtime_pseudocode.md"
            input_path.write_text(summary, encoding="utf-8")

            result = generate_core_overtime_pseudocode(
                summary_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            validation_markdown = validation_markdown_path_for_pseudocode(output_path).read_text(
                encoding="utf-8"
            )

        self.assertEqual(result, repaired_output)
        self.assertEqual(len(fake_client.responses.calls), 2)
        self.assertIn("Initial pseudocode draft to repair", fake_client.responses.calls[1]["input"][1]["content"])
        self.assertIn("Overall status: `passed`", validation_markdown)

    def test_default_overtime_interpretation_path_prefers_4b_then_4a_then_3b(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            award_dir = project_root / "data" / "processed" / "MA000018"
            award_dir.mkdir(parents=True)

            manual_4b_path = award_dir / "MA000018_overtime_interpretation_4b.md"
            entitlement_path = award_dir / "MA000018_overtime_entitlements.md"
            revised_path = award_dir / "MA000018_overtime_interpretation_revised.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            from unittest.mock import patch

            with patch(
                "src.script_5b_generate_overtime_pseudocode.PROJECT_ROOT",
                project_root,
            ):
                self.assertEqual(
                    default_overtime_interpretation_path("MA000018"),
                    revised_path,
                )

                entitlement_path.write_text("# 4A", encoding="utf-8")
                self.assertEqual(
                    default_overtime_interpretation_path("MA000018"),
                    entitlement_path,
                )

                manual_4b_path.write_text("# 4B", encoding="utf-8")
                self.assertEqual(
                    default_overtime_interpretation_path("MA000018"),
                    manual_4b_path,
                )


if __name__ == "__main__":
    unittest.main()
