import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_5b_generate_overtime_pseudocode import (
    DEFAULT_MODEL,
    PSEUDOCODE_FIELDS,
    build_messages,
    default_overtime_interpretation_path,
    first_top_level_bullets,
    generate_core_overtime_pseudocode,
    load_overtime_interpretation,
    output_path_for_summary,
    overtime_rule_bullets,
    select_overtime_interpretation_path,
)


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


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
            Path("data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md"),
        )

    def test_output_path_for_summary_uses_4b_source_when_present(self):
        self.assertEqual(
            output_path_for_summary(
                Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_4b.md")
            ),
            Path("data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md"),
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
        self.assertIn("Do not rely on a rule having an exact markdown heading", messages[0]["content"])
        self.assertIn("Required additional inputs", messages[0]["content"])
        self.assertIn(
            "Do not list a derived field that is just a renamed component of an existing field",
            messages[0]["content"],
        )
        self.assertIn(
            "totals such as hours worked in the day, week, or fortnight",
            messages[0]["content"],
        )
        self.assertIn(
            "Treat `Required additional inputs` narrowly",
            messages[0]["content"],
        )
        self.assertIn("Complete overtime interpretation markdown to convert", messages[1]["content"])
        self.assertIn("Daily excess rule", messages[1]["content"])
        self.assertIn("Clause interpretation table", messages[1]["content"])

    def test_select_overtime_interpretation_path_falls_back_from_4b_to_revised(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            manual_4b_path = source_dir / "award_overtime_interpretation_4b.md"
            revised_path = source_dir / "award_overtime_interpretation_revised.md"
            revised_path.write_text("# Revised", encoding="utf-8")

            selected_path = select_overtime_interpretation_path(manual_4b_path)

        self.assertEqual(selected_path, revised_path)

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

        self.assertEqual(result, written)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn(
            "Meal break note",
            fake_client.responses.calls[0]["input"][1]["content"],
        )

    def test_default_overtime_interpretation_path_prefers_4b_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            interpretation_dir = (
                project_root / "data" / "processed" / "3_overtime_interpretations"
            )
            interpretation_dir.mkdir(parents=True)

            manual_4b_path = interpretation_dir / "MA000018_overtime_interpretation_4b.md"
            revised_path = (
                interpretation_dir / "MA000018_overtime_interpretation_revised.md"
            )
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

                manual_4b_path.write_text("# 4B", encoding="utf-8")
                self.assertEqual(
                    default_overtime_interpretation_path("MA000018"),
                    manual_4b_path,
                )


if __name__ == "__main__":
    unittest.main()
