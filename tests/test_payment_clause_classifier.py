import json
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from src.payment_clause_classifier import (
    DEFAULT_MODEL,
    PaymentClauseClassifierError,
    classify_award,
    collect_descendants,
    flatten_clause,
    iter_top_level_groups,
    output_path_for_award,
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


class PaymentClauseClassifierTests(unittest.TestCase):
    def test_collects_descendant_references_and_flattens_lettered_clauses(self):
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

        self.assertEqual([item.reference for item in descendants], ["24.1", "24.1(a)", "24.1(b)"])
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

    def test_validate_group_classification_accepts_hourly_rate_and_multiplier_effects(self):
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
                        ]
                    ),
                )
            ]
        )
        group = iter_top_level_groups(award)[0]
        classification = {
            "top_level_clause": {
                "reference": "14",
                "title": "Minimum wages",
                "payment_effects": ["hourly_rate"],
                "requires_descendant_classification": True,
                "reason": "Sets base rates.",
            },
            "classified_clauses": [
                {
                    "reference": "14.1",
                    "tags": ["Hourly Rate"],
                    "payment_effects": ["hourly_rate"],
                    "reason": "Determines base hourly rate.",
                }
            ],
        }

        top_result, classified = validate_group_classification(group, classification)

        self.assertEqual(top_result["payment_effects"], ["hourly_rate"])
        self.assertEqual(classified["14.1"]["tags"], ["Hourly Rate"])

    def test_validate_group_classification_drops_none_when_concrete_effect_exists(self):
        award = OrderedDict(
            [
                (
                    "Part 1",
                    OrderedDict(
                        [
                            ("_content", []),
                            (
                                "25",
                                OrderedDict(
                                    [
                                        ("_content", ["Penalty rates"]),
                                        ("25.1", OrderedDict([("_content", ["Paid at 125%."])])),
                                    ]
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )
        group = iter_top_level_groups(award)[0]

        _top_result, classified = validate_group_classification(
            group,
            {
                "top_level_clause": {
                    "reference": "25",
                    "title": "Penalty rates",
                    "payment_effects": ["none", "multiplier_impact"],
                    "requires_descendant_classification": True,
                    "reason": "Changes multiplier.",
                },
                "classified_clauses": [
                    {
                        "reference": "25.1",
                        "tags": ["Penalty"],
                        "payment_effects": ["none", "multiplier_impact"],
                        "reason": "Applies a penalty multiplier.",
                    }
                ],
            },
        )

        self.assertEqual(classified["25.1"]["payment_effects"], ["multiplier_impact"])

    def test_validate_group_classification_rejects_unknown_tags(self):
        award = OrderedDict(
            [
                (
                    "Part 1",
                    OrderedDict(
                        [
                            ("_content", []),
                            (
                                "25",
                                OrderedDict(
                                    [
                                        ("_content", ["Penalty rates"]),
                                        ("25.1", OrderedDict([("_content", ["Paid at 125%."])])),
                                    ]
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )
        group = iter_top_level_groups(award)[0]

        with self.assertRaisesRegex(PaymentClauseClassifierError, "invalid tag"):
            validate_group_classification(
                group,
                {
                    "top_level_clause": {
                        "reference": "25",
                        "title": "Penalty rates",
                        "payment_effects": ["multiplier_impact"],
                        "requires_descendant_classification": True,
                        "reason": "Changes multiplier.",
                    },
                    "classified_clauses": [
                        {
                            "reference": "25.1",
                            "tags": ["Weekend"],
                            "payment_effects": ["multiplier_impact"],
                            "reason": "Invalid tag.",
                        }
                    ],
                },
            )

    def test_prompt_includes_definitions_and_allowed_tags(self):
        for tag in ALLOWED_TAGS:
            self.assertIn(tag, SYSTEM_PROMPT)
        self.assertIn("ordinary hours", DEFINITIONS)
        self.assertIn("shiftworker", SYSTEM_PROMPT)

        prompt = build_user_prompt({"top_level_clause": {"reference": "25"}})

        self.assertIn('"reference": "25"', prompt)

    def test_output_path_for_award(self):
        self.assertEqual(
            output_path_for_award(Path("data/processed/MA000018.json")),
            Path("data/processed/MA000018_payment_classification.json"),
        )

    def test_classify_award_writes_companion_json_with_mocked_client(self):
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
                    "payment_effects": ["hourly_rate"],
                    "requires_descendant_classification": True,
                    "reason": "Sets base rates.",
                },
                "classified_clauses": [
                    {
                        "reference": "14.1",
                        "tags": ["Hourly Rate"],
                        "payment_effects": ["hourly_rate"],
                        "reason": "Base hourly rate.",
                    }
                ],
            },
            {
                "top_level_clause": {
                    "reference": "25",
                    "title": "Overtime",
                    "payment_effects": ["multiplier_impact"],
                    "requires_descendant_classification": True,
                    "reason": "Changes multiplier.",
                },
                "classified_clauses": [
                    {
                        "reference": "25.1",
                        "tags": ["Overtime"],
                        "payment_effects": ["multiplier_impact"],
                        "reason": "Applies overtime multiplier.",
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

        self.assertEqual(result["model"], DEFAULT_MODEL)
        self.assertEqual(written["classified_clauses"]["14.1"]["tags"], ["Hourly Rate"])
        self.assertEqual(
            written["classified_clauses"]["25.1"]["payment_effects"],
            ["multiplier_impact"],
        )


if __name__ == "__main__":
    unittest.main()
