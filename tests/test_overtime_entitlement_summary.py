import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_4a_summarize_overtime import (
    DEFAULT_MODEL,
    build_messages,
    load_reference_template,
    output_path_for_interpretation,
    resolve_interpretation_path,
    summarize_overtime_entitlements,
    strip_wrapping_markdown_fence,
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


class OvertimeEntitlementSummaryTests(unittest.TestCase):
    def test_output_path_for_interpretation(self):
        self.assertEqual(
            output_path_for_interpretation(
                Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md")
            ),
            Path("data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md"),
        )

    def test_output_path_for_revised_interpretation_uses_award_stem(self):
        self.assertEqual(
            output_path_for_interpretation(
                Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md")
            ),
            Path("data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md"),
        )

    def test_resolve_interpretation_path_prefers_revised_award_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            original_path = temp_path / "MA000999_overtime_interpretation.md"
            revised_path = temp_path / "MA000999_overtime_interpretation_revised.md"
            original_path.write_text("# Original", encoding="utf-8")
            revised_path.write_text("# Revised", encoding="utf-8")

            explicit_path = resolve_interpretation_path(revised_path)

        self.assertEqual(explicit_path, revised_path)

    def test_strip_wrapping_markdown_fence(self):
        self.assertEqual(
            strip_wrapping_markdown_fence("```markdown\n# Source Rules\n\n- Rule\n```"),
            "# Source Rules\n\n- Rule",
        )

    def test_build_messages_includes_glossary_and_interpretation_markdown(self):
        messages = build_messages(
            "interpretation.md",
            (
                "# Overtime Interpretation Working Document\n\n"
                "## When does overtime occur?\n\n"
                "Overtime starts after ordinary hours. [20.1]"
            ),
            "resources/overtime_example.md",
            "# Source Rules\n\n## Ordinary Hours Rules:\n\n- Template example only.",
        )

        self.assertIn("ordinary hours", messages[0]["content"])
        self.assertIn("overtime", messages[0]["content"])
        self.assertIn("Tag definitions:", messages[0]["content"])
        self.assertIn("The payment clause classifier is the source of truth for scope", messages[0]["content"])
        self.assertIn("Use only rules that belong to the Ordinary Hours & Overtime tag definition", messages[0]["content"])
        self.assertIn("Exclude penalty rates", messages[0]["content"])
        self.assertIn("broken shift rules", messages[0]["content"])
        self.assertIn("unless the interpretation document expressly includes them", messages[0]["content"])
        self.assertIn("do not treat them as overtime triggers", messages[0]["content"])
        self.assertIn("Use the supplied markdown template only as a style and structure reference", messages[0]["content"])
        self.assertIn("Do not copy the template's award-specific facts", messages[0]["content"])
        self.assertIn("# Source Rules", messages[0]["content"])
        self.assertIn("## Specific Rule Breakdown", messages[0]["content"])
        self.assertIn("# Overtime Interpretation", messages[0]["content"])
        self.assertIn("## Overtime Entitlements", messages[0]["content"])
        self.assertIn("Initially allocate every worked hour as `Unallocated`", messages[0]["content"])
        self.assertIn("Apply time-based overtime checks first", messages[0]["content"])
        self.assertIn("Apply daily overtime checks next", messages[0]["content"])
        self.assertIn("Apply weekly or averaging-period overtime checks after that", messages[0]["content"])
        self.assertIn("Do not wrap the answer in a markdown code fence", messages[0]["content"])
        self.assertIn("Do not write \"All employees\"", messages[0]["content"])
        self.assertIn("Reference template: resources/overtime_example.md", messages[1]["content"])
        self.assertIn("Template example only.", messages[1]["content"])
        self.assertIn("Do not copy its award-specific facts", messages[1]["content"])
        self.assertIn("Source overtime interpretation working document", messages[1]["content"])
        self.assertIn("Overtime starts after ordinary hours. [20.1]", messages[1]["content"])

    def test_load_reference_template_reads_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "template.md"
            template_path.write_text("# Source Rules\n\n- Example pattern.", encoding="utf-8")

            result = load_reference_template(template_path)

        self.assertIn("Example pattern", result)

    def test_summarize_overtime_entitlements_writes_markdown_with_mocked_client(self):
        interpretation = (
            "# Overtime Interpretation Working Document\n\n"
            "## When does overtime occur?\n\n"
            "Overtime applies after ordinary hours. [20.1]"
        )
        fake_client = FakeClient(
            "```markdown\n# Overtime\n- Overtime applies after ordinary hours. (20.1)\n```"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_overtime_interpretation.md"
            output_path = Path(temp_dir) / "award_overtime_entitlements.md"
            input_path.write_text(interpretation, encoding="utf-8")

            result = summarize_overtime_entitlements(
                interpretation_path=input_path,
                output_path=output_path,
                template_path=Path("resources/overtime_example.md"),
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_entitlements_*.md")
            )

        self.assertEqual(result, "# Overtime\n- Overtime applies after ordinary hours. (20.1)")
        self.assertEqual(result, written)
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertIn(
            "Overtime applies after ordinary hours. [20.1]",
            fake_client.responses.calls[0]["input"][1]["content"],
        )
        self.assertIn(
            "# Source Rules",
            fake_client.responses.calls[0]["input"][1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
