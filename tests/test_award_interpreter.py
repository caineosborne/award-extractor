import unittest
from types import SimpleNamespace

from src.Archive.award_interpreter import (
    ClauseNotFoundError,
    build_messages,
    extract_response_text,
    flatten_clause,
    get_clause_node,
    load_sections,
    lookup_clause_text,
)
from src.Archive.award_interpreter_prompt import PSEUDOCODE_FIELDS, SYSTEM_PROMPT


class AwardInterpreterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = load_sections()

    def test_lookup_and_flatten_clause(self):
        sections = {
            "24.1": {
                "_content": ["Meal breaks"],
                "a": {
                    "_content": [
                        "Each employee who works in excess of five hours receives a meal break."
                    ]
                },
                "b": {
                    "_content": [
                        "Employees required to remain available during a meal break are paid overtime."
                    ]
                },
            }
        }
        clause_node = get_clause_node("24.1", sections)
        clause_text = flatten_clause("24.1", clause_node)

        self.assertIn("24.1: Meal breaks", clause_text)
        self.assertIn("24.1(a): Each employee who works in excess of five hours", clause_text)
        self.assertIn("24.1(b): Employees required to remain available", clause_text)

    def test_lookup_clause_text_loads_and_flattens_from_index(self):
        clause_text = lookup_clause_text("24.1")

        self.assertIn("24.1:", clause_text)
        self.assertGreater(len(clause_text), 20)

    def test_missing_clause_reference_raises_clear_error(self):
        with self.assertRaisesRegex(ClauseNotFoundError, "Clause reference not found: 999.9"):
            get_clause_node("999.9", self.sections)

    def test_system_prompt_lists_pseudocode_fields(self):
        for field, description in PSEUDOCODE_FIELDS.items():
            self.assertIn(field, SYSTEM_PROMPT)
            self.assertIn(description, SYSTEM_PROMPT)

    def test_messages_include_guidelines(self):
        messages = build_messages(
            "24.1",
            "24.1: Meal breaks",
            "Focus on shift-based inputs.",
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("Clause reference: 24.1", messages[1]["content"])
        self.assertIn("Focus on shift-based inputs.", messages[1]["content"])

    def test_extract_response_text_prefers_output_text(self):
        response = SimpleNamespace(output_text="Direct output")

        self.assertEqual(extract_response_text(response), "Direct output")

    def test_extract_response_text_handles_nested_response_output(self):
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(text="First block"),
                        SimpleNamespace(text="Second block"),
                    ]
                )
            ]
        )

        self.assertEqual(extract_response_text(response), "First block\nSecond block")


if __name__ == "__main__":
    unittest.main()
