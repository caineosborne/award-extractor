import json
import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.common.overtime_rules import OvertimeRule
from src.common.overtime_rulesets import OVERTIME_CONSEQUENCE_RULESET
from src.prompts.overtime_ruleset import (
    build_expert_comparison_messages as build_ruleset_expert_comparison_messages,
    build_interpretation_messages as build_ruleset_interpretation_messages,
)
from src.script_3_generate_overtime_ruleset import generate_overtime_ruleset
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
    validate_overtime_clause_classifications,
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
            Path("data/processed/MA000018/MA000018_overtime_interpretation.md"),
        )

    def test_classification_output_path_for_classification(self):
        self.assertEqual(
            classification_output_path_for_classification(
                Path("data/processed/2_payment_clause_identifier/MA000018_payment_classification.json")
            ),
            Path("data/processed/MA000018/MA000018_overtime_clause_classification.json"),
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
        self.assertEqual(
            clause_properties["employee_cohort"]["enum"],
            ["full-time", "part-time", "casual", "permanent", "all"],
        )
        self.assertEqual(
            clause_properties["work_arrangement"]["enum"],
            ["day-worker", "shiftworker", "all"],
        )

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

    def test_validate_overtime_clause_classifications_does_not_infer_day_worker_from_monday_to_friday_text(self):
        response_data = {
            "clauses": [
                {
                    "clause_number": "21.2",
                    "classification": "Ordinary Hours Boundary",
                    "classifications": ["Ordinary Hours Boundary"],
                    "clause_text": "Ordinary hours Monday to Friday.",
                    "explanation": "Defines ordinary hours.",
                    "employee_cohort": "all",
                    "work_arrangement": "day-worker",
                    "other_scope_notes": "Ordinary hours are confined to Monday to Friday.",
                }
            ]
        }
        overtime_clauses = {
            "21.2": {
                "text": (
                    "21.2: Ordinary hours will be worked in periods not exceeding eight "
                    "hours, in unbroken periods save for meal breaks, between Monday and "
                    "Friday."
                )
            }
        }

        classifications = validate_overtime_clause_classifications(
            response_data,
            overtime_clauses,
        )

        self.assertEqual(len(classifications), 1)
        self.assertEqual(classifications[0].work_arrangement, "all")

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
        self.assertIn("Each rule must be readable in isolation", user_prompt)
        self.assertIn("Do not rely on a clause reference as a substitute", user_prompt)
        self.assertIn("If a clause says 11.5 ordinary hours is the daily maximum", user_prompt)
        self.assertIn("Include all conditions, thresholds, limits, and requirements", user_prompt)
        self.assertIn("Each bullet must contain only one payroll test", user_prompt)
        self.assertIn("explicit and implicit triggers", user_prompt)
        self.assertIn("If the clause uses general wording such as \"employee\"", user_prompt)
        self.assertIn("employee_cohort", user_prompt)
        self.assertIn("work_arrangement", user_prompt)
        self.assertIn("Use the upstream scope tags as the starting point for scope", user_prompt)
        self.assertIn("Keep clause references in the markdown bullet", user_prompt)
        self.assertIn("Do not place a general rule under `Full time`", user_prompt)
        self.assertIn("Do not repeat a general rule under narrower headings", user_prompt)
        self.assertIn("Avoid duplicate rules.", user_prompt)
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

    def test_validate_interpretation_rules_renames_duplicate_rule_ids(self):
        response_data = {
            "rules": [
                {
                    "rule_id": "shiftworker_ordinary_hours_average_38_hours",
                    "section_heading": "Shiftworkers",
                    "employee_scope": ["full-time"],
                    "employee_cohort": "full-time",
                    "work_arrangement": "shiftworker",
                    "other_scope_notes": "",
                    "clause_references": ["15.1"],
                    "rule_markdown": "- First version. [15.1]",
                    "rule_plain_text": "First version.",
                    "source_clause_numbers": ["15.1"],
                    "source_classifications": ["Ordinary Hours Boundary"],
                },
                {
                    "rule_id": "shiftworker_ordinary_hours_average_38_hours",
                    "section_heading": "Shiftworkers",
                    "employee_scope": ["part-time"],
                    "employee_cohort": "part-time",
                    "work_arrangement": "shiftworker",
                    "other_scope_notes": "",
                    "clause_references": ["15.2"],
                    "rule_markdown": "- Second version. [15.2]",
                    "rule_plain_text": "Second version.",
                    "source_clause_numbers": ["15.2"],
                    "source_classifications": ["Ordinary Hours Boundary"],
                },
            ]
        }
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="15.1",
                classification="Ordinary Hours Boundary",
                classifications=["Ordinary Hours Boundary"],
                clause_text="Clause 15.1 text.",
                explanation="Defines ordinary hours.",
            ),
            OvertimeClauseClassification(
                clause_number="15.2",
                classification="Ordinary Hours Boundary",
                classifications=["Ordinary Hours Boundary"],
                clause_text="Clause 15.2 text.",
                explanation="Defines ordinary hours.",
            ),
        ]

        rules, warnings = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
        )

        self.assertEqual(rules[0].rule_id, "shiftworker_ordinary_hours_average_38_hours")
        self.assertEqual(rules[1].rule_id, "shiftworker_ordinary_hours_average_38_hours-2")
        self.assertIn(
            "Interpretation output returned duplicate rule_id "
            "`shiftworker_ordinary_hours_average_38_hours`. Rule 2 was renamed to "
            "`shiftworker_ordinary_hours_average_38_hours-2`.",
            warnings,
        )

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
            "Clause 22.8 was identified as relevant to overtime, but it is not present in the draft ruleset before review.",
        )

    def test_validate_interpretation_rules_records_scope_warning_when_rule_is_narrower_than_clause_scope(self):
        response_data = {
            "rules": [
                {
                    "rule_id": "full-time-outside-6am-630pm",
                    "section_heading": "Full-time employees",
                    "employee_scope": ["full-time"],
                    "employee_cohort": "full-time",
                    "work_arrangement": "all",
                    "other_scope_notes": "",
                    "clause_references": ["21.3"],
                    "rule_markdown": "- For a full-time employee, ordinary hours may only be worked between 6.00 am and 6.30 pm. [21.3]",
                    "rule_plain_text": "For a full-time employee, ordinary hours may only be worked between 6.00 am and 6.30 pm.",
                    "source_clause_numbers": ["21.3"],
                    "source_classifications": ["Ordinary Hours Boundary"],
                }
            ]
        }
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="21.3",
                classification="Ordinary Hours Boundary",
                clause_text="21.3 Ordinary hours may be worked between 6.00 am and 6.30 pm.",
                explanation="Defines the ordinary hours span.",
                employee_cohort="all",
                work_arrangement="all",
                other_scope_notes="",
            )
        ]

        _rules, warnings = validate_interpretation_rules(
            response_data,
            overtime_creation_clauses,
        )

        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0],
            "Rule 'full-time-outside-6am-630pm' draws on clause 21.3, which is classified as applying to all employees, but the rule is written as applying to full-time employees.",
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
            classification_path = Path(temp_dir) / "award" / "award_overtime_clause_classification.json"
            classification_artifact = json.loads(
                classification_path.read_text(encoding="utf-8")
            )
            archive_files = list(
                (Path(temp_dir) / "archive").glob("award_overtime_interpretation_*.md")
            )
            classification_archive_files = list(
                (Path(temp_dir) / "award" / "archive").glob(
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
            "overtime-clause-classification-v3",
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
        self.assertIn(
            "Clause 22.8 was identified as relevant to overtime, but it is not present in the draft ruleset before review.",
            written_markdown,
        )
        self.assertEqual(
            written_json["validation_warnings"],
            [
                "Clause 22.8 was identified as relevant to overtime, but it is not present in the draft ruleset before review."
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

    def test_generate_overtime_consequence_ruleset_writes_separate_files(self):
        data = {
            "classified_clauses": {
                "21.1": {
                    "tags": ["Ordinary Hours & Overtime"],
                    "text": "Overtime is paid at 150% for the first 2 hours and 200% after that.",
                    "reason": "Defines overtime rates.",
                }
            }
        }
        classification_json = json.dumps(
            {
                "clauses": [
                    {
                        "clause_number": "21.1",
                        "classification": "Overtime Consequence",
                        "classifications": ["Overtime Consequence"],
                        "clause_text": "Overtime is paid at 150% for the first 2 hours and 200% after that.",
                        "explanation": "Defines overtime payment once overtime already exists.",
                        "employee_cohort": "all",
                        "work_arrangement": "all",
                        "other_scope_notes": "",
                    }
                ]
            }
        )
        interpretation_json = json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "overtime-first-two-hours",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time", "part-time", "casual"],
                        "employee_cohort": "all",
                        "work_arrangement": "all",
                        "other_scope_notes": "",
                        "clause_references": ["21.1"],
                        "rule_markdown": "- The first 2 overtime hours are paid at 150% and subsequent overtime hours are paid at 200%. [21.1]",
                        "rule_plain_text": "The first 2 overtime hours are paid at 150% and subsequent overtime hours are paid at 200%.",
                        "source_clause_numbers": ["21.1"],
                        "source_classifications": ["Overtime Consequence"],
                    }
                ]
            }
        )
        fake_client = FakeClient([classification_json, interpretation_json])

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "award_payment_classification.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")

            result = generate_overtime_ruleset(
                classification_path=input_path,
                ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
                client=fake_client,
                expert_run_count=1,
            )

            clause_path = classification_output_path_for_classification(input_path)
            output_path = (
                Path(temp_dir)
                / "award"
                / "award_overtime_consequence_ruleset.md"
            )

            self.assertTrue(clause_path.exists())
            self.assertTrue(output_path.exists())
            self.assertIn("150%", result)
            self.assertIn(
                "Overtime is paid at 150% for the first 2 hours and 200% after that.",
                fake_client.responses.calls[1]["input"][1]["content"],
            )

    def test_overtime_consequence_prompt_instructs_pruning_of_trigger_only_content(self):
        messages = build_ruleset_interpretation_messages(
            OVERTIME_CONSEQUENCE_RULESET,
            "award_payment_classification.json",
            "Clause 1",
        )

        self.assertIn(
            "the most important implementation outcome is the actual overtime consequence",
            messages[0]["content"],
        )
        self.assertIn(
            "Prioritise full-time and part-time employee multipliers",
            messages[0]["content"],
        )
        self.assertIn(
            "Also capture casual employee overtime multipliers or rate rules",
            messages[0]["content"],
        )
        self.assertIn(
            "Prune trigger-only or boundary-only content",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not produce a standalone rule whose main purpose is to say when hours become overtime.",
            messages[1]["content"],
        )
        self.assertIn(
            "Prioritise overtime pay multipliers and other direct rate outcomes for each employee cohort.",
            messages[1]["content"],
        )
        self.assertIn(
            "Do not assume that a full-time or part-time multiplier rule automatically covers casual employees.",
            messages[1]["content"],
        )

    def test_overtime_consequence_comparison_prompt_instructs_pruning_of_trigger_rules(self):
        messages = build_ruleset_expert_comparison_messages(
            ruleset_key=OVERTIME_CONSEQUENCE_RULESET,
            source_path=Path("award_payment_classification.json"),
            shortlisted_clauses=[],
            run_a_rules_json=[],
            run_b_rules_json=[],
        )

        self.assertIn(
            "prefer pruning over preserving mixed trigger content",
            messages[0]["content"],
        )
        self.assertIn(
            "Remove standalone trigger/boundary rules that survived expert drafting by mistake.",
            messages[1]["content"],
        )

    def test_phase_1_ruleset_prompt_module_is_in_prompts_folder(self):
        prompt_source = inspect.getsourcefile(build_ruleset_interpretation_messages)
        self.assertIsNotNone(prompt_source)
        self.assertIn("/src/prompts/", prompt_source)

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
            "overtime-clause-classification-v3",
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

    def test_compare_expert_interpretation_runs_renames_duplicate_merged_rule_ids(self):
        comparison_json = json.dumps(
            {
                "comparison_summary_markdown": "# Comparison",
                "accounted_run_a_rule_ids": ["rule-a", "rule-b"],
                "accounted_run_b_rule_ids": [],
                "merge_explanations": [
                    {
                        "merged_rule_id": "duplicate-rule",
                        "run_a_rule_ids": ["rule-a"],
                        "run_b_rule_ids": [],
                        "reason": "First reason.",
                    },
                    {
                        "merged_rule_id": "duplicate-rule",
                        "run_a_rule_ids": ["rule-b"],
                        "run_b_rule_ids": [],
                        "reason": "Second reason.",
                    },
                ],
                "merged_rules": [
                    {
                        "rule_id": "duplicate-rule",
                        "section_heading": "All employees",
                        "employee_scope": ["full-time"],
                        "employee_cohort": "full-time",
                        "work_arrangement": "all",
                        "other_scope_notes": "",
                        "clause_references": ["10.1"],
                        "rule_markdown": "- First. [10.1]",
                        "rule_plain_text": "First.",
                        "source_clause_numbers": ["10.1"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    },
                    {
                        "rule_id": "duplicate-rule",
                        "section_heading": "All employees",
                        "employee_scope": ["part-time"],
                        "employee_cohort": "part-time",
                        "work_arrangement": "all",
                        "other_scope_notes": "",
                        "clause_references": ["10.2"],
                        "rule_markdown": "- Second. [10.2]",
                        "rule_plain_text": "Second.",
                        "source_clause_numbers": ["10.2"],
                        "source_classifications": ["Ordinary Hours Boundary"],
                    },
                ],
            }
        )
        fake_client = FakeClient([comparison_json])
        overtime_creation_clauses = [
            OvertimeClauseClassification(
                clause_number="10.1",
                classification="Ordinary Hours Boundary",
                clause_text="Clause 10.1 text.",
                explanation="Defines ordinary hours.",
            ),
            OvertimeClauseClassification(
                clause_number="10.2",
                classification="Ordinary Hours Boundary",
                clause_text="Clause 10.2 text.",
                explanation="Defines ordinary hours.",
            ),
        ]
        run_a_rules = [
            OvertimeRule(
                rule_id="rule-a",
                section_heading="All employees",
                employee_scope=("full-time",),
                clause_references=("10.1",),
                rule_markdown="- Rule A. [10.1]",
                rule_plain_text="Rule A.",
                source_clause_numbers=("10.1",),
                source_classifications=("Ordinary Hours Boundary",),
            ),
            OvertimeRule(
                rule_id="rule-b",
                section_heading="All employees",
                employee_scope=("part-time",),
                clause_references=("10.2",),
                rule_markdown="- Rule B. [10.2]",
                rule_plain_text="Rule B.",
                source_clause_numbers=("10.2",),
                source_classifications=("Ordinary Hours Boundary",),
            ),
        ]

        merged_rules, comparison_metadata, warnings = compare_expert_interpretation_runs(
            client=fake_client,
            model=DEFAULT_MODEL,
            source_path=Path("award_payment_classification.json"),
            overtime_creation_clauses=overtime_creation_clauses,
            run_a_rules=run_a_rules,
            run_b_rules=[],
        )

        self.assertEqual(merged_rules[0].rule_id, "duplicate-rule")
        self.assertEqual(merged_rules[1].rule_id, "duplicate-rule-2")
        self.assertEqual(
            comparison_metadata["merge_explanations"][1]["merged_rule_id"],
            "duplicate-rule-2",
        )
        self.assertIn(
            "Comparison output returned duplicate rule_id `duplicate-rule`. "
            "Rule 2 was renamed to `duplicate-rule-2`.",
            warnings,
        )


if __name__ == "__main__":
    unittest.main()
