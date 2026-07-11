from copy import deepcopy

from src.step_6_1_generate_calculator_yaml.core import (
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
                "sunday_overtime_multiplier": _answer(
                    2.0,
                    source_ruleset_keys=["overtime_consequence"],
                    source_rule_ids=["consequence-rule-3"],
                    clause_references=["21.4"],
                ),
            },
            "span": {
                "day_workers_have_span_overtime": _answer(
                    True,
                    source_ruleset_keys=["overtime_creation"],
                    source_rule_ids=["creation-rule-5"],
                    clause_references=["13.3"],
                ),
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
                            "description": "Standard afternoon shift penalty.",
                            "applies_to": ["shift"],
                        },
                        {
                            "code_name": "shiftwork_saturday_sunday_public_holiday",
                            "type": "shift_based",
                            "basis": "start",
                            "start_hour": 0,
                            "end_hour": 24,
                            "rate": 0.5,
                            "description": "Weekend shift penalty that should not be in live weekday penalties.",
                            "applies_to": ["shift"],
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
                            "description": "Saturday day rule that should not leak into weekday penalties.",
                            "applies_to": ["day"],
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
    assert normalized["calculator_rules"]["ordinary_hours_limit_daily"] == 10
    assert normalized["calculator_rules"]["day_worker_ordinary_hours_daily"] == 8
    assert normalized["calculator_rules"]["apply_span_overtime"] is True
    assert normalized["calculator_rules"]["span_overtime_hour"] == 19
    assert normalized["calculator_rules"]["gap_penalty_hours"] == 10
    assert normalized["calculator_rules"]["gap_penalty_rate"] == 1.0
    assert normalized["calculator_rules"]["two_tier_overtime"] is True
    assert normalized["calculator_rules"]["two_tier_overtime_threshold"] == 2
    assert normalized["calculator_rules"]["extended_overtime_days"] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]
    assert normalized["calculator_rules"]["penalties"] == {
        "afternoon_shift": {
            "type": "shift_based",
            "basis": "end",
            "start": 19,
            "end": 24,
            "rate": 0.15,
            "description": "Standard afternoon shift penalty.",
            "applies_to": ["shift"],
        }
    }
    assert normalized["calculator_rules"]["saturday_overtime_rate"] == 2.0
    assert normalized["calculator_rules"]["weekend_rules"]["shift"]["Saturday"] == {
        "is_overtime": False,
        "rate": None,
        "penalty_rate": 0.5,
    }
    assert normalized["calculator_rules"]["weekend_rules"]["day"]["Saturday"] == {
        "is_overtime": True,
    }
    assert normalized["calculator_rules"]["use_contracted_hours_for_pt_overtime"] is True
    assert normalized["field_evidence"]["gap_penalty_hours"]["special_case_notes"] == (
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

    assert normalized_without_live_span_cutoff["calculator_rules"]["apply_span_overtime"] is False
    assert normalized_without_live_span_cutoff["calculator_rules"]["span_overtime_hour"] is None
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

    assert normalized["field_evidence"]["ordinary_hours_limit_daily"]["status"] == "derived"
    assert normalized["field_evidence"]["ordinary_hours_limit_weekly"]["status"] == "defaulted"
    assert normalized["field_evidence"]["ordinary_hours_limit_daily"]["source_rule_ids"] == ["missing-rule"]

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

    assert normalized["field_evidence"]["weekend_rules"]["source_rule_ids"] == [
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

    assert normalized["calculator_rules"]["penalties"]["early_morning_shift"] == {
        "type": "shift_based",
        "basis": "start",
        "start": 5,
        "end": 6,
        "rate": 0.1,
        "description": (
            "Shiftworkers: early morning shift starts at or after 5.00 am and "
            "before 6.00 am; the entire shift attracts a 10% loading."
        ),
        "applies_to": ["shift"],
    }


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

    assert normalized["calculator_rules"]["penalties"]["afternoon_shift"] == {
        "type": "shift_based",
        "basis": "end",
        "start": 19,
        "end": 24,
        "rate": 0.15,
        "description": (
            "Afternoon shift for shiftworkers: shift finishing after 6.30 pm and "
            "at or before midnight."
        ),
        "applies_to": ["shift"],
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

    assert "early_morning_shift" in normalized["calculator_rules"]["penalties"]


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

    assert "shift" in normalized["calculator_rules"]["penalties"]
    assert "shift_start_13_to_16" in normalized["calculator_rules"]["penalties"]


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

    assert len(normalized["validation_warnings"]) == 1
    assert "structured hours do not match" in normalized["validation_warnings"][0]


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

    penalty = next(iter(normalized["calculator_rules"]["penalties"].values()))

    assert penalty["start"] == 19
    assert penalty["end"] == 24


def test_render_python_text_matches_calculator_class_shape():
    normalized_data = {
        "schema_version": "calculator-rules-python-v1",
        "award_code": "MA000002",
        "award_title": "This is the Clerks—Private Sector Award 2020.",
        "calculator_rules": {
            "ordinary_hours_limit_daily": 10,
            "ordinary_hours_limit_weekly": 38,
            "day_worker_ordinary_hours_daily": 8,
            "day_worker_ordinary_hours_weekly": 38,
            "standard_overtime_rate": 1.5,
            "extended_overtime_rate": 2.0,
            "sunday_overtime_rate": 2.0,
            "saturday_overtime_rate": 2.0,
            "apply_span_overtime": True,
            "span_overtime_hour": 19,
            "gap_penalty_hours": 10,
            "gap_penalty_rate": 1.0,
            "two_tier_overtime": True,
            "two_tier_overtime_threshold": 2,
            "extended_overtime_days": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ],
            "use_contracted_hours_for_pt_overtime": True,
            "pt_employees_entitled_to_contracted_topup": True,
            "ft_employees_entitled_to_contracted_topup": True,
            "penalties": {
                "afternoon_shift": {
                    "type": "shift_based",
                    "basis": "end",
                    "start": 19,
                    "end": 24,
                    "rate": 0.15,
                    "description": "Standard afternoon shift penalty.",
                    "applies_to": ["shift"],
                }
            },
            "hours_pen_rules": {},
            "weekend_rules": {
                "day": {
                    "Saturday": {
                        "is_overtime": True,
                    }
                },
                "shift": {
                    "Saturday": {
                        "is_overtime": False,
                        "rate": None,
                        "penalty_rate": 0.5,
                    }
                }
            },
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
    }

    rendered = render_python_text(normalized_data)

    assert "class ClerksPrivateSectorRules:" in rendered
    assert "ORDINARY_HOURS_LIMIT_DAILY = 10" in rendered
    assert "USE_CONTRACTED_HOURS_FOR_PT_OVERTIME = True" in rendered
    assert "EXTENDED_OVERTIME_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']" in rendered
    assert "DEFAULT_BREAK = 0.5" in rendered
    assert "'basis': 'end'" in rendered
    assert "'penalty_rate': 0.5" in rendered
    assert "# FIELD_EVIDENCE =" in rendered
    assert "# GENERATION_METADATA =" in rendered


def test_render_python_text_puts_validation_warnings_before_the_calculator_class():
    normalized_data = {
        "schema_version": "1.0",
        "award_code": "MA000002",
        "calculator_rules": {
            "ordinary_hours_limit_daily": None,
            "ordinary_hours_limit_weekly": None,
            "day_worker_ordinary_hours_daily": None,
            "day_worker_ordinary_hours_weekly": None,
            "standard_overtime_rate": None,
            "extended_overtime_rate": None,
            "sunday_overtime_rate": None,
            "saturday_overtime_rate": None,
            "apply_span_overtime": False,
            "span_overtime_hour": None,
            "gap_penalty_hours": None,
            "gap_penalty_rate": None,
            "penalties": {},
            "hours_pen_rules": {},
            "weekend_rules": {},
            "two_tier_overtime": False,
            "two_tier_overtime_threshold": None,
            "extended_overtime_days": [],
            "use_contracted_hours_for_pt_overtime": True,
            "pt_employees_entitled_to_contracted_topup": True,
            "ft_employees_entitled_to_contracted_topup": True,
        },
        "field_evidence": {},
        "validation_warnings": ["A live span cutoff is not available."],
    }

    rendered = render_python_text(normalized_data)

    assert "# IMPORTANT: REVIEW REQUIRED BEFORE USING THIS CALCULATOR" in rendered
    assert rendered.index("# IMPORTANT:") < rendered.index("class MA000002Rules:")
