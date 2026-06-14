import unittest

from src.award_interpreter import (
    ClauseNotFoundError,
    build_messages,
    flatten_clause,
    get_clause_node,
    load_sections,
)
from src.award_interpreter_prompt import PSEUDOCODE_FIELDS, SYSTEM_PROMPT


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

    def test_missing_clause_reference_raises_clear_error(self):
        with self.assertRaisesRegex(ClauseNotFoundError, "Clause reference not found: 999.9"):
            get_clause_node("999.9", self.sections)

    def test_system_prompt_lists_pseudocode_fields(self):
        for field in PSEUDOCODE_FIELDS:
            self.assertIn(field, SYSTEM_PROMPT)

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


if __name__ == "__main__":
    unittest.main()
