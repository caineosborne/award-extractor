import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from src.common.output_naming import formatted_ruleset_path_for_ruleset
from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET, PENALTIES_RULESET
from src.prompts.step_4_1_format_ruleset import build_messages
from src.step_4_1_format_ruleset.run import summarize_overtime_entitlements
from src.step_4_1_format_ruleset.schema import (
    DEFAULT_MODEL,
    DEFAULT_CONSEQUENCE_TEMPLATE_PATH,
    DEFAULT_TEMPLATE_PATH,
)
from src.step_4_1_format_ruleset.step_1_load_inputs import (
    load_text_file,
    resolve_interpretation_path,
    resolve_formatting_inputs,
    strip_validation_notes_preamble,
    strip_wrapping_markdown_fence,
)
from src.step_4_1_format_ruleset.step_2_format_ruleset import (
    append_missing_rules_catch_all,
    extract_markdown_bullets,
    rule_is_represented_in_output,
)


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text: str):
        self.responses = FakeResponses(output_text)


class OvertimeEntitlementSummaryTests(unittest.TestCase):
    def test_extract_markdown_bullets_keeps_nested_rule_details_with_parent(self):
        rules = extract_markdown_bullets(
            "- Apply overtime after the daily limit. [13.7]\n"
            "  - Day shift: 8 hours.\n"
            "  - Night shift: 10 hours.\n"
            "- Apply overtime after 38 hours per week. [13.2]"
        )

        self.assertEqual(
            rules,
            [
                "Apply overtime after the daily limit. [13.7] Day shift: 8 hours. Night shift: 10 hours.",
                "Apply overtime after 38 hours per week. [13.2]",
            ],
        )

    def test_rule_coverage_allows_one_reviewed_rule_to_be_split_across_output(self):
        source_rule = (
            "An afternoon shift finishes after 7 pm and a night shift finishes after "
            "midnight. [31.2]"
        )
        formatted_rules = [
            "Afternoon shift finishes after 7 pm. [31.2]",
            "Night shift finishes after midnight. [31.2]",
        ]

        self.assertTrue(rule_is_represented_in_output(source_rule, formatted_rules))

    def test_formatted_ruleset_path_for_creation_ruleset_uses_canonical_name(self):
        result = formatted_ruleset_path_for_ruleset(
            Path("data/processed/MA000018/3_2_OT_creation_revised_ruleset.md"),
            "overtime_creation",
        )

        self.assertEqual(
            result,
            Path("data/processed/MA000018/4_1_OT_creation_formatted_ruleset.md"),
        )

    def test_formatted_ruleset_path_for_consequence_ruleset_keeps_canonical_isolation(self):
        result = formatted_ruleset_path_for_ruleset(
            Path("data/processed/MA000018/3_2_OT_consequence_revised_ruleset.md"),
            OVERTIME_CONSEQUENCE_RULESET,
        )

        self.assertEqual(
            result,
            Path("data/processed/MA000018/4_1_OT_consequence_formatted_ruleset.md"),
        )

    def test_resolve_interpretation_path_supports_ruleset_award_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            award_dir = project_root / "data" / "processed" / "MA000999"
            award_dir.mkdir(parents=True)
            revised_path = award_dir / "3_2_OT_consequence_revised_ruleset.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            from unittest.mock import patch

            with patch("src.step_4_1_format_ruleset.step_1_load_inputs.PROJECT_ROOT", project_root):
                result = resolve_interpretation_path(
                    "MA000999",
                    OVERTIME_CONSEQUENCE_RULESET,
                )

        self.assertEqual(result, revised_path)

    def test_resolve_interpretation_path_returns_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            revised_path = Path(temp_dir) / "MA000999_overtime_interpretation_revised.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            result = resolve_interpretation_path(revised_path)

        self.assertEqual(result, revised_path)

    def test_strip_wrapping_markdown_fence(self):
        result = strip_wrapping_markdown_fence("```markdown\n# Overtime Triggers\n\n- Rule\n```")

        self.assertEqual(result, "# Overtime Triggers\n\n- Rule")

    def test_strip_validation_notes_preamble_keeps_only_rule_sections(self):
        source_text = (
            "# Validation notes\n\n"
            "## Action required\n\n"
            "- Clause 19.2 was not represented.\n\n"
            "## Review notes\n\n"
            "- A merged rule was retained conservatively.\n\n"
            "## All employees\n\n"
            "- After 38 hours per week. [20.1]\n"
        )

        result = strip_validation_notes_preamble(source_text)

        self.assertEqual(
            result,
            "## All employees\n\n- After 38 hours per week. [20.1]",
        )

    def test_build_messages_uses_interpretation_and_template_sources(self):
        messages = build_messages(
            "interpretation.md",
            "## All employees\n\n- After 38 hours in a week. [20.1]",
            "Templates/Template.md",
            "# Overtime Triggers\n\n## All Employees\n-",
            "overtime_creation",
        )

        self.assertIn("reviewed payroll ruleset", messages[0]["content"])
        self.assertIn("presentation rewrite", messages[0]["content"])
        self.assertIn(
            "Start every top-level bullet with the direct payroll rule or outcome",
            messages[0]["content"],
        )
        self.assertIn(
            "Overtime is created when an employee works more than the daily limit",
            messages[1]["content"],
        )
        self.assertIn(
            "If the reviewed 3.2 rule is already understandable, retain its sentence",
            messages[0]["content"],
        )
        self.assertIn(
            "Do not expand a reviewed rule into an explanation",
            messages[0]["content"],
        )
        self.assertIn(
            "Keep clause references at the end of the lead bullet",
            messages[0]["content"],
        )
        self.assertIn("Reviewed ruleset content:", messages[1]["content"])
        self.assertNotIn("interpretation.md", messages[1]["content"])
        self.assertNotIn("Template source:", messages[1]["content"])
        self.assertIn("Core template structure", messages[1]["content"])
        self.assertIn("After 38 hours in a week. [20.1]", messages[1]["content"])
        self.assertIn("# Overtime Triggers", messages[1]["content"])
        self.assertIn("## All Employees", messages[1]["content"])
        self.assertIn("Only include a heading", messages[1]["content"])
        self.assertIn("Do not add headings outside this structure", messages[1]["content"])
        self.assertIn(
            "Preserve ordinary-hours boundary rules clearly where work outside",
            messages[1]["content"],
        )
        self.assertIn(
            "Keep the actual operative numbers and conditions in the bullet text",
            messages[1]["content"],
        )
        self.assertIn(
            "Place each rule under the most specific supported heading, not under `Other` by default.",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not place a general rule in `### Other` merely because it was added during review or evaluator feedback.",
            messages[1]["content"],
        )

    def test_build_messages_supports_consequence_ruleset_formatting(self):
        messages = build_messages(
            "interpretation.md",
            "## All employees\n\n- Overtime on Sunday is paid at double time. [23.5]",
            "Templates/Template.md",
            "# unused",
            OVERTIME_CONSEQUENCE_RULESET,
        )

        self.assertNotIn("Template source:", messages[1]["content"])
        self.assertIn("# Overtime Consequences", messages[1]["content"])
        self.assertIn("## Full-Time And Part-Time Employees", messages[1]["content"])
        self.assertIn(
            "what is paid, owed, or applied once overtime already exists",
            messages[1]["content"],
        )
        self.assertIn("This is a presentation rewrite, not a new interpretation.", messages[0]["content"])
        self.assertIn("The output must be lossless in substance", messages[0]["content"])
        self.assertIn("Do not delete, omit, merge, generalise, or invent substantive rules.", messages[0]["content"])
        self.assertIn("Do not add new operational claims, even if they seem implied by the source.", messages[1]["content"])
        self.assertIn("weekend/public-holiday overtime consequences", messages[1]["content"])
        self.assertIn(
            "Keep the actual multiplier, block, minimum payment, entitlement, and cohort condition in the bullet text itself.",
            messages[1]["content"],
        )
        self.assertIn(
            "Every award is expected to have a clause stating the overtime rates for the main employee cohorts.",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not include standalone commentary on what creates overtime.",
            messages[1]["content"],
        )
        self.assertIn(
            "Place each rule under the most specific supported heading, not under `### Other` by default.",
            messages[1]["content"],
        )

    def test_build_messages_supports_penalties_ruleset_formatting(self):
        messages = build_messages(
            "interpretation.md",
            "## Shift-Based Allowances And Penalties\n\n- Night shift commencing at 4.00 pm and before 4.00 am is paid at 115% for the entire shift. [26.1(c)]",
            "Templates/Template.md",
            "# unused",
            PENALTIES_RULESET,
        )

        self.assertIn("# Penalties", messages[1]["content"])
        self.assertIn("## Shift-Based Allowances And Penalties", messages[1]["content"])
        self.assertIn("## Breaks Between Work Periods", messages[1]["content"])
        self.assertIn(
            "Keep whole-shift qualification rules separate from specific-hours rules",
            messages[1]["content"],
        )
        self.assertIn("Keep non-financial break-gap rules representable", messages[1]["content"])

    def test_load_text_file_reads_template_markdown(self):
        template_text = load_text_file(DEFAULT_TEMPLATE_PATH, "Template markdown")

        self.assertIn("# Overtime Triggers", template_text)
        self.assertIn("## Special Circumstances", template_text)

    def test_load_text_file_reads_consequence_template_markdown(self):
        template_text = load_text_file(
            DEFAULT_CONSEQUENCE_TEMPLATE_PATH,
            "Consequence template markdown",
        )

        self.assertIn("# Overtime Consequences", template_text)
        self.assertIn("## Full-Time And Part-Time Employees", template_text)

    def test_resolve_formatting_inputs_uses_consequence_template_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            interpretation_path = (
                Path(temp_dir) / "3_2_OT_consequence_revised_ruleset.md"
            )
            interpretation_path.write_text(
                "# Overtime Consequences\n\n- Overtime is paid at 150%. [23.1]",
                encoding="utf-8",
            )

            inputs = resolve_formatting_inputs(
                interpretation_path=interpretation_path,
                ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
            )

        self.assertEqual(inputs.template_path, DEFAULT_CONSEQUENCE_TEMPLATE_PATH)
        self.assertIn("# Overtime Consequences", inputs.template_markdown)

    def test_summarize_overtime_entitlements_writes_formatted_markdown(self):
        interpretation = (
            "# Validation notes\n\n"
            "## Action required\n\n"
            "- Clause 19.2 was not represented.\n\n"
            "## Review notes\n\n"
            "- A merged rule was retained conservatively.\n\n"
            "## All employees\n\n"
            "- Overtime applies after 38 hours per week. [20.1]\n"
        )
        fake_client = FakeClient(
            "```markdown\n# Overtime Triggers\n\n## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)\n- After 38 hours per week. [20.1]\n```"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation_revised.md"
            output_path = temp_path / "award_overtime_entitlements.md"
            interpretation_path.write_text(interpretation, encoding="utf-8")

            result = summarize_overtime_entitlements(
                interpretation_path=interpretation_path,
                output_path=output_path,
                client=fake_client,
            )

            written_output = output_path.read_text(encoding="utf-8")
        self.assertEqual(
            result,
            "# Overtime Triggers\n\n## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)\n- After 38 hours per week. [20.1]",
        )
        self.assertEqual(written_output, result)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertEqual(
            fake_client.responses.calls[0]["reasoning"],
            {"effort": "medium"},
        )
        self.assertNotIn(
            "award_overtime_interpretation_revised.md",
            fake_client.responses.calls[0]["input"][1]["content"],
        )
        self.assertNotIn("Clause 19.2 was not represented.", fake_client.responses.calls[0]["input"][1]["content"])

    def test_summarize_overtime_entitlements_records_warning_for_dropped_reviewed_rule(self):
        interpretation = (
            "## Full-time employees\n\n"
            "- For a full-time employee, any work performed in addition to the employee's rostered ordinary hours on any day is overtime. [25.1(a)(i)]\n\n"
            "## Ordinary hours daily limits\n\n"
            "- Ordinary hours under clause 22.1 may be worked as eight hours on a day shift or 10 hours on a night shift. Please test whether hours beyond those daily ordinary-hours limits should be treated as overtime for the relevant cohort and roster arrangement. [22.1(c)]\n"
        )
        fake_client = FakeClient(
            "# Overtime Triggers\n\n"
            "## Full-Time Employees Only\n"
            "- For a full-time employee, any work performed in addition to the employee's rostered ordinary hours on any day is overtime. [25.1(a)(i)]\n"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "3_2_OT_creation_revised_ruleset.md"
            output_path = temp_path / "4_1_OT_creation_formatted_ruleset.md"
            interpretation_path.write_text(interpretation, encoding="utf-8")
            validation_warnings: list[str] = []

            result = summarize_overtime_entitlements(
                interpretation_path=interpretation_path,
                output_path=output_path,
                client=fake_client,
                validation_warnings_output=validation_warnings,
            )

            written_output = output_path.read_text(encoding="utf-8")
            metadata_path = output_path.with_name(f"{output_path.stem}_metadata.json")
            written_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(result, written_output)
        self.assertEqual(len(validation_warnings), 1)
        self.assertIn(
            "Step 4.1 formatted output may have dropped this reviewed rule",
            validation_warnings[0],
        )
        self.assertIn(
            "eight hours on a day shift or 10 hours on a night shift",
            validation_warnings[0],
        )
        self.assertEqual(written_metadata["rendered_markdown"], written_output)
        self.assertEqual(written_metadata["validation_warnings"], validation_warnings)
        self.assertIn("## Reviewed rules omitted by the formatter", written_output)
        self.assertIn(
            "eight hours on a day shift or 10 hours on a night shift",
            written_output,
        )

    def test_append_missing_rules_catch_all_keeps_the_reviewed_rule_verbatim(self):
        warning = (
            "Step 4.1 formatted output may have dropped this reviewed rule instead "
            "of only formatting it: Casual Sunday overtime is 250%. [25.1(c)]"
        )

        result = append_missing_rules_catch_all("# Penalties\n", [warning])

        self.assertIn("## Reviewed rules omitted by the formatter", result)
        self.assertIn("- Casual Sunday overtime is 250%. [25.1(c)]", result)


if __name__ == "__main__":
    unittest.main()
