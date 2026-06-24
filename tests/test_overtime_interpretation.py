import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.script_3_interpret_overtime import (
    DEFAULT_MODEL,
    OVERTIME_CREATION_CLASSIFICATIONS,
    OvertimeClauseClassification,
    build_messages,
    classification_output_path_for_classification,
    classification_response_json_schema,
    compare_expert_interpretation_runs,
    filter_overtime_creation_clauses,
    filter_overtime_clauses,
    format_clauses_for_prompt,
    generate_overtime_interpretation,
    output_path_for_classification,
    validate_interpretation_rules,
)


class FakeResponses:
    def __init__(self, output_texts):
        self.output_texts = list(output_texts)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_texts.pop(0))


class FakeClient:
    def __init__(self, output_texts):
        self.responses = FakeResponses(output_texts)


class OvertimeInterpretationTests(unittest.TestCase):
    def test_filter_overtime_clauses_matches_requested_filter(self):
        data = {
            "classified_clauses": {
                "10.1": {"tags": ["Ordinary Hours & Overtime"], "text": "ordinary"},
                "20.1": {"tags": ["Ordinary Hours & Overtime"], "text": "overtime"},
                "30.1": {"tags": ["Penalty"], "text": "penalty"},
            }
        }

        results = filter_overtime_clauses(data)

        self.assertEqual(list(results), ["10.1", "20.1"])

    def test_output_path_for_classification(self):
        self.assertEqual(
            output_path_for_classification(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json")
            ),
            Path("data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"),
        )

    def test_classification_output_path_for_classification(self):
        self.assertEqual(
            classification_output_path_for_classification(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json")
            ),
            Path(
                "data/processed/3_overtime_interpretations/"
                "MA000018_overtime_clause_classification.json"
            ),
        )

    def test_format_clauses_for_prompt_uses_plain_clause_sections(self):
        prompt_text = format_clauses_for_prompt(
            {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime applies after ordinary hours.",
                }
            }
        )

        self.assertIn("## Clause 20.1", prompt_text)
        self.assertIn("Overtime applies after ordinary hours.", prompt_text)

    def test_classification_response_schema_lists_allowed_categories(self):
        schema = classification_response_json_schema()
        clause_properties = schema["properties"]["clauses"]["items"]["properties"]
        classification_enum = clause_properties[
            "classification"
        ]["enum"]
        classifications_enum = clause_properties["classifications"]["items"]["enum"]

        self.assertIn("Ordinary Hours Boundary", classification_enum)
        self.assertIn("Overtime Trigger", classification_enum)
        self.assertIn("Overtime Consequence", classification_enum)
        self.assertIn("Related Rule", classification_enum)
        self.assertIn("Not Relevant", classification_enum)
        self.assertEqual(classifications_enum, classification_enum)

    def test_filter_overtime_creation_clauses_keeps_only_creation_categories(self):
        classifications = [
            OvertimeClauseClassification(
                clause_number="10.1",
                classification="Ordinary Hours Boundary",
                clause_text="Ordinary hours are 38 per week.",
                explanation="Defines ordinary hours.",
            ),
            OvertimeClauseClassification(
                clause_number="20.1",
                classification="Overtime Trigger",
                clause_text="Overtime applies after 10 hours.",
                explanation="Directly creates overtime.",
            ),
            OvertimeClauseClassification(
                clause_number="30.1",
                classification="Overtime Consequence",
                clause_text="Overtime is paid at 150%.",
                explanation="Explains payment after overtime exists.",
            ),
            OvertimeClauseClassification(
                clause_number="40.1",
                classification="Overtime Consequence",
                classifications=("Overtime Trigger", "Overtime Consequence"),
                clause_text=(
                    "Overtime applies after 10 hours and is paid at overtime rates."
                ),
                explanation="Contains both an overtime trigger and consequence.",
            ),
        ]

        results = filter_overtime_creation_clauses(classifications)

        self.assertEqual(
            [classification.clause_number for classification in results],
            ["10.1", "20.1", "40.1"],
        )

    def test_build_messages_includes_required_working_document_sections(self):
        messages = build_messages(
            "classification.json",
            [
                OvertimeClauseClassification(
                    clause_number="20.1",
                    classification="Overtime Trigger",
                    clause_text="Paid overtime.",
                    explanation="Directly creates overtime.",
                )
            ],
        )

        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("expert payroll award interpretation assistant", system_prompt)
        self.assertIn("What circumstances increase Total Overtime Hours?", user_prompt)
        self.assertIn("Special Instructions:", user_prompt)
        self.assertIn("explicit and implicit triggers", user_prompt)
        self.assertIn("Do not include:", user_prompt)
        self.assertIn("specific employee segment section only when", user_prompt)
        self.assertIn("dedicated work-arrangement section", user_prompt)
        self.assertIn("still state the employee type affected", user_prompt)
        self.assertIn("Each bullet must contain only one payroll test", user_prompt)
        self.assertIn("If the clause uses general wording such as \"employee\"", user_prompt)
        self.assertIn("Write the clause references directly in the markdown bullet", user_prompt)
        self.assertIn("Do not place a general rule under `Full time`", user_prompt)
        self.assertIn("Do not repeat a general rule", user_prompt)
        self.assertIn("Avoid duplicate rules:", user_prompt)
        self.assertNotIn("What data is required", user_prompt)
        self.assertNotIn("What assumptions are being made", user_prompt)
        self.assertIn("## Clause 20.1", user_prompt)
        self.assertIn("Overtime Trigger", user_prompt)

    def test_validate_interpretation_rules_accepts_contains_match_for_source_classifications(self):
        response_data = {
            "rules": [
                {
                    "rule_id": "broken-shift-beyond-12-hour-span",
                    "section_heading": "All employees",
                    "employee_scope": ["part-time", "casual"],
                    "clause_references": ["22.8"],
                    "rule_markdown": "- Broken shift over 12 hours becomes overtime. [22.8]",
                    "rule_plain_text": "Broken shift over 12 hours becomes overtime.",
                    "source_clause_numbers": ["22.8"],
                    "source_classifications": [
                        "Ordinary Hours Boundary",
                        "Overtime Consequence",
                    ],
                }
            ]
        }
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="22.8",
                classification="Ordinary Hours Boundary",
                classifications=(
                    "Ordinary Hours Boundary",
                    "Overtime Consequence",
                    "Related Rule",
                ),
                clause_text="22.8 Broken shifts...",
                explanation="Broken shift span is capped at 12 hours.",
            )
        ]

        rules, warnings = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
        )

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "broken-shift-beyond-12-hour-span")
        self.assertEqual(len(warnings), 1)
        self.assertIn("accepted because it also contains an allowed creation classification", warnings[0])

    def test_validate_interpretation_rules_records_missing_shortlisted_clause_as_warning(self):
        response_data = {
            "rules": [
                {
                    "rule_id": "full-time-over-38",
                    "section_heading": "All employees",
                    "employee_scope": ["full-time"],
                    "clause_references": ["22.1"],
                    "rule_markdown": "- Hours over 38 are overtime. [22.1]",
                    "rule_plain_text": "Hours over 38 are overtime.",
                    "source_clause_numbers": ["22.1"],
                    "source_classifications": ["Ordinary Hours Boundary"],
                }
            ]
        }
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="22.1",
                classification="Ordinary Hours Boundary",
                clause_text="22.1 Ordinary hours...",
                explanation="Ordinary hours are capped.",
            ),
            OvertimeClauseClassification(
                clause_number="22.8",
                classification="Ordinary Hours Boundary",
                clause_text="22.8 Broken shifts...",
                explanation="Broken shift span is capped at 12 hours.",
            ),
        ]

        _rules, warnings = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
        )

        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0],
            "Shortlisted clause 22.8 from step 3.2 is not referenced by any step 3.4 rule.",
        )

    def test_generate_overtime_interpretation_writes_markdown_with_mocked_client(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
                "21.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime is paid at 150%.",
                    "reason": "Explains the overtime rate.",
                },
                "30.1": {
                    "tags": ["Penalty"],
                    "text": "Weekend penalty.",
                },
            }
        }
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "clause_text": "Employees are paid overtime after ordinary hours.",
                        "explanation": "Directly creates overtime.",
                    },
                    {
                        "clause_number": "21.1",
                        "classification": "Overtime Consequence",
                        "clause_text": "Overtime is paid at 150%.",
                        "explanation": "Explains payment after overtime exists.",
                    },
                ]
            }
        )
        fake_client = FakeClient(
            [
                classification_json,
                "## All Employees\n\n"
                "- The hours will be overtime after ordinary hours. [20.1]",
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            output_path = Path(temp_dir) / "award_overtime_interpretation.md"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            result = generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            written = output_path.read_text(encoding="utf-8")
            classification_path = Path(temp_dir) / (
                "3_overtime_interpretations/award_overtime_clause_classification.json"
            )
            classification_artifact = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_interpretation_*.md")
            )
            classification_archive_files = list(
                (Path(temp_dir) / "3_overtime_interpretations" / "archive").glob(
                    "award_overtime_clause_classification_*.json"
                )
            )

        self.assertEqual(result, written)
        self.assertIn("# Validation notes", written)
        self.assertIn(
            "The step 3.4 model did not return valid JSON. A markdown fallback parser was used",
            written,
        )
        self.assertIn(
            "## All Employees\n\n- The hours will be overtime after ordinary hours. [20.1]",
            written,
        )
        self.assertEqual(len(archive_files), 1)
        self.assertEqual(len(classification_archive_files), 1)
        self.assertEqual(
            classification_artifact["schema_version"],
            "overtime-clause-classification-v2",
        )
        self.assertEqual(len(classification_artifact["clauses"]), 2)
        self.assertEqual(
            classification_artifact["clauses"][0]["classifications"],
            ["Overtime Trigger"],
        )
        self.assertEqual(fake_client.responses.calls[0]["model"], DEFAULT_MODEL)
        self.assertEqual(fake_client.responses.calls[1]["model"], DEFAULT_MODEL)
        self.assertIn("## Clause 20.1", fake_client.responses.calls[0]["input"][1]["content"])
        self.assertIn(
            "Employees are paid overtime after ordinary hours.",
            fake_client.responses.calls[1]["input"][1]["content"],
        )
        self.assertIn("text", fake_client.responses.calls[1])
        self.assertNotIn(
            "Overtime is paid at 150%.",
            fake_client.responses.calls[1]["input"][1]["content"],
        )
        self.assertNotIn(
            "## Clause 30.1",
            fake_client.responses.calls[0]["input"][1]["content"],
        )

    def test_generate_overtime_interpretation_writes_validation_notes_in_markdown(self):
        data = {
            "classified_clauses": {
                "22.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Ordinary hours are 38 per week.",
                    "reason": "Defines ordinary hours.",
                },
                "22.8": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Broken shifts have a maximum span of 12 hours.",
                    "reason": "Sets a broken shift boundary.",
                },
            }
        }
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "22.1",
                        "classification": "Ordinary Hours Boundary",
                        "classifications": ["Ordinary Hours Boundary"],
                        "clause_text": "Ordinary hours are 38 per week.",
                        "explanation": "Defines ordinary hours.",
                    },
                    {
                        "clause_number": "22.8",
                        "classification": "Ordinary Hours Boundary",
                        "classifications": [
                            "Ordinary Hours Boundary",
                            "Overtime Consequence",
                        ],
                        "clause_text": "Broken shifts have a maximum span of 12 hours.",
                        "explanation": "Sets a broken shift boundary.",
                    },
                ]
            }
        )
        interpretation_json = json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "full-time-over-38",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "clause_references": ["22.1"],
                        "rule_markdown": "- Hours over 38 are overtime. [22.1]",
                        "rule_plain_text": "Hours over 38 are overtime.",
                        "source_clause_numbers": ["22.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    }
                ]
            }
        )
        fake_client = FakeClient([classification_json, interpretation_json])

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            output_path = Path(temp_dir) / "award_overtime_interpretation.md"
            json_output_path = Path(temp_dir) / "award_overtime_interpretation.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                client=fake_client,
            )

            written_markdown = output_path.read_text(encoding="utf-8")
            written_json = json.loads(json_output_path.read_text(encoding="utf-8"))

        self.assertIn("# Validation notes", written_markdown)
        self.assertIn("Shortlisted clause 22.8 from step 3.2 is not referenced", written_markdown)
        self.assertEqual(
            written_json["validation_warnings"],
            [
                "Shortlisted clause 22.8 from step 3.2 is not referenced by any step 3.4 rule."
            ],
        )

    def test_generate_overtime_interpretation_reuses_existing_clause_classification(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
                "21.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime is paid at 150%.",
                    "reason": "Explains the overtime rate.",
                },
            }
        }
        saved_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "source_classification_file": "award_payment_classification.json",
            "included_categories_for_interpretation": [
                "Ordinary Hours Boundary",
                "Overtime Trigger",
            ],
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Trigger",
                    "classifications": ["Overtime Trigger"],
                    "clause_text": "Employees are paid overtime after ordinary hours.",
                    "explanation": "Directly creates overtime.",
                },
                {
                    "clause_number": "21.1",
                    "classification": "Overtime Consequence",
                    "classifications": ["Overtime Consequence"],
                    "clause_text": "Overtime is paid at 150%.",
                    "explanation": "Explains payment after overtime exists.",
                },
            ],
        }
        fake_client = FakeClient(
            [
                "## General\n\n"
                "- The hours will be overtime after ordinary hours. [20.1]",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "award_payment_classification.json"
            output_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_overtime_clause_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            classification_path.write_text(
                json.dumps(saved_classification),
                encoding="utf-8",
            )

            result = generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                classification_output_path=classification_path,
                client=fake_client,
            )

            archive_files = list(
                temp_path.glob("archive/award_overtime_clause_classification_*.json")
            )

        self.assertIn("## General", result)
        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertIn("text", fake_client.responses.calls[0])
        self.assertEqual(archive_files, [])

    def test_generate_overtime_interpretation_merges_two_expert_runs(self):
        data = {
            "classified_clauses": {
                "22.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Ordinary hours are 38 per week and 8 hours on a day shift.",
                    "reason": "Defines ordinary hours.",
                }
            }
        }
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "22.1",
                        "classification": "Ordinary Hours Boundary",
                        "classifications": ["Ordinary Hours Boundary"],
                        "clause_text": "Ordinary hours are 38 per week and 8 hours on a day shift.",
                        "explanation": "Defines ordinary hours.",
                    }
                ]
            }
        )
        expert_a_json = json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "full-time-over-38",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "clause_references": ["22.1"],
                        "rule_markdown": "- Hours over 38 per week are overtime. [22.1]",
                        "rule_plain_text": "Hours over 38 per week are overtime.",
                        "source_clause_numbers": ["22.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    }
                ]
            }
        )
        expert_b_json = json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "day-shift-over-8",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "clause_references": ["22.1(c)"],
                        "rule_markdown": "- Hours over 8 on a day shift are overtime. [22.1(c)]",
                        "rule_plain_text": "Hours over 8 on a day shift are overtime.",
                        "source_clause_numbers": ["22.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    }
                ]
            }
        )
        comparison_json = json.dumps(
            {
                "comparison_summary_markdown": "# Comparison\n\nMerged complementary rules from both expert runs.",
                "accounted_run_a_rule_ids": ["full-time-over-38"],
                "accounted_run_b_rule_ids": ["day-shift-over-8"],
                "merged_rules": [
                    {
                        "rule_id": "full-time-over-38",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "clause_references": ["22.1"],
                        "rule_markdown": "- Hours over 38 per week are overtime. [22.1]",
                        "rule_plain_text": "Hours over 38 per week are overtime.",
                        "source_clause_numbers": ["22.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    },
                    {
                        "rule_id": "day-shift-over-8",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "clause_references": ["22.1(c)"],
                        "rule_markdown": "- Hours over 8 on a day shift are overtime. [22.1(c)]",
                        "rule_plain_text": "Hours over 8 on a day shift are overtime.",
                        "source_clause_numbers": ["22.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    },
                ],
                "merge_explanations": [
                    {
                        "merged_rule_id": "full-time-over-38",
                        "run_a_rule_ids": ["full-time-over-38"],
                        "run_b_rule_ids": [],
                        "reason": "Only run A captured the weekly boundary.",
                    },
                    {
                        "merged_rule_id": "day-shift-over-8",
                        "run_a_rule_ids": [],
                        "run_b_rule_ids": ["day-shift-over-8"],
                        "reason": "Only run B captured the day-shift boundary.",
                    },
                ],
            }
        )
        fake_client = FakeClient(
            [classification_json, expert_a_json, expert_b_json, comparison_json]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            output_path = Path(temp_dir) / "award_overtime_interpretation.md"
            output_json_path = Path(temp_dir) / "award_overtime_interpretation.json"
            comparison_path = Path(temp_dir) / "award_overtime_interpretation_comparison.json"
            expert_a_path = Path(temp_dir) / "award_overtime_interpretation_expert_a.json"
            expert_b_path = Path(temp_dir) / "award_overtime_interpretation_expert_b.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            result = generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                client=fake_client,
                expert_run_count=2,
            )

            written_markdown = output_path.read_text(encoding="utf-8")
            written_json = json.loads(output_json_path.read_text(encoding="utf-8"))
            comparison_artifact = json.loads(comparison_path.read_text(encoding="utf-8"))
            expert_a_exists = expert_a_path.exists()
            expert_b_exists = expert_b_path.exists()

        self.assertEqual(result, written_markdown)
        self.assertIn("Hours over 38 per week are overtime", written_markdown)
        self.assertIn("Hours over 8 on a day shift are overtime", written_markdown)
        self.assertEqual(written_json["comparison_mode"], "band_of_experts")
        self.assertEqual(len(written_json["expert_outputs"]), 2)
        self.assertTrue(expert_a_exists)
        self.assertTrue(expert_b_exists)
        self.assertEqual(
            comparison_artifact["accounted_run_a_rule_ids"],
            ["full-time-over-38"],
        )
        self.assertEqual(
            comparison_artifact["accounted_run_b_rule_ids"],
            ["day-shift-over-8"],
        )

    def test_generate_overtime_interpretation_regenerates_old_clause_classification(self):
        data = {
            "classified_clauses": {
                "20.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Employees are paid overtime after ordinary hours.",
                    "reason": "Creates overtime entitlement.",
                },
            }
        }
        old_classification = {
            "schema_version": "overtime-clause-classification-v1",
            "source_classification_file": "award_payment_classification.json",
            "included_categories_for_interpretation": [
                "Ordinary Hours Boundary",
                "Overtime Trigger",
            ],
            "clauses": [
                {
                    "clause_number": "20.1",
                    "classification": "Overtime Consequence",
                    "clause_text": "Employees are paid overtime after ordinary hours.",
                    "explanation": "Old single-label classification.",
                },
            ],
        }
        new_classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "20.1",
                        "classification": "Overtime Trigger",
                        "classifications": [
                            "Overtime Trigger",
                            "Overtime Consequence",
                        ],
                        "clause_text": "Employees are paid overtime after ordinary hours.",
                        "explanation": "Contains both a trigger and consequence.",
                    },
                ]
            }
        )
        fake_client = FakeClient(
            [
                new_classification_json,
                "## General\n\n"
                "- The hours will be overtime after ordinary hours. [20.1]",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "award_payment_classification.json"
            output_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_overtime_clause_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            classification_path.write_text(
                json.dumps(old_classification),
                encoding="utf-8",
            )

            generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                classification_output_path=classification_path,
                client=fake_client,
            )

            regenerated_classification = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            archive_files = list(
                temp_path.glob("archive/award_overtime_clause_classification_*.json")
            )

        self.assertEqual(len(fake_client.responses.calls), 2)
        self.assertEqual(
            regenerated_classification["schema_version"],
            "overtime-clause-classification-v2",
        )
        self.assertEqual(len(archive_files), 1)

    def test_generate_overtime_interpretation_regenerates_stale_clause_classification(self):
        data = {
            "classified_clauses": {
                "10.2": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Part-time ordinary hours limit.",
                    "reason": "Defines the ordinary-hours boundary.",
                },
            }
        }
        stale_classification = {
            "schema_version": "overtime-clause-classification-v2",
            "source_classification_file": "award_payment_classification.json",
            "included_categories_for_interpretation": [
                "Ordinary Hours Boundary",
                "Overtime Trigger",
            ],
            "clauses": [
                {
                    "clause_number": "10.4",
                    "classification": "Ordinary Hours Boundary",
                    "classifications": ["Ordinary Hours Boundary"],
                    "clause_text": "Guaranteed hours and availability.",
                    "explanation": "Old clause set from a previous run.",
                },
            ],
        }
        regenerated_classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "10.2",
                        "classification": "Ordinary Hours Boundary",
                        "classifications": ["Ordinary Hours Boundary"],
                        "clause_text": "Part-time ordinary hours limit.",
                        "explanation": "Defines the ordinary-hours boundary.",
                    },
                ]
            }
        )
        fake_client = FakeClient(
            [
                regenerated_classification_json,
                "## General\n\n"
                "- The part-time employee rules set the ordinary-hours boundary. [10.2]",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "award_payment_classification.json"
            output_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_overtime_clause_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            classification_path.write_text(
                json.dumps(stale_classification),
                encoding="utf-8",
            )

            generate_overtime_interpretation(
                classification_path=input_path,
                output_path=output_path,
                classification_output_path=classification_path,
                client=fake_client,
            )

            regenerated_classification = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            archive_files = list(
                temp_path.glob("archive/award_overtime_clause_classification_*.json")
            )

        self.assertEqual(len(fake_client.responses.calls), 2)
        self.assertEqual(
            regenerated_classification["clauses"][0]["clause_number"],
            "10.2",
        )
        self.assertEqual(len(archive_files), 1)

    def test_compare_expert_interpretation_runs_treats_subclause_as_covering_parent_clause(self):
        comparison_json = json.dumps(
            {
                "comparison_summary_markdown": "Merged output keeps the same rule.",
                "accounted_run_a_rule_ids": ["rest-period-after-overtime"],
                "accounted_run_b_rule_ids": ["rest-period-after-overtime"],
                "merge_explanations": [
                    {
                        "merged_rule_id": "rest-period-after-overtime",
                        "run_a_rule_ids": ["rest-period-after-overtime"],
                        "run_b_rule_ids": ["rest-period-after-overtime"],
                        "reason": "Same business rule.",
                    }
                ],
                "merged_rules": [
                    {
                        "rule_id": "rest-period-after-overtime",
                        "section_heading": "Rest period after overtime",
                        "employee_scope": ["full-time", "part-time"],
                        "clause_references": ["25.1(d)(i)", "25.1(d)(ii)"],
                        "rule_markdown": "- Less than 10 hours off duty after overtime stays overtime.",
                        "rule_plain_text": "Less than 10 hours off duty after overtime stays overtime.",
                        "source_clause_numbers": ["25.1(d)(i)", "25.1(d)(ii)"],
                        "source_classifications": ["Overtime Trigger"],
                    }
                ],
            }
        )
        fake_client = FakeClient([comparison_json])
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="25.1",
                classification="Overtime Trigger",
                clause_text="25.1 Overtime rates...",
                explanation="Creates overtime consequences and triggers.",
            )
        ]
        interpreted_rules, interpreted_warnings = validate_interpretation_rules(
            {
                "rules": [
                    {
                        "rule_id": "rest-period-after-overtime",
                        "section_heading": "Rest period after overtime",
                        "employee_scope": ["full-time", "part-time"],
                        "clause_references": ["25.1(d)(i)", "25.1(d)(ii)"],
                        "rule_markdown": "- Less than 10 hours off duty after overtime stays overtime.",
                        "rule_plain_text": "Less than 10 hours off duty after overtime stays overtime.",
                        "source_clause_numbers": ["25.1(d)(i)", "25.1(d)(ii)"],
                        "source_classifications": ["Overtime Trigger"],
                    }
                ]
            },
            overtime_creation_clauses,
        )

        self.assertEqual(interpreted_warnings, [])

        _merged_rules, _comparison_metadata, warnings = compare_expert_interpretation_runs(
            client=fake_client,
            model=DEFAULT_MODEL,
            source_path=Path("award_payment_classification.json"),
            overtime_creation_clauses=overtime_creation_clauses,
            run_a_rules=interpreted_rules,
            run_b_rules=interpreted_rules,
        )

        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
