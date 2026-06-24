import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_4a_summarize_overtime import (
    DEFAULT_MODEL,
    DEFAULT_TEMPLATE_PATH,
    build_messages,
    load_text_file,
    output_path_for_interpretation,
    resolve_interpretation_path,
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
            Path("data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md"),
        )

    def test_resolve_interpretation_path_returns_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            revised_path = Path(temp_dir) / "MA000999_overtime_interpretation_revised.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            result = resolve_interpretation_path(revised_path)

        self.assertEqual(result, revised_path)

    def test_strip_wrapping_markdown_fence(self):
        result = strip_wrapping_markdown_fence("```markdown\n# Overtime Triggers\n\n- Rule\n```")

        self.assertEqual(result, "# Overtime Triggers\n\n- Rule")

    def test_build_messages_uses_interpretation_and_template_sources(self):
        messages = build_messages(
            "interpretation.md",
            "## All employees\n\n- After 38 hours in a week. [20.1]",
            "Template.md",
            "# Overtime Triggers\n\n## All Employees\n-",
        )

        self.assertIn("human-readable overtime guide", messages[0]["content"])
        self.assertIn("Interpretation source: interpretation.md", messages[1]["content"])
        self.assertIn("Template source: Template.md", messages[1]["content"])
        self.assertIn("After 38 hours in a week. [20.1]", messages[1]["content"])
        self.assertIn("# Overtime Triggers", messages[1]["content"])
        self.assertIn("Use the template headings exactly as provided", messages[1]["content"])

    def test_load_text_file_reads_template_markdown(self):
        template_text = load_text_file(DEFAULT_TEMPLATE_PATH, "Template markdown")

        self.assertIn("# Overtime Triggers", template_text)
        self.assertIn("## Special Circumstances", template_text)

    def test_summarize_overtime_entitlements_writes_formatted_markdown(self):
        interpretation = (
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
            archive_files = list((temp_path / "archive").glob("award_overtime_entitlements_*.md"))

        self.assertEqual(
            result,
            "# Overtime Triggers\n\n## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)\n- After 38 hours per week. [20.1]",
        )
        self.assertEqual(written_output, result)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn("award_overtime_interpretation_revised.md", fake_client.responses.calls[0]["input"][1]["content"])
        self.assertIn("Template.md", fake_client.responses.calls[0]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
