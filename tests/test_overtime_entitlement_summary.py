import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.overtime_entitlement_summary import (
    DEFAULT_MODEL,
    build_messages,
    load_reference_template,
    output_path_for_interpretation,
    summarize_overtime_entitlements,
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
            Path("data/processed/4_overtime_entitlements/MA000018_overtime_entitlements.md"),
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
        self.assertIn("handled by separate extraction workflows", messages[0]["content"])
        self.assertIn("Use the supplied markdown template only as a style and structure reference", messages[0]["content"])
        self.assertIn("Do not copy the template's award-specific facts", messages[0]["content"])
        self.assertIn("# Source Rules", messages[0]["content"])
        self.assertIn("## Specific Rule Breakdown", messages[0]["content"])
        self.assertIn("# Overtime Interpretation", messages[0]["content"])
        self.assertIn("## Overtime Entitlements", messages[0]["content"])
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
        fake_client = FakeClient("# Overtime\n- Overtime applies after ordinary hours. (20.1)")

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
