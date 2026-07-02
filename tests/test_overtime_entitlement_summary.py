import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET
from src.prompts.step_4_1_format_ruleset import build_messages
from src.step_4_1_format_ruleset import (
    DEFAULT_MODEL,
    DEFAULT_TEMPLATE_PATH,
    load_text_file,
    output_path_for_interpretation,
    resolve_interpretation_path,
    strip_validation_notes_preamble,
    strip_wrapping_markdown_fence,
    summarize_overtime_entitlements,
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
    def test_output_path_for_revised_interpretation_uses_award_stem(self):
        result = output_path_for_interpretation(
            Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md")
        )

        self.assertEqual(
            result,
            Path("data/processed/MA000018/MA000018_overtime_entitlements.md"),
        )

    def test_output_path_for_ruleset_revised_interpretation_keeps_ruleset_isolation(self):
        result = output_path_for_interpretation(
            Path("data/processed/MA000018/MA000018_overtime_consequence_ruleset_revised.md")
        )

        self.assertEqual(
            result,
            Path(
                "data/processed/MA000018/MA000018_overtime_consequence_ruleset_overtime_entitlements.md"
            ),
        )

    def test_resolve_interpretation_path_supports_ruleset_award_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            award_dir = project_root / "data" / "processed" / "MA000999"
            award_dir.mkdir(parents=True)
            revised_path = award_dir / "MA000999_overtime_consequence_ruleset_revised.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            from unittest.mock import patch

            with patch("src.step_4_1_format_ruleset.deterministic.PROJECT_ROOT", project_root):
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
            "- Clause 19.2 was not represented.\n\n"
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
            "Template.md",
            "# Overtime Triggers\n\n## All Employees\n-",
            "overtime_creation",
        )

        self.assertIn("reviewed overtime ruleset", messages[0]["content"])
        self.assertIn(
            "Write each rule as clearly and operationally as possible",
            messages[0]["content"],
        )
        self.assertIn(
            "Keep clause references visible in every rule bullet",
            messages[0]["content"],
        )
        self.assertIn("Reviewed ruleset source: interpretation.md", messages[1]["content"])
        self.assertIn("After 38 hours in a week. [20.1]", messages[1]["content"])
        self.assertIn("# Overtime Triggers", messages[1]["content"])
        self.assertIn("Only include a heading", messages[1]["content"])
        self.assertIn("Do not add headings outside this structure", messages[1]["content"])
        self.assertIn(
            "Preserve ordinary-hours boundary rules clearly and explicitly",
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
            "Template.md",
            "# unused",
            OVERTIME_CONSEQUENCE_RULESET,
        )

        self.assertIn("# Overtime Consequences", messages[1]["content"])
        self.assertIn(
            "what is paid, owed, or applied once overtime already exists",
            messages[1]["content"],
        )
        self.assertIn("weekend/public-holiday overtime consequences", messages[1]["content"])
        self.assertIn(
            "Keep the actual multiplier, block, minimum payment, entitlement, and cohort condition in the bullet text itself.",
            messages[1]["content"],
        )
        self.assertIn(
            "Place each rule under the most specific supported heading, not under `### Other` by default.",
            messages[1]["content"],
        )

    def test_load_text_file_reads_template_markdown(self):
        template_text = load_text_file(DEFAULT_TEMPLATE_PATH, "Template markdown")

        self.assertIn("# Overtime Triggers", template_text)
        self.assertIn("## Special Circumstances", template_text)

    def test_summarize_overtime_entitlements_writes_formatted_markdown(self):
        interpretation = (
            "# Validation notes\n\n"
            "- Clause 19.2 was not represented.\n\n"
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
        self.assertIn("award_overtime_interpretation_revised.md", fake_client.responses.calls[0]["input"][1]["content"])
        self.assertNotIn("Clause 19.2 was not represented.", fake_client.responses.calls[0]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
