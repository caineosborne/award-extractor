import json
import tempfile
import unittest
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from src.script_2_classify_payments import (
    DEFAULT_MODEL,
    SCHEMA_VERSION,
    PaymentClauseClassifierError,
    classify_award,
    collect_descendants,
    direct_l2_reference_for,
    flatten_clause,
    has_substantive_l1_content,
    iter_top_level_groups,
    l1_body_text,
    output_path_for_award,
    timestamped_output_path,
    title_only_top_level_result,
    validate_group_classification,
)
from src.prompts.payment_clause_classification import (
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

    def test_substantive_l1_content_excludes_title_only_text(self):
        # Build this group directly because award_with_clause is for child-node cases.
        group = iter_top_level_groups(
            OrderedDict(
                [
                    (
                        "Part 1",
                        OrderedDict(
                            [
                                ("_content", []),
                                (
                                    "2",
                                    OrderedDict(
                                        [
                                            (
                                                "_content",
                                                [
                                                    "Definitions",
                                                    "minimum hourly rate means the minimum hourly rate prescribed in clause 16.",
                                                ],
                                            )
                                        ]
                                    ),
                                ),
                            ]
                        ),
                    )
                ]
            )
        )[0]
        stub_group = iter_top_level_groups(
            OrderedDict(
                [
                    (
                        "Part 7",
                        OrderedDict(
                            [
                                ("_content", []),
                                ("36", OrderedDict([("_content", ["Family and domestic violence leave"])])),
                            ]
                        ),
                    )
                ]
            )
        )[0]

        self.assertIn("minimum hourly rate", l1_body_text(group))
        self.assertTrue(has_substantive_l1_content(group))
        self.assertFalse(has_substantive_l1_content(stub_group))

    def test_validate_group_classification_accepts_substantive_l1_only_classification(self):
        group = iter_top_level_groups(
            OrderedDict(
                [
                    (
                        "Part 1",
                        OrderedDict(
                            [
                                ("_content", []),
                                (
                                    "2",
                                    OrderedDict(
                                        [
                                            (
                                                "_content",
                                                [
                                                    "Definitions",
                                                    "minimum hourly rate means the minimum hourly rate prescribed in clause 16.",
                                                    "shiftworker means an employee to whom Part 6 applies.",
                                                ],
                                            )
                                        ]
                                    ),
                                ),
                            ]
                        ),
                    )
                ]
            )
        )[0]

        _top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "2",
                    "title": "Definitions",
                    "payment_relevant": True,
                    "definition_relevant": True,
                    "requires_l2_classification": True,
                    "reason": "Defines payroll terms.",
                },
                "classified_clauses": [
                    {
                        "reference": "2",
                        "tags": ["Definition", "Hourly Rate"],
                        "reason": "Contains payroll-relevant definitions.",
                    }
                ],
            },
        )

        self.assertEqual(classified["2"]["tags"], ["Definition", "Hourly Rate"])
        self.assertIn("minimum hourly rate", classified["2"]["text"])

    def test_validate_group_classification_rejects_title_only_l1_classification(self):
        group = iter_top_level_groups(
            OrderedDict(
                [
                    (
                        "Part 7",
                        OrderedDict(
                            [
                                ("_content", []),
                                ("36", OrderedDict([("_content", ["Family and domestic violence leave"])])),
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
                        "reference": "36",
                        "title": "Family and domestic violence leave",
                        "payment_relevant": True,
                        "definition_relevant": False,
                        "requires_l2_classification": True,
                        "reason": "Heading only.",
                    },
                    "classified_clauses": [
                        {
                            "reference": "36",
                            "tags": ["Leave"],
                            "reason": "Should not be classified from heading only.",
                        }
                    ],
                },
            )

    def test_title_only_top_level_result_is_not_payment_relevant(self):
        group = iter_top_level_groups(
            OrderedDict(
                [
                    (
                        "Part 7",
                        OrderedDict(
                            [
                                ("_content", []),
                                ("25A", OrderedDict([("_content", ["Parental leave and related entitlements"])])),
                            ]
                        ),
                    )
                ],
            )
        )[0]

        result = title_only_top_level_result(group)

        self.assertFalse(result["payment_relevant"])
        self.assertFalse(result["definition_relevant"])
        self.assertFalse(result["requires_l2_classification"])
        self.assertIn("only a heading", result["reason"])

    def test_classify_award_skips_title_only_top_level_groups(self):
        award = OrderedDict(
            [
                (
                    "Part 1",
                    OrderedDict(
                        [
                            ("_content", []),
                            ("25", OrderedDict([("_content", ["Personal/carer's leave"])])),
                            (
                                "27",
                                OrderedDict(
                                    [
                                        ("_content", ["Public holidays"]),
                                        ("27.1", OrderedDict([("_content", ["Public holidays are in the NES."])])),
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
                    "reference": "27",
                    "title": "Public holidays",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Public holidays affect payment outcomes.",
                },
                "classified_clauses": [
                    {
                        "reference": "27.1",
                        "tags": ["Leave"],
                        "reason": "Public holiday entitlement.",
                    }
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            award_path = Path(temp_dir) / "award.json"
            output_path = Path(temp_dir) / "award_payment_classification.json"
            award_path.write_text(json.dumps(award), encoding="utf-8")
            fake_client = FakeClient(payloads)

            result = classify_award(
                award_path=award_path,
                output_path=output_path,
                client=fake_client,
            )

        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertFalse(result["top_level_clauses"]["25"]["payment_relevant"])
        self.assertIn("27.1", result["classified_clauses"])

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

    def test_direct_l2_reference_for_maps_nested_references_to_parent(self):
        direct_references = {"14.7", "14.10"}

        self.assertEqual(direct_l2_reference_for("14.7", direct_references), "14.7")
        self.assertEqual(direct_l2_reference_for("14.7(b)", direct_references), "14.7")
        self.assertEqual(direct_l2_reference_for("14.7.b", direct_references), "14.7")
        self.assertIsNone(direct_l2_reference_for("14.8(b)", direct_references))

    def test_validate_group_classification_maps_nested_clause_references_to_direct_l2(self):
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

        _top_result, classified = validate_group_classification(
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
                        "reference": "25.1",
                        "tags": ["Ordinary Hours & Overtime"],
                        "reason": "Direct L2 overtime boundary.",
                    },
                    {
                        "reference": "25.1(a)",
                        "tags": ["Penalty"],
                        "reason": "Nested reference returned by model.",
                    },
                ],
            },
        )

        self.assertEqual(
            classified["25.1"]["tags"],
            ["Ordinary Hours & Overtime", "Penalty"],
        )
        self.assertIn("Returned nested reference 25.1(a)", classified["25.1"]["reason"])

    def test_validate_group_classification_maps_relative_numeric_reference_to_direct_l2(self):
        group = iter_top_level_groups(
            award_with_clause(
                "17",
                "Payment of wages",
                [
                    ("17.1", OrderedDict([("_content", ["Wages are paid weekly."])])),
                    ("17.2", OrderedDict([("_content", ["The employer may deduct an overpayment."])])),
                ],
            )
        )[0]

        _top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "17",
                    "title": "Payment of wages",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Contains payment rules.",
                },
                "classified_clauses": [
                    {
                        "reference": "2",
                        "tags": ["Other Payment"],
                        "reason": "Relative direct child reference returned by model.",
                    }
                ],
            },
        )

        self.assertIn("17.2", classified)
        self.assertEqual(classified["17.2"]["tags"], ["Other Payment"])
        self.assertIn("Returned nested reference 2", classified["17.2"]["reason"])

    def test_validate_group_classification_maps_relative_nested_reference_to_direct_l2(self):
        group = iter_top_level_groups(
            award_with_clause(
                "24",
                "Breaks",
                [
                    (
                        "24.1",
                        OrderedDict(
                            [
                                ("_content", ["Meal breaks"]),
                                ("a", OrderedDict([("_content", ["Employees must take a meal break."])])),
                            ]
                        ),
                    )
                ],
            )
        )[0]

        _top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "24",
                    "title": "Breaks",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Contains break rules.",
                },
                "classified_clauses": [
                    {
                        "reference": "1(a)",
                        "tags": ["Breaks (Meal Breaks)"],
                        "reason": "Relative nested reference returned by model.",
                    }
                ],
            },
        )

        self.assertIn("24.1", classified)
        self.assertEqual(classified["24.1"]["tags"], ["Breaks (Meal Breaks)"])
        self.assertIn("Returned nested reference 1(a)", classified["24.1"]["reason"])

    def test_validate_group_classification_rejects_unknown_clause_references(self):
        group = iter_top_level_groups(
            award_with_clause(
                "25",
                "Penalty rates",
                [("25.1", OrderedDict([("_content", ["Paid at 125%."])]))],
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
                            "reference": "25.2",
                            "tags": ["Penalty"],
                            "reason": "Reference is not in supplied direct L2 clauses.",
                        }
                    ],
                },
            )

    def test_validate_group_classification_accepts_omitted_non_payment_l2_clauses(self):
        group = iter_top_level_groups(
            award_with_clause(
                "17",
                "Payment of wages",
                [
                    ("17.1", OrderedDict([("_content", ["Wages are paid weekly."])])),
                    (
                        "17.2",
                        OrderedDict(
                            [
                                (
                                    "_content",
                                    [
                                        "Method of payment. Wages must be paid by cash or "
                                        "electronic funds transfer into an account nominated by "
                                        "the employee."
                                    ],
                                )
                            ]
                        ),
                    ),
                    ("17.3", OrderedDict([("_content", ["The employer may deduct an overpayment."])])),
                ],
            )
        )[0]

        top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "17",
                    "title": "Payment of wages",
                    "payment_relevant": True,
                    "definition_relevant": False,
                    "requires_l2_classification": True,
                    "reason": "Contains at least one clause affecting payment outcomes.",
                },
                "classified_clauses": [
                    {
                        "reference": "17.3",
                        "tags": ["Other Payment"],
                        "reason": "Deductions affect the amount paid and do not fit a specific tag.",
                    }
                ],
            },
        )

        self.assertTrue(top_result["payment_relevant"])
        self.assertNotIn("17.1", classified)
        self.assertNotIn("17.2", classified)
        self.assertEqual(classified["17.3"]["tags"], ["Other Payment"])

    def test_prompt_includes_definitions_and_allowed_tags(self):
        for tag in ALLOWED_TAGS:
            self.assertIn(tag, SYSTEM_PROMPT)
        self.assertIn("ordinary hours", DEFINITIONS)
        self.assertIn("shiftworker", SYSTEM_PROMPT)
        self.assertIn("Definition", SYSTEM_PROMPT)
        self.assertIn("Ordinary Hours & Overtime", SYSTEM_PROMPT)
        self.assertIn("L2 relevance is independent", SYSTEM_PROMPT)
        self.assertIn("Omit direct L2 clauses", SYSTEM_PROMPT)
        self.assertIn("classify the top-level reference itself", SYSTEM_PROMPT)
        self.assertIn("direct_l2_clauses is empty", SYSTEM_PROMPT)
        self.assertIn("A definitions clause with no direct L2 children", SYSTEM_PROMPT)
        self.assertIn("Do not use the Other Payment tag to mean irrelevant", SYSTEM_PROMPT)
        self.assertIn("Irrelevant direct L2 clauses must be omitted", SYSTEM_PROMPT)
        self.assertIn(
            "Use the Other Payment tag only when the clause is payment-related",
            SYSTEM_PROMPT,
        )
        self.assertIn("Other payment", SYSTEM_PROMPT)
        self.assertIn("Non-payment or payment administration", SYSTEM_PROMPT)
        self.assertIn("Method of payment", SYSTEM_PROMPT)
        self.assertIn("electronic funds transfer", SYSTEM_PROMPT)
        self.assertIn("Prefer inclusion", SYSTEM_PROMPT)
        self.assertIn("do not mark a top-level clause as relevant from its heading alone", SYSTEM_PROMPT)
        self.assertIn("District allowances", SYSTEM_PROMPT)
        self.assertIn("Individual flexibility arrangement clauses are a common trap", SYSTEM_PROMPT)
        self.assertIn("better-off-overall payment outcome", SYSTEM_PROMPT)
        self.assertIn(
            "time off is to be taken at convenient times after consultation",
            SYSTEM_PROMPT,
        )

        prompt = build_user_prompt({"top_level_clause": {"reference": "25"}})

        self.assertIn('"reference": "25"', prompt)

    def test_output_paths(self):
        self.assertEqual(
            output_path_for_award(Path("data/processed/MA000018.json")),
            Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json"),
        )
        self.assertEqual(
            timestamped_output_path(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json"),
                datetime(2026, 6, 16, 15, 30, 12),
            ),
            Path(
                "data/processed/2_payment_clause_identifier/archive/"
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
