from src.step_6_1_generate_calculator_yaml.core import (
    normalize_response_data,
    render_python_text,
)


def test_normalize_response_data_applies_default_booleans_and_object_defaults():
    response_data = {
        "calculator_rules": {
            "ordinary_hours_limit_daily": 10,
            "ordinary_hours_limit_weekly": 38,
            "day_worker_ordinary_hours_daily": 8,
            "day_worker_ordinary_hours_weekly": 38,
            "standard_overtime_rate": 1.5,
            "extended_overtime_rate": 2.0,
            "sunday_overtime_rate": 2.0,
            "saturday_overtime_rate": 1.5,
            "saturday_penalty_rate": 0.25,
            "sunday_penalty_rate": 0.5,
            "apply_span_overtime": False,
            "span_overtime_hour": 18,
            "gap_penalty_hours": 10,
            "gap_penalty_rate": 1.0,
            "penalties": {"afternoon_shift": {"rate": 0.1}},
            "hours_pen_rules": None,
            "weekend_rules": {"day": {"Saturday": {"is_overtime": True, "rate": 1.5}}},
            "two_tier_overtime": True,
            "two_tier_overtime_threshold": 2,
        },
        "field_evidence": {
            "ordinary_hours_limit_daily": {
                "status": "derived",
                "source_ruleset_keys": ["overtime_creation"],
                "source_rule_ids": ["creation-rule-1"],
                "clause_references": ["15.1"],
                "reasoning_summary": "Derived from reviewed creation rules.",
            },
            "ordinary_hours_limit_weekly": {
                "status": "derived",
                "source_ruleset_keys": ["overtime_creation"],
                "source_rule_ids": ["creation-rule-1"],
                "clause_references": ["15.1"],
                "reasoning_summary": "Derived from reviewed creation rules.",
            },
        },
    }

    normalized = normalize_response_data(
        response_data,
        award_code="MA000009",
        known_rule_ids={
            "overtime_creation": {"creation-rule-1"},
            "overtime_consequence": set(),
            "penalties": set(),
        },
    )

    assert normalized["award_code"] == "MA000009"
    assert normalized["calculator_rules"]["use_contracted_hours_for_pt_overtime"] is True
    assert normalized["calculator_rules"]["pt_employees_entitled_to_contracted_topup"] is True
    assert normalized["calculator_rules"]["ft_employees_entitled_to_contracted_topup"] is True
    assert normalized["calculator_rules"]["hours_pen_rules"] == {}
    assert normalized["field_evidence"]["use_contracted_hours_for_pt_overtime"]["status"] == "defaulted"


def test_normalize_response_data_flattens_wrapped_review_values():
    response_data = {
        "calculator_rules": {
            "ordinary_hours_limit_daily": {
                "value": 10,
                "unit": "hours",
                "evidence_status": "derived",
            },
            "ordinary_hours_limit_weekly": {
                "value": 38,
                "unit": "hours",
                "evidence_status": "derived",
            },
            "day_worker_ordinary_hours_daily": None,
            "day_worker_ordinary_hours_weekly": 38,
            "standard_overtime_rate": {"value": 150, "unit": "percent"},
            "extended_overtime_rate": {"value": 200, "unit": "percent"},
            "sunday_overtime_rate": {"value": 200, "unit": "percent"},
            "saturday_overtime_rate": None,
            "saturday_penalty_rate": {"value": 125, "unit": "percent"},
            "sunday_penalty_rate": {"value": 200, "unit": "percent"},
            "apply_span_overtime": {"value": True},
            "span_overtime_hour": None,
            "gap_penalty_hours": None,
            "gap_penalty_rate": {"value": 200, "unit": "percent"},
            "penalties": {
                "weekend": {"day_worker": {"saturday": {"type": "penalty", "rate": 125}}},
                "evidence_status": "derived",
            },
            "hours_pen_rules": None,
            "weekend_rules": {
                "day_worker": {"saturday": {"basis": "penalty", "rate": 125}},
                "evidence_status": "derived",
            },
            "two_tier_overtime": {"value": True},
            "two_tier_overtime_threshold": {
                "day_worker": {"daily_hours": 2, "weekly_hours": None},
                "shiftworker": {"daily_hours": 2, "weekly_hours": 3},
                "evidence_status": "derived",
            },
        },
        "field_evidence": {},
    }

    normalized = normalize_response_data(
        response_data,
        award_code="MA000002",
        known_rule_ids={
            "overtime_creation": set(),
            "overtime_consequence": set(),
            "penalties": set(),
        },
    )

    assert normalized["calculator_rules"]["ordinary_hours_limit_daily"] == 10
    assert normalized["calculator_rules"]["standard_overtime_rate"] == 150
    assert normalized["calculator_rules"]["apply_span_overtime"] is True
    assert normalized["calculator_rules"]["span_overtime_hour"] is None
    assert normalized["calculator_rules"]["saturday_overtime_rate"] is None
    assert normalized["calculator_rules"]["penalties"] == {
        "weekend": {"day_worker": {"saturday": {"type": "penalty", "rate": 125}}}
    }
    assert normalized["calculator_rules"]["weekend_rules"] == {
        "day_worker": {"saturday": {"basis": "penalty", "rate": 125}}
    }
    assert normalized["calculator_rules"]["gap_penalty_hours"] is None
    assert normalized["calculator_rules"]["two_tier_overtime_threshold"] == {
        "day_worker": {"daily_hours": 2, "weekly_hours": None},
        "shiftworker": {"daily_hours": 2, "weekly_hours": 3},
    }


def test_normalize_response_data_rejects_unknown_rule_ids():
    response_data = {
        "calculator_rules": {
            "ordinary_hours_limit_daily": None,
            "ordinary_hours_limit_weekly": None,
            "day_worker_ordinary_hours_daily": None,
            "day_worker_ordinary_hours_weekly": None,
            "standard_overtime_rate": None,
            "extended_overtime_rate": None,
            "sunday_overtime_rate": None,
            "saturday_overtime_rate": None,
            "saturday_penalty_rate": None,
            "sunday_penalty_rate": None,
            "apply_span_overtime": None,
            "span_overtime_hour": None,
            "gap_penalty_hours": None,
            "gap_penalty_rate": None,
            "penalties": None,
            "hours_pen_rules": None,
            "weekend_rules": None,
            "two_tier_overtime": None,
            "two_tier_overtime_threshold": None,
        },
        "field_evidence": {
            "ordinary_hours_limit_daily": {
                "status": "derived",
                "source_ruleset_keys": ["overtime_creation"],
                "source_rule_ids": ["missing-rule"],
                "clause_references": ["15.1"],
                "reasoning_summary": "Bad source id.",
            },
        },
    }

    try:
        normalize_response_data(
            response_data,
            award_code="MA000009",
            known_rule_ids={
                "overtime_creation": {"creation-rule-1"},
                "overtime_consequence": set(),
                "penalties": set(),
            },
        )
    except Exception as exc:
        assert "unknown rule_id" in str(exc)
    else:
        raise AssertionError("Expected unknown rule ids to fail validation")


def test_render_python_text_matches_calculator_class_shape():
    normalized_data = {
        "schema_version": "calculator-rules-python-v1",
        "award_code": "MA000002",
        "award_title": "This is the Clerks—Private Sector Award 2020.",
        "calculator_rules": {
            "ordinary_hours_limit_daily": 10,
            "ordinary_hours_limit_weekly": 38,
            "day_worker_ordinary_hours_daily": None,
            "day_worker_ordinary_hours_weekly": 38,
            "standard_overtime_rate": 1.5,
            "extended_overtime_rate": 2.0,
            "sunday_overtime_rate": 2.0,
            "saturday_overtime_rate": 1.5,
            "saturday_penalty_rate": 1.25,
            "sunday_penalty_rate": 2.0,
            "apply_span_overtime": True,
            "span_overtime_hour": None,
            "gap_penalty_hours": None,
            "gap_penalty_rate": 2.0,
            "penalties": {"afternoon_shift": {"rate": 0.15}},
            "hours_pen_rules": {},
            "weekend_rules": {"day": {"Saturday": {"is_overtime": True, "rate": 1.5}}},
            "two_tier_overtime": True,
            "two_tier_overtime_threshold": 2,
            "use_contracted_hours_for_pt_overtime": True,
            "pt_employees_entitled_to_contracted_topup": True,
            "ft_employees_entitled_to_contracted_topup": True,
        },
        "field_evidence": {
            "ordinary_hours_limit_daily": {
                "status": "derived",
                "source_ruleset_keys": ["overtime_creation"],
                "source_rule_ids": ["creation-rule-1"],
                "clause_references": ["15.1"],
                "reasoning_summary": "Derived from rule 15.1.",
            }
        },
    }

    rendered = render_python_text(normalized_data)

    assert "class ClerksPrivateSectorRules:" in rendered
    assert "ORDINARY_HOURS_LIMIT_DAILY = 10" in rendered
    assert "USE_CONTRACTED_HOURS_FOR_PT_OVERTIME = True" in rendered
    assert "DEFAULT_BREAK = 0.5" in rendered
    assert "PENALTIES = {'afternoon_shift': {'rate': 0.15}}" in rendered
    assert "# FIELD_EVIDENCE =" in rendered
    assert "# GENERATION_METADATA =" in rendered
