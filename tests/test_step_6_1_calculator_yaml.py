import ast
from copy import deepcopy

from src.step_6_1_generate_calculator_yaml.core import (
    align_questionnaire_to_calculator_contract,
    calculator_rules_response_json_schema,
    normalize_response_data,
    render_python_text,
    summarized_rules,
)


def _answer(
    answer,
    *,
    status="derived",
    source_ruleset_keys=None,
    source_rule_ids=None,
    clause_references=None,
    reasoning_summary="Derived from reviewed rules.",
    special_case_notes="",
):
    return {
        "answer": answer,
        "status": status,
        "source_ruleset_keys": source_ruleset_keys or [],
        "source_rule_ids": source_rule_ids or [],
        "clause_references": clause_references or [],
        "reasoning_summary": reasoning_summary,
        "special_case_notes": special_case_notes,
    }


def test_questionnaire_schema_only_adds_supported_overtime_and_penalties_questions():
    schema = calculator_rules_response_json_schema()
    sections = schema["properties"]["questionnaire_answers"]["properties"]

    assert "casual_standard_overtime_multiplier" in sections["overtime"]["properties"]
    assert "public_holiday_overtime_multiplier" in sections["overtime"]["properties"]
    assert "live_span_start_hour" in sections["span"]["properties"]
    assert "casual_breach_penalty_multiplier" in sections["gap_between_shifts"]["properties"]
    assert "casual_ordinary_loading" not in sections["weekday_penalties"]["properties"]
    assert "top_up" not in sections
    assert "minimum_engagement" not in sections
    status_options = sections["core_hours"]["properties"][
        "day_worker_daily_limit_hours"
    ]["properties"]["status"]["enum"]
    assert "not_applicable" in status_options


def test_summarized_rules_retains_rule_markdown_needed_for_numeric_calculator_values():
    artifact = {
        "rules": [
            {
                "rule_id": "non-shiftworker-out-of-spread",
                "rule_markdown": (
                    "- Ordinary hours are between 7:00 am and 11:00 pm."
                ),
                "rule_plain_text": "Work outside the ordinary-hours spread is overtime.",
            }
        ]
    }

    summarized = summarized_rules(artifact)

    assert summarized[0]["rule_markdown"] == (
        "- Ordinary hours are between 7:00 am and 11:00 pm."
    )


def test_normalize_response_data_maps_questionnaire_to_calculator_fields():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(
                    8,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-1"],
                    clause_references=["13.7"],
                ),
                "shift_worker_daily_limit_hours": _answer(
                    10,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-2"],
                    clause_references=["26.2"],
                ),
                "day_worker_weekly_limit_hours": _answer(
                    38,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-3"],
                    clause_references=["13.2"],
                ),
                "shift_worker_weekly_limit_hours": _answer(
                    38,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-4"],
                    clause_references=["26.1"],
                ),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(
                    1.5,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-1"],
                    clause_references=["21.4"],
                ),
                "casual_standard_overtime_multiplier": _answer(1.875),
                "has_two_tier_overtime": _answer(
                    True,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-1"],
                    clause_references=["21.4"],
                ),
                "extended_overtime_multiplier": _answer(
                    2.0,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-1"],
                    clause_references=["21.4"],
                ),
                "casual_extended_overtime_multiplier": _answer(2.5),
                "higher_overtime_starts_after_hours": _answer(
                    2,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-1"],
                    clause_references=["21.4"],
                ),
                "extended_overtime_days": _answer(
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-1"],
                    clause_references=["21.4"],
                    reasoning_summary="The higher overtime tier applies only on weekdays.",
                ),
                "saturday_overtime_multiplier": _answer(
                    2.0,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-2"],
                    clause_references=["21.4"],
                ),
                "casual_saturday_overtime_multiplier": _answer(2.5),
                "sunday_overtime_multiplier": _answer(
                    2.0,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-3"],
                    clause_references=["21.4"],
                ),
                "casual_sunday_overtime_multiplier": _answer(2.5),
                "public_holiday_overtime_multiplier": _answer(2.5),
                "casual_public_holiday_overtime_multiplier": _answer(3.125),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(
                    True,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-5"],
                    clause_references=["13.3"],
                ),
                "live_span_start_hour": _answer(7),
                "live_span_cutoff_hour": _answer(
                    19,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-5"],
                    clause_references=["13.3"],
                    special_case_notes="Saturday has a narrower ordinary span.",
                ),
                "ordinary_span_summary": _answer(
                    "7:00 am to 7:00 pm Monday to Friday.",
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-5"],
                    clause_references=["13.3"],
                    special_case_notes="Saturday has a narrower ordinary span.",
                ),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(
                    "penalty",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["24.2"],
                ),
                "day_sunday_treatment": _answer(
                    "penalty",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-2"],
                    clause_references=["24.3"],
                ),
                "shift_saturday_treatment": _answer(
                    "penalty",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-3"],
                    clause_references=["31.1"],
                ),
                "shift_sunday_treatment": _answer(
                    "penalty",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-3"],
                    clause_references=["31.1"],
                ),
                "day_saturday_penalty_loading": _answer(
                    0.25,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["24.2"],
                ),
                "day_sunday_penalty_loading": _answer(
                    1.0,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-2"],
                    clause_references=["24.3"],
                ),
                "shift_saturday_penalty_loading": _answer(
                    0.5,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-3"],
                    clause_references=["31.1"],
                ),
                "shift_sunday_penalty_loading": _answer(
                    0.5,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-3"],
                    clause_references=["31.1"],
                ),
                "casual_day_saturday_penalty_loading": _answer(0.5),
                "casual_day_sunday_penalty_loading": _answer(1.25),
                "casual_shift_saturday_penalty_loading": _answer(0.75),
                "casual_shift_sunday_penalty_loading": _answer(1.0),
                "day_public_holiday_treatment": _answer("overtime"),
                "shift_public_holiday_treatment": _answer("penalty"),
                "day_public_holiday_penalty_loading": _answer(0),
                "shift_public_holiday_penalty_loading": _answer(1.5),
                    "casual_day_public_holiday_penalty_loading": _answer(1.75),
                "casual_shift_public_holiday_penalty_loading": _answer(1.75),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(
                    True,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-4"],
                    clause_references=["22.2"],
                ),
                "standard_minimum_break_hours": _answer(
                    10,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-4"],
                    clause_references=["22.2"],
                    special_case_notes="Shiftworkers use 8 hours under clause 30.",
                ),
                "breach_penalty_multiplier": _answer(
                    1.0,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-5"],
                    clause_references=["22.4"],
                    special_case_notes="Shiftworkers use 8 hours under clause 30.",
                ),
                "casual_breach_penalty_multiplier": _answer(1.25),
                "special_case_thresholds": _answer(
                    [
                        {
                            "worker_group": "shiftworkers",
                            "threshold_hours": 8,
                            "notes": "Shiftworker overtime rest break threshold.",
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-6"],
                    clause_references=["30.3"],
                    special_case_notes="Shiftworkers use 8 hours under clause 30.",
                ),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "afternoon_shift",
                            "type": "shift_based",
                            "basis": "end",
                            "start_hour": 19,
                            "end_hour": 24,
                            "rate": 0.15,
                            "casual_rate": 0.25,
                            "description": "Standard afternoon shift penalty.",
                            "applies_to": ["shift"],
                            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
                        },
                        {
                            "code_name": "shiftwork_saturday_sunday_public_holiday",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 0,
                            "end_hour": 24,
                            "rate": 0.5,
                            "casual_rate": 0.75,
                            "description": "Weekend shift penalty that should not be in live weekday penalties.",
                            "applies_to": ["shift"],
                            "days": ["Saturday", "Sunday"],
                        },
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-7"],
                    clause_references=["31.1"],
                ),
                "time_based_penalties": _answer(
                    [
                        {
                            "code_name": "nonshift_saturday_ordinary_hours",
                            "type": "time_based",
                            "basis": "start",
                            "start_hour": 7,
                            "end_hour": 19,
                            "rate": 0.25,
                            "casual_rate": 0.5,
                            "description": "Saturday day rule that should not leak into weekday penalties.",
                            "applies_to": ["day"],
                            "days": ["Saturday"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-7"],
                    clause_references=["31.1"],
                ),
                "other_penalty_notes": _answer(
                    "Permanent night shift is a special case and is not included as a live rule.",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-8"],
                    clause_references=["31.1"],
                    special_case_notes="Permanent night shift excluded from live calculator fields.",
                ),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000002")

    assert normalized["award_code"] == "MA000002"
    rules = normalized["calculator_rules"]
    assert rules["ORDINARY_TIME_RULES"]["daily"]["shift"] == 10
    assert rules["ORDINARY_TIME_RULES"]["daily"]["day"] == 8
    assert rules["ORDINARY_TIME_RULES"]["span_overtime"]["day"]["default"] == {
        "start": 7,
        "end": 19,
        "enabled": True,
    }
    assert rules["GAP_BETWEEN_SHIFTS_RULE"]["minimum_hours"] == 10
    assert rules["GAP_BETWEEN_SHIFTS_RULE"]["loading"] == 1.0
    assert rules["GAP_BETWEEN_SHIFTS_RULE"]["casual_rate"] == 1.25
    assert rules["PAY_RATES"]["overtime"]["two_tier"]["enabled"] is True
    assert rules["PAY_RATES"]["overtime"]["two_tier"]["threshold"] == 2
    assert rules["PAY_RATES"]["overtime"]["two_tier"]["days"] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]
    assert rules["ORDINARY_HOUR_PENALTIES"] == {
        "afternoon_shift": {
            "type": "shift_based",
            "basis": "end",
            "start": 19,
            "end": 24,
            "rate": 0.15,
            "casual_rate": 0.25,
            "description": "Standard afternoon shift penalty.",
            "applies_to": ["shift"],
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        }
    }
    assert rules["PAY_RATES"]["overtime"]["saturday"]["multiplier"] == 2.0
    assert rules["PAY_RATES"]["overtime"]["weekday"]["casual"] == 1.875
    assert rules["PAY_RATES"]["overtime"]["extended"]["casual"] == 2.5
    assert rules["PAY_RATES"]["overtime"]["public_holiday"] == {
        "multiplier": 2.5,
        "casual": 3.125,
    }
    assert rules["DAY_TREATMENT_RULES"]["Saturday"]["shift"] == {
        "base_classification": "ordinary",
        "ordinary_loading": 0.5,
        "casual_rate": 0.75,
        "overtime_rate_key": "saturday",
    }
    assert rules["DAY_TREATMENT_RULES"]["Saturday"]["day"] == {
        "base_classification": "ordinary",
        "ordinary_loading": 0.25,
        "casual_rate": 0.5,
        "overtime_rate_key": "saturday",
    }
    assert rules["DAY_TREATMENT_RULES"]["public_holiday"]["shift"] == {
        "base_classification": "ordinary",
        "ordinary_loading": 1.5,
        "casual_rate": 1.75,
        "overtime_rate_key": "public_holiday",
    }
    assert rules["DAY_TREATMENT_RULES"]["public_holiday"]["day"] == {
        "base_classification": "overtime",
        "ordinary_loading": 0,
        "casual_rate": 0,
        "overtime_rate_key": "public_holiday",
    }
    assert rules["ORDINARY_TIME_RULES"]["ordinary_rates"]["casual_loading"] == 0
    assert any(
        missing["field"] == "ORDINARY_TIME_RULES.ordinary_rates.casual_loading"
        for missing in normalized["missing_from_analysis"]
    )
    assert rules["ORDINARY_TIME_RULES"]["period"]["part_time_uses_contracted_hours"] is True
    assert normalized["field_evidence"]["GAP_BETWEEN_SHIFTS_RULE"]["special_case_notes"] == (
        "Shiftworkers use 8 hours under clause 30."
    )

    no_live_span_cutoff_response = deepcopy(response_data)
    no_live_span_cutoff_response["questionnaire_answers"]["span"][
        "live_span_cutoff_hour"
    ]["answer"] = None

    normalized_without_live_span_cutoff = normalize_response_data(
        no_live_span_cutoff_response,
        award_code="MA000002",
    )

    assert normalized_without_live_span_cutoff["calculator_rules"]["ORDINARY_TIME_RULES"][
        "span_overtime"
    ] == {}
    assert "live span-overtime calculation has been disabled" in (
        normalized_without_live_span_cutoff["validation_warnings"][0]
    )


def test_normalize_response_data_preserves_source_rule_ids_without_validation():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(
                    10,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["missing-rule"],
                    clause_references=["13.7"],
                ),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None, status="defaulted"),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer([], status="not_found"),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000009")

    ordinary_evidence = normalized["field_evidence"]["ORDINARY_TIME_RULES"]
    assert ordinary_evidence["daily.shift"]["status"] == "derived"
    assert ordinary_evidence["period.shift"]["status"] == "defaulted"
    assert ordinary_evidence["daily.shift"]["source_rule_ids"] == ["missing-rule"]

def test_normalize_response_data_preserves_source_rule_ids_verbatim():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(
                    "penalty",
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=[
                        "saturday-shiftworker-ordinary-hours-time-and-a-half"
                    ],
                    clause_references=["Clause 23.5(b)"],
                ),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(
                    0.5,
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=[
                        "saturday-shiftworker-ordinary-hours-time-and-a-half"
                    ],
                    clause_references=["Clause 23.5(b)"],
                ),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer([], status="not_found"),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000120")

    assert normalized["field_evidence"]["DAY_TREATMENT_RULES"]["source_rule_ids"] == [
        "saturday-shiftworker-ordinary-hours-time-and-a-half"
    ]


def test_normalize_response_data_accepts_dotted_am_pm_shift_penalty_times():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "early_morning_shift_loading",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 5,
                            "end_hour": 6,
                            "rate": 0.1,
                            "description": (
                                "Shiftworkers: early morning shift starts at or after "
                                "5.00 am and before 6.00 am; the entire shift attracts "
                                "a 10% loading."
                            ),
                            "applies_to": ["shift"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["23.4(d)(i)"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000120")

    assert normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"]["early_morning_shift"] == {
        "type": "shift_based",
        "basis": "start",
        "start": 5,
        "end": 6,
        "rate": 0.1,
        "casual_rate": 0.1,
        "description": (
            "Shiftworkers: early morning shift starts at or after 5.00 am and "
            "before 6.00 am; the entire shift attracts a 10% loading."
        ),
        "applies_to": ["shift"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }
    assert not any(
        missing["field"].endswith(".casual_rate")
        and missing["field"].startswith("ORDINARY_HOUR_PENALTIES")
        for missing in normalized["missing_from_analysis"]
    )


def test_normalize_response_data_rounds_fractional_penalty_hours_to_whole_hours():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "afternoon_shift_loading",
                            "type": "shift_based",
                            "basis": "end",
                            "start_hour": 18.5,
                            "end_hour": 24,
                            "rate": 0.15,
                            "description": (
                                "Afternoon shift for shiftworkers: shift finishing after "
                                "6.30 pm and at or before midnight."
                            ),
                            "applies_to": ["shift"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["23.4(d)(ii)"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000120")

    assert normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"]["afternoon_shift"] == {
        "type": "shift_based",
        "basis": "end",
        "start": 19,
        "end": 24,
        "rate": 0.15,
        "casual_rate": 0.15,
        "description": (
            "Afternoon shift for shiftworkers: shift finishing after 6.30 pm and "
            "at or before midnight."
        ),
        "applies_to": ["shift"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }


def test_normalize_response_data_shortens_penalty_names():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                        [
                            {
                                "code_name": "early_morning_shift_allowance_10pct",
                                "type": "shift_based",
                                "basis": "start",
                                "start_hour": 4,
                                "end_hour": 6,
                            "rate": 0.1,
                            "description": "10% shift allowance for shifts starting from 04:00 to 06:00.",
                            "applies_to": ["shift"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["31.1"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000018")

    assert "early_morning_shift" in normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"]


def test_normalize_response_data_uses_time_suffix_only_when_short_names_collide():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "shift_allowance_10_percent_10am_to_1pm",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 10,
                            "end_hour": 13,
                            "rate": 0.1,
                            "description": "10% shift allowance for shifts starting from 10:00 to 13:00.",
                            "applies_to": ["shift"],
                        },
                        {
                            "code_name": "shift_allowance_12_5_percent_1pm_to_4pm",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 13,
                            "end_hour": 16,
                            "rate": 0.125,
                            "description": "12.5% shift allowance for shifts starting from 13:00 to 16:00.",
                            "applies_to": ["shift"],
                        },
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["31.1"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000018")

    assert "shift" in normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"]
    assert "shift_start_13_to_16" in normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"]


def test_normalize_response_data_records_penalty_time_text_mismatch_as_warning():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "shift_allowance_15_percent_4pm_to_4am",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 16,
                            "end_hour": 24,
                            "rate": 0.15,
                            "description": "Applies to shifts commencing 16:00 to before 04:00.",
                            "applies_to": ["shift"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["31.1"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000018")

    assert len(normalized["validation_warnings"]) == 2
    assert "structured hours do not match" in normalized["validation_warnings"][0]
    assert "generated using assumptions or defaults" in normalized[
        "validation_warnings"
    ][1]


def test_normalize_response_data_accepts_ampm_penalty_time_with_midnight():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(None),
                "shift_worker_daily_limit_hours": _answer(None),
                "day_worker_weekly_limit_hours": _answer(None),
                "shift_worker_weekly_limit_hours": _answer(None),
            },
            "overtime": {
                "standard_overtime_multiplier": _answer(None),
                "has_two_tier_overtime": _answer(False),
                "extended_overtime_multiplier": _answer(None),
                "higher_overtime_starts_after_hours": _answer(None),
                "extended_overtime_days": _answer([], status="not_found"),
                "saturday_overtime_multiplier": _answer(None),
                "sunday_overtime_multiplier": _answer(None),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(False),
                "live_span_cutoff_hour": _answer(None),
                "ordinary_span_summary": _answer(None),
            },
            "weekend_treatment": {
                "day_saturday_treatment": _answer(None),
                "day_sunday_treatment": _answer(None),
                "shift_saturday_treatment": _answer(None),
                "shift_sunday_treatment": _answer(None),
                "day_saturday_penalty_loading": _answer(None),
                "day_sunday_penalty_loading": _answer(None),
                "shift_saturday_penalty_loading": _answer(None),
                "shift_sunday_penalty_loading": _answer(None),
            },
            "gap_between_shifts": {
                "minimum_break_required": _answer(False),
                "standard_minimum_break_hours": _answer(None),
                "breach_penalty_multiplier": _answer(None),
                "special_case_thresholds": _answer([], status="not_found"),
            },
            "weekday_penalties": {
                "shift_based_penalties": _answer(
                    [
                        {
                            "code_name": "afternoon_shift_allowance",
                            "type": "shift_based",
                            "basis": "end",
                            "start_hour": 19,
                            "end_hour": 24,
                            "rate": 0.15,
                            "description": (
                                "Afternoon shift allowance for shiftworkers finishing "
                                "after 6:30 pm and at or before midnight."
                            ),
                            "applies_to": ["shift"],
                        }
                    ],
                    source_ruleset_keys=["penalties"],
                    source_rule_ids=["penalty-rule-1"],
                    clause_references=["31.1"],
                ),
                "time_based_penalties": _answer([], status="not_found"),
                "other_penalty_notes": _answer(None, status="not_found"),
            },
        }
    }

    normalized = normalize_response_data(response_data, award_code="MA000120")

    penalty = next(
        iter(normalized["calculator_rules"]["ORDINARY_HOUR_PENALTIES"].values())
    )

    assert penalty["start"] == 19
    assert penalty["end"] == 24


def test_render_python_text_matches_calculator_class_shape():
    normalized_data = {
        "schema_version": "calculator-rules-python-v2",
        "award_code": "MA000002",
        "award_title": "This is the Clerks—Private Sector Award 2020.",
        "calculator_rules": {
            "SHIFT_RULES": {
                "default_break_hours": 0.5,
                "minimum_paid_shift_hours": {},
            },
            "ORDINARY_TIME_RULES": {
                "span_overtime": {
                    "day": {
                        "default": {"start": None, "end": 19, "enabled": True}
                    }
                },
                "daily": {"variation": "worker_type", "day": 8, "shift": 10},
                "long_day": {"uses_per_week": 0, "ordinary_limit_hours": None},
                "period": {
                    "variation": "worker_type",
                    "day": 38,
                    "shift": 38,
                    "basis": "weekly",
                    "max_work_days": None,
                    "max_work_days_basis": "weekly",
                    "part_time_uses_contracted_hours": True,
                },
                "ordinary_rates": {"casual_loading": 0},
            },
            "DAY_TREATMENT_RULES": {},
            "PAY_RATES": {"overtime": {}},
            "GAP_BETWEEN_SHIFTS_RULE": {
                "minimum_hours": 10,
                "loading": 1.0,
                "casual_rate": 1.0,
            },
            "ORDINARY_HOUR_PENALTIES": {
                "afternoon_shift": {
                    "type": "shift_based",
                    "basis": "end",
                    "start": 19,
                    "end": 24,
                    "rate": 0.15,
                    "casual_rate": 0.15,
                    "description": "Standard afternoon shift penalty.",
                    "applies_to": ["shift"],
                    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                }
            },
            "TOP_UP_RULES": {"part_time": True, "full_time": True},
        },
        "field_evidence": {
            "ordinary_hours_limit_daily": {
                "status": "derived",
                "source_ruleset_keys": ["overtime_creation"],
                "source_rule_ids": ["creation-rule-1"],
                "clause_references": ["13.7"],
                "reasoning_summary": "Derived from rule 13.7.",
                "special_case_notes": "",
            }
        },
        "missing_from_analysis": [
            {
                "field": "SHIFT_RULES.minimum_paid_shift_hours",
                "default_value": {},
                "reason": "Minimum engagement is not included in the current analysis.",
            }
        ],
    }

    rendered = render_python_text(normalized_data)

    assert "class ClerksPrivateSectorRules:" in rendered
    assert "SHIFT_RULES = {'default_break_hours': 0.5" in rendered
    assert "ORDINARY_TIME_RULES = {'span_overtime'" in rendered
    assert "DAY_TREATMENT_RULES = {}" in rendered
    assert "PAY_RATES = {'overtime': {}}" in rendered
    assert "GAP_BETWEEN_SHIFTS_RULE = {'minimum_hours': 10" in rendered
    assert "ORDINARY_HOUR_PENALTIES = {'afternoon_shift'" in rendered
    assert "TOP_UP_RULES = {'part_time': True, 'full_time': True}" in rendered
    assert "ORDINARY_HOURS_LIMIT_DAILY" not in rendered
    assert "'basis': 'end'" in rendered
    assert "'casual_rate': 0.15" in rendered
    assert "# RULES EXCLUDED FROM THE ANALYSIS" in rendered
    assert (
        "# - Minimum paid shift: disabled because minimum engagement was not covered "
        "by the analysis."
    ) in rendered
    assert "# FIELD_EVIDENCE =" in rendered
    assert "# GENERATION_METADATA =" in rendered

    parsed_module = ast.parse(rendered)
    rules_class = next(
        node for node in parsed_module.body if isinstance(node, ast.ClassDef)
    )
    assigned_attributes = {
        target.id
        for statement in rules_class.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name)
    }
    assert assigned_attributes == {
        "SHIFT_RULES",
        "ORDINARY_TIME_RULES",
        "DAY_TREATMENT_RULES",
        "PAY_RATES",
        "GAP_BETWEEN_SHIFTS_RULE",
        "ORDINARY_HOUR_PENALTIES",
        "TOP_UP_RULES",
    }


def test_render_python_text_puts_validation_warnings_before_the_calculator_class():
    normalized_data = {
        "schema_version": "1.0",
        "award_code": "MA000002",
        "calculator_rules": {
            "SHIFT_RULES": {},
            "ORDINARY_TIME_RULES": {},
            "DAY_TREATMENT_RULES": {},
            "PAY_RATES": {},
            "GAP_BETWEEN_SHIFTS_RULE": {},
            "ORDINARY_HOUR_PENALTIES": {},
            "TOP_UP_RULES": {},
        },
        "field_evidence": {},
        "validation_warnings": ["A live span cutoff is not available."],
    }

    rendered = render_python_text(normalized_data)

    assert "# IMPORTANT: REVIEW REQUIRED BEFORE USING THIS CALCULATOR" in rendered
    assert rendered.index("# IMPORTANT:") < rendered.index("class MA000002Rules:")
def test_align_questionnaire_populates_fields_that_are_not_applicable():
    response_data = {
        "questionnaire_answers": {
            "weekend_treatment": {
                "day_saturday_treatment": _answer("overtime"),
                "day_saturday_penalty_loading": _answer(None, status="not_found"),
                "casual_day_saturday_penalty_loading": _answer(
                    0.75,
                    status="derived",
                ),
            },
            "gap_between_shifts": {
                "casual_breach_penalty_multiplier": _answer(
                    None,
                    status="not_found",
                    reasoning_summary="The payment expressly excludes casual employees.",
                ),
            },
            "weekday_penalties": {
                "time_based_penalties": _answer([], status="not_found"),
                "casual_ordinary_loading": _answer(0.25),
            },
        }
    }

    aligned = align_questionnaire_to_calculator_contract(response_data)
    answers = aligned["questionnaire_answers"]

    assert answers["weekend_treatment"]["day_saturday_penalty_loading"]["answer"] == 0
    assert answers["weekend_treatment"]["day_saturday_penalty_loading"]["status"] == "not_applicable"
    assert answers["weekend_treatment"]["casual_day_saturday_penalty_loading"]["answer"] == 0
    assert answers["gap_between_shifts"]["casual_breach_penalty_multiplier"]["answer"] == 0
    assert answers["gap_between_shifts"]["casual_breach_penalty_multiplier"]["status"] == "not_applicable"
    assert answers["weekday_penalties"]["time_based_penalties"]["status"] == "not_applicable"
    assert "casual_ordinary_loading" not in answers["weekday_penalties"]
    assert response_data["questionnaire_answers"]["weekend_treatment"][
        "day_saturday_penalty_loading"
    ]["answer"] is None


def test_align_questionnaire_marks_day_night_worker_mapping_as_an_assumption():
    response_data = {
        "questionnaire_answers": {
            "core_hours": {
                "day_worker_daily_limit_hours": _answer(
                    8,
                    reasoning_summary="The source provides an 8-hour day shift.",
                ),
                "shift_worker_daily_limit_hours": _answer(
                    10,
                    reasoning_summary="The source provides a 10-hour night shift.",
                ),
            }
        }
    }

    aligned = align_questionnaire_to_calculator_contract(response_data)
    core_hours = aligned["questionnaire_answers"]["core_hours"]

    assert core_hours["day_worker_daily_limit_hours"]["status"] == "defaulted"
    assert core_hours["shift_worker_daily_limit_hours"]["status"] == "defaulted"
    assert "Contract-alignment assumption" in core_hours[
        "shift_worker_daily_limit_hours"
    ]["special_case_notes"]
