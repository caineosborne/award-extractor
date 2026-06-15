import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core_overtime_pseudocode import (
    DEFAULT_MODEL,
    PSEUDOCODE_FIELDS,
    build_messages,
    first_top_level_bullets,
    generate_core_overtime_pseudocode,
    output_path_for_summary,
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
            output_path_for_summary(Path("data/processed/MA000018_overtime_entitlements.md")),
            Path("data/processed/MA000018_core_overtime_pseudocode.md"),
        )

    def test_build_messages_include_available_fields_and_constraints(self):
        messages = build_messages("summary.md", "- Full-time employees...")

        for field, description in PSEUDOCODE_FIELDS.items():
            self.assertIn(field, messages[0]["content"])
            self.assertIn(description, messages[0]["content"])
        self.assertIn("any hours that are not ordinary hours are overtime", messages[0]["content"])
        self.assertIn("Only use the supplied first five entitlement bullets", messages[0]["content"])
        self.assertIn("Required additional inputs", messages[0]["content"])
        self.assertIn("- Full-time employees...", messages[1]["content"])

    def test_generate_core_overtime_pseudocode_writes_markdown_with_mocked_client(self):
        summary = """# Overtime

- Full-time rule.
- Part-time rule:
  - over 38 hours
- Casual rule.
- Day worker span rule.
- Weekend/public holiday rule.
- Meal break rule.
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

        self.assertEqual(result, written)
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertNotIn("Meal break rule", fake_client.responses.calls[0]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
