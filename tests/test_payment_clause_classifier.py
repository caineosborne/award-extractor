import json
import tempfile
import unittest
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from src.payment_clause_classifier import (
    DEFAULT_MODEL,
    SCHEMA_VERSION,
    PaymentClauseClassifierError,
    classify_award,
    collect_descendants,
    flatten_clause,
    iter_top_level_groups,
    output_path_for_award,
    timestamped_output_path,
    validate_group_classification,
)
from src.payment_clause_classifier_prompt import (
    ALLOWED_TAGS,
    DEFINITIONS,
    SYSTEM_PROMPT,
    build_user_prompt,
)


class FakeResponses:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return SimpleNamespace(output_text=json.dumps(payload))


class FakeClient:
    def __init__(self, payloads):
        self.responses = FakeResponses(payloads)


def award_with_clause(reference, title, children):
    return OrderedDict(
        [
            (
                "Part 1",
                OrderedDict(
                    [
                        ("_content", []),
                        (reference, OrderedDict([("_content", [title]), *children])),
                    ]
                ),
            )
        ]
    )


class PaymentClauseClassifierTests(unittest.TestCase):
    def test_collects_direct_l2_references_and_flattens_their_subtrees(self):
        node = OrderedDict(
            [
                ("_content", ["Breaks"]),
                (
                    "24.1",
                    OrderedDict(
                        [
                            ("_content", ["Meal breaks"]),
                            ("a", OrderedDict([("_content", ["Take a meal break."])])),
                            ("b", OrderedDict([("_content", ["Paid at overtime."])])),
                        ]
                    ),
                ),
            ]
        )

        descendants = collect_descendants("24", node)

        self.assertEqual([item.reference for item in descendants], ["24.1"])
        self.assertIn("24.1(a): Take a meal break.", descendants[0].text)
        self.assertIn("24.1(a): Take a meal break.", flatten_clause("24.1", node["24.1"]))

    def test_iter_top_level_groups_uses_full_award_json_parts(self):
        award = OrderedDict(
            [
                (
                    "Part 1",
                    OrderedDict(
                        [
                            ("_content", []),
                            ("1", OrderedDict([("_content", ["Title"])])),
                            (
                                "2",
                                OrderedDict(
                                    [
                                        ("_content", ["Wages"]),
                                        ("2.1", OrderedDict([("_content", ["Minimum rate."])])),
                                    ]
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )

        groups = iter_top_level_groups(award)

        self.assertEqual([group.reference for group in groups], ["1", "2"])
        self.assertEqual(groups[1].descendants[0].reference, "2.1")

    def test_validate_group_classification_accepts_payment_only_l1(self):
        group = iter_top_level_groups(
            award_with_clause(
                "14",
                "Minimum wages",
                [("14.1", OrderedDict([("_content", ["Base hourly rate."])]))],
            )
        )[0]
        classification = {
            "top_level_clause": {
                "reference": "14",
                "title": "Minimum wages",
                "payment_relevant": True,
                "definition_relevant": False,
                "requires_l2_classification": True,
                "reason": "Sets base rates.",
            },
            "classified_clauses": [
                {
                    "reference": "14.1",
                    "tags": ["Hourly Rate"],
                    "reason": "Determines base hourly rate.",
                }
            ],
        }

        top_result, classified = validate_group_classification(group, classification)

        self.assertTrue(top_result["payment_relevant"])
        self.assertFalse(top_result["definition_relevant"])
        self.assertTrue(top_result["requires_l2_classification"])
        self.assertEqual(classified["14.1"]["tags"], ["Hourly Rate"])

    def test_validate_group_classification_accepts_definition_only_l1(self):
        group = iter_top_level_groups(
            award_with_clause(
                "3",
                "Definitions",
                [("3.1", OrderedDict([("_content", ["shiftworker means ..."])]))],
            )
        )[0]

        top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "3",
                    "title": "Definitions",
                    "payment_relevant": False,
                    "definition_relevant": True,
                    "requires_l2_classification": True,
                    "reason": "Defines payroll terms.",
                },
                "classified_clauses": [
                    {
                        "reference": "3.1",
                        "tags": ["Definition"],
                        "reason": "Defines shiftworker.",
                    }
                ],
            },
        )

        self.assertFalse(top_result["payment_relevant"])
        self.assertTrue(top_result["definition_relevant"])
        self.assertEqual(classified["3.1"]["tags"], ["Definition"])

    def test_validate_group_classification_accepts_l1_and_l2_that_are_both_payment_and_definition(self):
        group = iter_top_level_groups(
            award_with_clause(
                "10",
                "Employment categories",
                [("10.1", OrderedDict([("_content", ["Full-time employees work 38 ordinary hours."])]))],
            )
        )[0]

        top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "10",
                    "title": "Employment categories",
                    "payment_relevant": True,
                    "definition_relevant": True,
                    "requires_l2_classification": False,
                    "reason": "Defines employee categories and ordinary hours.",
                },
                "classified_clauses": [
                    {
                        "reference": "10.1",
                        "tags": ["Definition", "Ordinary Hours & Overtime"],
                        "reason": "Defines full-time ordinary hours.",
                    }
                ],
            },
        )

        self.assertTrue(top_result["requires_l2_classification"])
        self.assertEqual(
            classified["10.1"]["tags"],
            ["Definition", "Ordinary Hours & Overtime"],
        )

    def test_validate_group_classification_rejects_classified_clauses_when_l1_is_neither(self):
        group = iter_top_level_groups(
            award_with_clause(
                "1",
                "Title",
                [("1.1", OrderedDict([("_content", ["This award is named ..."])]))],
            )
        )[0]

        with self.assertRaisesRegex(PaymentClauseClassifierError, "not payment or definition"):
            validate_group_classification(
                group,
                {
                    "top_level_clause": {
                        "reference": "1",
                        "title": "Title",
                        "payment_relevant": False,
                        "definition_relevant": False,
                        "requires_l2_classification": True,
                        "reason": "Title only.",
                    },
                    "classified_clauses": [
                        {
                            "reference": "1.1",
                            "tags": ["Definition"],
                            "reason": "Should not be returned.",
                        }
                    ],
                },
            )

    def test_validate_group_classification_rejects_unknown_or_nested_clause_references(self):
        group = iter_top_level_groups(
            award_with_clause(
                "25",
                "Penalty rates",
                [
                    (
                        "25.1",
                        OrderedDict(
                            [
                                ("_content", ["Paid at 125%."]),
                                ("a", OrderedDict([("_content", ["Nested detail."])])),
                            ]
                        ),
                    )
                ],
            )
        )[0]

        with self.assertRaisesRegex(PaymentClauseClassifierError, "Unknown classified clause"):
            validate_group_classification(
                group,
                {
                    "top_level_clause": {
                        "reference": "25",
                        "title": "Penalty rates",
                        "payment_relevant": True,
                        "definition_relevant": False,
                        "requires_l2_classification": True,
                        "reason": "Changes amount paid.",
                    },
                    "classified_clauses": [
                        {
                            "reference": "25.1(a)",
                            "tags": ["Penalty"],
                            "reason": "Nested references are not valid classified outputs.",
                        }
                    ],
                },
            )

    def test_prompt_includes_definitions_and_allowed_tags(self):
        for tag in ALLOWED_TAGS:
            self.assertIn(tag, SYSTEM_PROMPT)
        self.assertIn("ordinary hours", DEFINITIONS)
        self.assertIn("shiftworker", SYSTEM_PROMPT)
        self.assertIn("Definition", SYSTEM_PROMPT)
        self.assertIn("Ordinary Hours & Overtime", SYSTEM_PROMPT)
        self.assertIn("L2 relevance is independent", SYSTEM_PROMPT)
        self.assertIn("Omit direct L2 clauses", SYSTEM_PROMPT)

        prompt = build_user_prompt({"top_level_clause": {"reference": "25"}})

        self.assertIn('"reference": "25"', prompt)

    def test_output_paths(self):
        self.assertEqual(
            output_path_for_award(Path("data/processed/MA000018.json")),
            Path("data/processed/payment_clause_identifier/MA000018_payment_classification.json"),
        )
        self.assertEqual(
            timestamped_output_path(
                Path("data/processed/payment_clause_identifier/MA000018_payment_classification.json"),
                datetime(2026, 6, 16, 15, 30, 12),
            ),
            Path(
                "data/processed/payment_clause_identifier/archive/"
                "MA000018_payment_classification_20260616_153012.json"
            ),
        )

    def test_classify_award_writes_prod_and_timestamped_json_with_mocked_client(self):
        award = OrderedDict(
            [
                (
                    "Part 1",
                    OrderedDict(
                        [
                            ("_content", []),
                            (
                                "14",
                                OrderedDict(
                                    [
                                        ("_content", ["Minimum wages"]),
                                        ("14.1", OrderedDict([("_content", ["Base hourly rate."])])),
                                    ]
                                ),
                            ),
                            (
                                "25",
                                OrderedDict(
                                    [
                                        ("_content", ["Overtime"]),
                                        ("25.1", OrderedDict([("_content", ["Paid at 150%."])])),
                                    ]
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )
        payloads = [
            {
                "top_level_clause": {
                    "reference": "14",
                    "title": "Minimum wages",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Sets base rates.",
                },
                "classified_clauses": [
                    {
                        "reference": "14.1",
                        "tags": ["Hourly Rate"],
                        "reason": "Base hourly rate.",
                    }
                ],
            },
            {
                "top_level_clause": {
                    "reference": "25",
                    "title": "Overtime",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Sets overtime boundaries.",
                },
                "classified_clauses": [
                    {
                        "reference": "25.1",
                        "tags": ["Ordinary Hours & Overtime"],
                        "reason": "Applies overtime.",
                    }
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            award_path = Path(temp_dir) / "award.json"
            output_path = Path(temp_dir) / "award_payment_classification.json"
            award_path.write_text(json.dumps(award), encoding="utf-8")

            result = classify_award(
                award_path=award_path,
                output_path=output_path,
                client=FakeClient(payloads),
            )

            written = json.loads(output_path.read_text(encoding="utf-8"))
            history_files = list(
                (Path(temp_dir) / "archive").glob("award_payment_classification_*.json")
            )

        self.assertEqual(result["model"], DEFAULT_MODEL)
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(written["schema_version"], "payment-classification-v2")
        self.assertEqual(written["classified_clauses"]["14.1"]["tags"], ["Hourly Rate"])
        self.assertEqual(
            written["classified_clauses"]["25.1"]["tags"],
            ["Ordinary Hours & Overtime"],
        )
        self.assertEqual(len(history_files), 1)


if __name__ == "__main__":
    unittest.main()
