"""Shared logic for step 6.1 calculator Python generation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import pprint
import re
from typing import Any

from src.common.output_naming import award_title_from_award_json_path
from src.common.output_paths import write_text_output


DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_BOOLEAN_FIELDS = {
    "use_contracted_hours_for_pt_overtime": True,
    "pt_employees_entitled_to_contracted_topup": True,
    "ft_employees_entitled_to_contracted_topup": True,
}
GROUPED_CLASS_ATTRIBUTES = (
    "SHIFT_RULES",
    "ORDINARY_TIME_RULES",
    "DAY_TREATMENT_RULES",
    "PAY_RATES",
    "GAP_BETWEEN_SHIFTS_RULE",
    "ORDINARY_HOUR_PENALTIES",
    "TOP_UP_RULES",
)
FIELDS_EXCLUDED_FROM_ANALYSIS = {
    "SHIFT_RULES.default_break_hours",
    "SHIFT_RULES.minimum_paid_shift_hours",
    "ORDINARY_TIME_RULES.long_day",
    "ORDINARY_TIME_RULES.period.basis",
    "ORDINARY_TIME_RULES.period.max_work_days",
    "ORDINARY_TIME_RULES.period.max_work_days_basis",
    "ORDINARY_TIME_RULES.period.part_time_uses_contracted_hours",
    "ORDINARY_TIME_RULES.ordinary_rates.casual_loading",
    "TOP_UP_RULES.part_time",
    "TOP_UP_RULES.full_time",
}
WEEKEND_TREATMENT_OPTIONS = (
    "overtime",
    "penalty",
    "not_applicable",
    "needs_review",
)
WORKER_TYPE_OPTIONS = (
    "day",
    "shift",
)
DAY_NAME_OPTIONS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
PENALTY_TYPE_OPTIONS = (
    "shift_based",
    "time_based",
)
PENALTY_BASIS_OPTIONS = (
    "start",
    "end",
    "duration",
    "time",
)
TIME_CONNECTOR_TOKENS = {
    "to",
    "until",
    "till",
    "through",
    "thru",
    "before",
    "after",
    "from",
}


class CalculatorRulesYamlError(RuntimeError):
    """Raised when step 6.1 cannot produce a valid calculator Python artifact."""


@dataclass(frozen=True)
class CalculatorYamlInputs:
    """Prepared step 6.1 inputs."""

    award_code: str
    creation_json_path: Path
    consequence_json_path: Path
    penalties_json_path: Path
    output_path: Path
    creation_artifact: dict[str, Any]
    consequence_artifact: dict[str, Any]
    penalties_artifact: dict[str, Any]
    award_title: str | None


def evidence_schema() -> dict[str, Any]:
    """Return the strict evidence schema for one questionnaire answer."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {
                "type": "string",
                "enum": [
                    "derived",
                    "not_applicable",
                    "needs_review",
                    "defaulted",
                    "not_found",
                ],
            },
            "source_ruleset_keys": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_rule_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "clause_references": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reasoning_summary": {"type": "string"},
            "special_case_notes": {"type": "string"},
        },
        "required": [
            "status",
            "source_ruleset_keys",
            "source_rule_ids",
            "clause_references",
            "reasoning_summary",
            "special_case_notes",
        ],
    }


def _answer_schema(answer_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": answer_schema,
            **evidence_schema()["properties"],
        },
        "required": [
            "answer",
            *evidence_schema()["required"],
        ],
    }


def _nullable_number_schema() -> dict[str, Any]:
    return {"anyOf": [{"type": "number"}, {"type": "null"}]}


def _nullable_boolean_schema() -> dict[str, Any]:
    return {"anyOf": [{"type": "boolean"}, {"type": "null"}]}


def _nullable_string_schema() -> dict[str, Any]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _nullable_enum_schema(options: tuple[str, ...]) -> dict[str, Any]:
    return {"anyOf": [{"type": "string", "enum": list(options)}, {"type": "null"}]}


def align_questionnaire_to_calculator_contract(
    response_data: dict[str, Any],
) -> dict[str, Any]:
    """Populate neutral values for fields made irrelevant by another answer."""
    aligned_response = deepcopy(response_data)
    questionnaire_answers = aligned_response.get("questionnaire_answers")
    if not isinstance(questionnaire_answers, dict):
        return aligned_response

    core_hours_answers = questionnaire_answers.get("core_hours")
    if isinstance(core_hours_answers, dict):
        day_daily_record = core_hours_answers.get("day_worker_daily_limit_hours")
        shift_daily_record = core_hours_answers.get("shift_worker_daily_limit_hours")
        daily_records = [day_daily_record, shift_daily_record]
        if all(isinstance(record, dict) for record in daily_records):
            daily_explanation = " ".join(
                str(record.get(field_name) or "")
                for record in daily_records
                for field_name in ("reasoning_summary", "special_case_notes")
            ).lower().replace("-", " ")
            has_day_and_night_shift_source = (
                "day shift" in daily_explanation
                and "night shift" in daily_explanation
            )
            has_numeric_worker_values = all(
                isinstance(record.get("answer"), (int, float))
                for record in daily_records
            )
            if has_day_and_night_shift_source and has_numeric_worker_values:
                for record in daily_records:
                    record["status"] = "defaulted"
                day_daily_record["special_case_notes"] = (
                    "Contract-alignment assumption: the day-shift boundary is used "
                    "for the calculator's day-worker category."
                )
                shift_daily_record["special_case_notes"] = (
                    "Contract-alignment assumption: the night-shift boundary is used "
                    "for the calculator's shiftworker category."
                )

    weekend_answers = questionnaire_answers.get("weekend_treatment")
    if isinstance(weekend_answers, dict):
        for day_name in ("saturday", "sunday", "public_holiday"):
            for worker_prefix in ("day", "shift"):
                treatment_name = f"{worker_prefix}_{day_name}_treatment"
                treatment_record = weekend_answers.get(treatment_name)
                if not isinstance(treatment_record, dict):
                    continue
                if treatment_record.get("answer") != "overtime":
                    continue

                loading_names = [
                    f"{worker_prefix}_{day_name}_penalty_loading",
                    f"casual_{worker_prefix}_{day_name}_penalty_loading",
                ]
                for loading_name in loading_names:
                    loading_record = weekend_answers.get(loading_name)
                    if not isinstance(loading_record, dict):
                        continue
                    loading_record["answer"] = 0
                    loading_record["status"] = "not_applicable"
                    loading_record["reasoning_summary"] = (
                        "This worker type is classified as overtime for this day, so "
                        "the calculator does not use an ordinary-hours penalty loading."
                    )
                    loading_record["special_case_notes"] = (
                        "The applicable overtime rate is selected from PAY_RATES."
                    )

    gap_answers = questionnaire_answers.get("gap_between_shifts")
    if isinstance(gap_answers, dict):
        casual_gap_record = gap_answers.get("casual_breach_penalty_multiplier")
        if isinstance(casual_gap_record, dict) and casual_gap_record.get("answer") is None:
            casual_gap_explanation = " ".join(
                str(casual_gap_record.get(field_name) or "")
                for field_name in ("reasoning_summary", "special_case_notes")
            ).lower()
            if "casual" in casual_gap_explanation and "exclud" in casual_gap_explanation:
                casual_gap_record["answer"] = 0
                casual_gap_record["status"] = "not_applicable"
                casual_gap_record["special_case_notes"] = (
                    "The reviewed payment excludes casual employees. The calculator "
                    "contract cannot exclude casuals from an active gap rule, so this "
                    "zero value still requires confirmation of the suppression effect."
                )

    penalty_answers = questionnaire_answers.get("weekday_penalties")
    if isinstance(penalty_answers, dict):
        # Removed from the current questionnaire scope. Drop it when an older
        # saved questionnaire is rebuilt through the current code.
        penalty_answers.pop("casual_ordinary_loading", None)
        for penalty_list_name in ("shift_based_penalties", "time_based_penalties"):
            penalty_record = penalty_answers.get(penalty_list_name)
            if not isinstance(penalty_record, dict):
                continue
            if penalty_record.get("answer") == [] and penalty_record.get("status") == "not_found":
                penalty_record["status"] = "not_applicable"
                penalty_record["special_case_notes"] = (
                    "The reviewed rules produced no live rules that fit this calculator "
                    "penalty shape."
                )

    return aligned_response


def penalty_rule_schema() -> dict[str, Any]:
    """Return one ordinary-hour penalty rule answer shape."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "code_name": {"type": "string"},
            "type": {"type": "string", "enum": list(PENALTY_TYPE_OPTIONS)},
            "basis": {"type": "string", "enum": list(PENALTY_BASIS_OPTIONS)},
            "start_hour": {"type": "number"},
            "end_hour": {"type": "number"},
            "rate": {"type": "number"},
            "casual_rate": _nullable_number_schema(),
            "description": {"type": "string"},
            "applies_to": {
                "type": "array",
                "items": {"type": "string", "enum": list(WORKER_TYPE_OPTIONS)},
            },
            "days": {
                "type": "array",
                "items": {"type": "string", "enum": list(DAY_NAME_OPTIONS)},
            },
        },
        "required": [
            "code_name",
            "type",
            "basis",
            "start_hour",
            "end_hour",
            "rate",
            "casual_rate",
            "description",
            "applies_to",
            "days",
        ],
    }


def special_case_schema() -> dict[str, Any]:
    """Return one simple special-case note structure."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "worker_group": {"type": "string"},
            "threshold_hours": _nullable_number_schema(),
            "notes": {"type": "string"},
        },
        "required": ["worker_group", "threshold_hours", "notes"],
    }


def calculator_rules_response_json_schema() -> dict[str, Any]:
    """Return the strict questionnaire JSON schema expected from step 6.1."""
    core_hours = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "day_worker_daily_limit_hours": _answer_schema(_nullable_number_schema()),
            "shift_worker_daily_limit_hours": _answer_schema(_nullable_number_schema()),
            "day_worker_weekly_limit_hours": _answer_schema(_nullable_number_schema()),
            "shift_worker_weekly_limit_hours": _answer_schema(_nullable_number_schema()),
        },
        "required": [
            "day_worker_daily_limit_hours",
            "shift_worker_daily_limit_hours",
            "day_worker_weekly_limit_hours",
            "shift_worker_weekly_limit_hours",
        ],
    }

    overtime = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "standard_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_standard_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "has_two_tier_overtime": _answer_schema(_nullable_boolean_schema()),
            "extended_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_extended_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "higher_overtime_starts_after_hours": _answer_schema(_nullable_number_schema()),
            "extended_overtime_days": _answer_schema(
                {
                    "type": "array",
                    "items": {"type": "string", "enum": list(DAY_NAME_OPTIONS)},
                }
            ),
            "saturday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_saturday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "sunday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_sunday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "public_holiday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_public_holiday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
        },
        "required": [
            "standard_overtime_multiplier",
            "casual_standard_overtime_multiplier",
            "has_two_tier_overtime",
            "extended_overtime_multiplier",
            "casual_extended_overtime_multiplier",
            "higher_overtime_starts_after_hours",
            "extended_overtime_days",
            "saturday_overtime_multiplier",
            "casual_saturday_overtime_multiplier",
            "sunday_overtime_multiplier",
            "casual_sunday_overtime_multiplier",
            "public_holiday_overtime_multiplier",
            "casual_public_holiday_overtime_multiplier",
        ],
    }

    span = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "day_workers_have_span_overtime": _answer_schema(_nullable_boolean_schema()),
            "live_span_start_hour": _answer_schema(_nullable_number_schema()),
            "live_span_cutoff_hour": _answer_schema(_nullable_number_schema()),
            "ordinary_span_summary": _answer_schema(_nullable_string_schema()),
        },
        "required": [
            "day_workers_have_span_overtime",
            "live_span_start_hour",
            "live_span_cutoff_hour",
            "ordinary_span_summary",
        ],
    }

    weekend_treatment = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "day_saturday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "day_sunday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "shift_saturday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "shift_sunday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "day_saturday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "day_sunday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "shift_saturday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "shift_sunday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_day_saturday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_day_sunday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_shift_saturday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_shift_sunday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "day_public_holiday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "shift_public_holiday_treatment": _answer_schema(
                _nullable_enum_schema(WEEKEND_TREATMENT_OPTIONS)
            ),
            "day_public_holiday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "shift_public_holiday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_day_public_holiday_penalty_loading": _answer_schema(_nullable_number_schema()),
            "casual_shift_public_holiday_penalty_loading": _answer_schema(_nullable_number_schema()),
        },
        "required": [
            "day_saturday_treatment",
            "day_sunday_treatment",
            "shift_saturday_treatment",
            "shift_sunday_treatment",
            "day_saturday_penalty_loading",
            "day_sunday_penalty_loading",
            "shift_saturday_penalty_loading",
            "shift_sunday_penalty_loading",
            "casual_day_saturday_penalty_loading",
            "casual_day_sunday_penalty_loading",
            "casual_shift_saturday_penalty_loading",
            "casual_shift_sunday_penalty_loading",
            "day_public_holiday_treatment",
            "shift_public_holiday_treatment",
            "day_public_holiday_penalty_loading",
            "shift_public_holiday_penalty_loading",
            "casual_day_public_holiday_penalty_loading",
            "casual_shift_public_holiday_penalty_loading",
        ],
    }

    gap_between_shifts = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "minimum_break_required": _answer_schema(_nullable_boolean_schema()),
            "standard_minimum_break_hours": _answer_schema(_nullable_number_schema()),
            "breach_penalty_multiplier": _answer_schema(_nullable_number_schema()),
            "casual_breach_penalty_multiplier": _answer_schema(_nullable_number_schema()),
            "special_case_thresholds": _answer_schema(
                {
                    "type": "array",
                    "items": special_case_schema(),
                }
            ),
        },
        "required": [
            "minimum_break_required",
            "standard_minimum_break_hours",
            "breach_penalty_multiplier",
            "casual_breach_penalty_multiplier",
            "special_case_thresholds",
        ],
    }

    weekday_penalties = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "shift_based_penalties": _answer_schema(
                {"type": "array", "items": penalty_rule_schema()}
            ),
            "time_based_penalties": _answer_schema(
                {"type": "array", "items": penalty_rule_schema()}
            ),
            "other_penalty_notes": _answer_schema(_nullable_string_schema()),
        },
        "required": [
            "shift_based_penalties",
            "time_based_penalties",
            "other_penalty_notes",
        ],
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "questionnaire_answers": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "core_hours": core_hours,
                    "overtime": overtime,
                    "span": span,
                    "weekend_treatment": weekend_treatment,
                    "gap_between_shifts": gap_between_shifts,
                    "weekday_penalties": weekday_penalties,
                },
                "required": [
                    "core_hours",
                    "overtime",
                    "span",
                    "weekend_treatment",
                    "gap_between_shifts",
                    "weekday_penalties",
                ],
            }
        },
        "required": ["questionnaire_answers"],
    }


def summarized_rules(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep only the rule fields needed for calculator derivation."""
    summarized: list[dict[str, Any]] = []

    for raw_rule in artifact.get("rules", []):
        if not isinstance(raw_rule, dict):
            continue

        summarized.append(
            {
                "rule_id": raw_rule.get("rule_id"),
                "section_heading": raw_rule.get("section_heading"),
                "employee_cohort": raw_rule.get("employee_cohort"),
                "work_arrangement": raw_rule.get("work_arrangement"),
                "clause_references": raw_rule.get("clause_references"),
                "rule_markdown": raw_rule.get("rule_markdown"),
                "rule_plain_text": raw_rule.get("rule_plain_text"),
                "other_scope_notes": raw_rule.get("other_scope_notes"),
            }
        )

    return summarized


def default_evidence(reasoning_summary: str, status: str) -> dict[str, Any]:
    """Build one evidence record with empty sources."""
    return {
        "status": status,
        "source_ruleset_keys": [],
        "source_rule_ids": [],
        "clause_references": [],
        "reasoning_summary": reasoning_summary,
        "special_case_notes": "",
    }


def _normalize_evidence_record(
    raw_record: dict[str, Any],
) -> dict[str, Any]:
    source_ruleset_keys = [
        str(value).strip()
        for value in raw_record.get("source_ruleset_keys", [])
        if str(value).strip()
    ]
    source_rule_ids: list[str] = []

    for value in raw_record.get("source_rule_ids", []):
        raw_rule_id = str(value).strip()
        if not raw_rule_id:
            continue

        if raw_rule_id not in source_rule_ids:
            source_rule_ids.append(raw_rule_id)
    clause_references = [
        str(value).strip()
        for value in raw_record.get("clause_references", [])
        if str(value).strip()
    ]
    reasoning_summary = str(raw_record.get("reasoning_summary") or "").strip()
    special_case_notes = str(raw_record.get("special_case_notes") or "").strip()
    status = str(raw_record.get("status") or "").strip() or "needs_review"

    return {
        "status": status,
        "source_ruleset_keys": sorted(set(source_ruleset_keys)),
        "source_rule_ids": source_rule_ids,
        "clause_references": clause_references,
        "reasoning_summary": reasoning_summary or "No reasoning summary provided.",
        "special_case_notes": special_case_notes,
    }


def _get_question_record(
    questionnaire_answers: dict[str, Any],
    section_name: str,
    question_name: str,
) -> dict[str, Any]:
    section = questionnaire_answers.get(section_name)
    if not isinstance(section, dict):
        raise CalculatorRulesYamlError(f"Missing questionnaire section: {section_name}")

    record = section.get(question_name)
    if not isinstance(record, dict):
        raise CalculatorRulesYamlError(
            f"Missing questionnaire answer: {section_name}.{question_name}"
        )

    return record


def _normalize_question_record(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
) -> dict[str, Any]:
    record = _get_question_record(questionnaire_answers, section_name, question_name)
    normalized = _normalize_evidence_record(record)
    normalized["answer"] = record.get("answer")
    return normalized


def _normalize_optional_question_record(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
) -> dict[str, Any]:
    """Read a newly added question while keeping stored draft fixtures reviewable."""
    section = questionnaire_answers.get(section_name)
    if isinstance(section, dict) and isinstance(section.get(question_name), dict):
        return _normalize_question_record(
            questionnaire_answers,
            section_name=section_name,
            question_name=question_name,
        )

    normalized = default_evidence(
        f"The questionnaire did not provide {section_name}.{question_name}.",
        "not_found",
    )
    normalized["answer"] = None
    return normalized


def _merge_status(statuses: list[str], *, default_status: str = "not_found") -> str:
    if not statuses:
        return default_status
    if "needs_review" in statuses:
        return "needs_review"
    if "derived" in statuses:
        return "derived"
    if "defaulted" in statuses:
        return "defaulted"
    return statuses[0]


def _merge_evidence_records(
    records: list[dict[str, Any]],
    *,
    empty_reason: str,
) -> dict[str, Any]:
    usable_records = [record for record in records if isinstance(record, dict)]
    if not usable_records:
        return default_evidence(empty_reason, "not_found")

    source_ruleset_keys: list[str] = []
    source_rule_ids: list[str] = []
    clause_references: list[str] = []
    reasoning_parts: list[str] = []
    special_case_parts: list[str] = []

    for record in usable_records:
        for ruleset_key in record.get("source_ruleset_keys", []):
            if ruleset_key not in source_ruleset_keys:
                source_ruleset_keys.append(ruleset_key)
        for rule_id in record.get("source_rule_ids", []):
            if rule_id not in source_rule_ids:
                source_rule_ids.append(rule_id)
        for clause_reference in record.get("clause_references", []):
            if clause_reference not in clause_references:
                clause_references.append(clause_reference)

        reasoning_summary = str(record.get("reasoning_summary") or "").strip()
        if reasoning_summary and reasoning_summary not in reasoning_parts:
            reasoning_parts.append(reasoning_summary)

        special_case_notes = str(record.get("special_case_notes") or "").strip()
        if special_case_notes and special_case_notes not in special_case_parts:
            special_case_parts.append(special_case_notes)

    return {
        "status": _merge_status(
            [str(record.get("status") or "").strip() for record in usable_records]
        ),
        "source_ruleset_keys": source_ruleset_keys,
        "source_rule_ids": source_rule_ids,
        "clause_references": clause_references,
        "reasoning_summary": " | ".join(reasoning_parts) or empty_reason,
        "special_case_notes": " | ".join(special_case_parts),
    }


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _format_hour_for_identifier(value: int | float) -> str:
    numeric_value = float(value)
    whole_hours = int(numeric_value)

    if numeric_value == whole_hours:
        return str(whole_hours)

    minutes = int(round((numeric_value - whole_hours) * 60))
    return f"{whole_hours}_{minutes:02d}"


def _extract_explicit_hours_from_text(text: str) -> list[float]:
    extracted_hours: list[float] = []
    normalized_text = text.lower().replace("_", " ")

    for match in re.finditer(
        r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b",
        normalized_text,
    ):
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        meridiem = match.group(3)

        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12

        extracted_hours.append(hour + (minute / 60))

    # Do not extract the clock portion a second time when it already has an
    # am/pm suffix. Otherwise "6:30 pm" becomes both 18.5 and 6.5, shifting
    # the apparent end time and causing a false hard validation failure.
    for match in re.finditer(
        r"\b(\d{1,2}):(\d{2})\b(?!\s*(?:am|pm)\b)",
        normalized_text,
    ):
        hour = int(match.group(1))
        minute = int(match.group(2))
        extracted_hours.append(hour + (minute / 60))

    if re.search(r"\bmidnight\b", normalized_text):
        extracted_hours.append(0.0)
    if re.search(r"\bnoon\b", normalized_text):
        extracted_hours.append(12.0)

    return extracted_hours


def _strip_trailing_time_tokens(code_name: str) -> str:
    parts = [part for part in code_name.lower().split("_") if part]
    if not parts:
        return ""

    time_pattern = re.compile(r"^\d{1,2}(?:am|pm)$|^\d{1,2}$")
    trailing_index = len(parts)
    saw_time_token = False

    while trailing_index > 0:
        current_part = parts[trailing_index - 1]
        if current_part in TIME_CONNECTOR_TOKENS or current_part in {"midnight", "noon"}:
            saw_time_token = True
            trailing_index -= 1
            continue
        if time_pattern.match(current_part):
            saw_time_token = True
            trailing_index -= 1
            continue
        break

    if not saw_time_token:
        return "_".join(parts)

    stripped_parts = parts[:trailing_index]
    return "_".join(stripped_parts).strip("_")


def _strip_trailing_rate_tokens(code_name: str) -> str:
    parts = [part for part in code_name.lower().split("_") if part]
    if not parts:
        return ""

    trailing_index = len(parts)

    while trailing_index > 0:
        current_part = parts[trailing_index - 1]

        if current_part in {"allowance", "allowances", "loading", "loadings"}:
            trailing_index -= 1
            continue

        if re.match(r"^\d+(?:pct|percent)$", current_part):
            trailing_index -= 1
            continue

        if current_part in {"pct", "percent"} and trailing_index > 1:
            numeric_index = trailing_index - 1
            while numeric_index > 0 and re.match(r"^\d+$", parts[numeric_index - 1]):
                numeric_index -= 1

            if numeric_index < trailing_index - 1:
                trailing_index = numeric_index
                continue

        break

    stripped_parts = parts[:trailing_index]
    return "_".join(stripped_parts).strip("_")


def _simplified_penalty_code_name(raw_code_name: str) -> str:
    without_times = _strip_trailing_time_tokens(raw_code_name)
    without_rates = _strip_trailing_rate_tokens(without_times)

    if without_rates:
        return without_rates
    if without_times:
        return without_times
    return raw_code_name.lower().strip("_")


def _canonical_penalty_code_name(
    raw_code_name: str,
    *,
    penalty_basis: str,
    start_hour: int | float,
    end_hour: int | float,
) -> str:
    base_name = _simplified_penalty_code_name(raw_code_name) or "penalty_window"
    start_text = _format_hour_for_identifier(start_hour)
    end_text = _format_hour_for_identifier(end_hour)
    return f"{base_name}_{penalty_basis}_{start_text}_to_{end_text}"


def _normalize_midnight_hour(value: int | float) -> float:
    """Treat midnight as the end of day when comparing live rule windows."""
    numeric_value = float(value)
    if numeric_value == 0.0:
        return 24.0
    return numeric_value


def _round_live_penalty_hour(value: int | float) -> int:
    """Round a rule window to the whole-hour precision supported by the calculator."""
    numeric_value = float(value)
    if numeric_value == 24.0:
        return 24
    return int(numeric_value + 0.5)


def _validate_penalty_time_text(
    *,
    description: str,
    start_hour: int | float,
    end_hour: int | float,
) -> str | None:
    explicit_hours = _extract_explicit_hours_from_text(description)
    if len(explicit_hours) < 2:
        return None

    expected_start = _normalize_midnight_hour(start_hour)
    expected_end = _normalize_midnight_hour(end_hour)
    stated_start = _normalize_midnight_hour(explicit_hours[0])
    stated_end = _normalize_midnight_hour(explicit_hours[1])

    rounded_expected_start = _round_live_penalty_hour(expected_start)
    rounded_expected_end = _round_live_penalty_hour(expected_end)
    rounded_stated_start = _round_live_penalty_hour(stated_start)
    rounded_stated_end = _round_live_penalty_hour(stated_end)

    if (
        rounded_stated_start != rounded_expected_start
        or rounded_stated_end != rounded_expected_end
    ):
        return (
            "Step 6.1 produced a weekday penalty whose structured hours do not match its "
            f"description: '{description}' implies {rounded_stated_start} to "
            f"{rounded_stated_end}, but the structured window is "
            f"{rounded_expected_start} to {rounded_expected_end}."
        )

    return None


def _penalty_code_name_has_explicit_times(code_name: str) -> bool:
    normalized_name = code_name.lower().replace("_", " ")
    explicit_hours = _extract_explicit_hours_from_text(normalized_name)
    return len(explicit_hours) >= 2


def _unique_penalty_name(base_name: str, existing_penalties: dict[str, Any]) -> str:
    if base_name not in existing_penalties:
        return base_name

    suffix = 2
    while f"{base_name}_{suffix}" in existing_penalties:
        suffix += 1
    return f"{base_name}_{suffix}"


def _build_live_penalties(
    shift_based_rules: list[dict[str, Any]],
    time_based_rules: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    penalties: dict[str, Any] = {}

    for raw_rule in [*shift_based_rules, *time_based_rules]:
        if not isinstance(raw_rule, dict):
            continue

        code_name = str(raw_rule.get("code_name") or "").strip()
        if not code_name:
            continue

        start_hour = raw_rule.get("start_hour")
        end_hour = raw_rule.get("end_hour")
        penalty_type = str(raw_rule.get("type") or "").strip()
        penalty_basis = str(raw_rule.get("basis") or "").strip()

        if penalty_type not in PENALTY_TYPE_OPTIONS:
            continue
        if penalty_basis not in PENALTY_BASIS_OPTIONS:
            continue
        if not isinstance(start_hour, (int, float)):
            continue
        if not isinstance(end_hour, (int, float)):
            continue

        start_hour = _round_live_penalty_hour(_normalize_midnight_hour(start_hour))
        end_hour = _round_live_penalty_hour(_normalize_midnight_hour(end_hour))

        applies_to = [
            worker_type
            for worker_type in raw_rule.get("applies_to", [])
            if worker_type in WORKER_TYPE_OPTIONS
        ]
        description = str(raw_rule.get("description") or "").strip()
        lower_description = description.lower()
        lower_code_name = code_name.lower()

        penalty_time_warning = _validate_penalty_time_text(
            description=description,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        if penalty_time_warning is not None:
            validation_warnings.append(penalty_time_warning)

        # Named weekend and public-holiday treatments belong in
        # DAY_TREATMENT_RULES. Ordinary-hour penalties may still provide their
        # own explicit day list when one rule operates across several days.
        calendar_specific_terms = (
            "saturday",
            "sunday",
            "weekend",
            "public holiday",
            "public_holiday",
        )
        if any(term in lower_code_name or term in lower_description for term in calendar_specific_terms):
            continue

        normalized_code_name = _simplified_penalty_code_name(code_name) or code_name
        if normalized_code_name in penalties and _penalty_code_name_has_explicit_times(code_name):
            normalized_code_name = _canonical_penalty_code_name(
                code_name,
                penalty_basis=penalty_basis,
                start_hour=start_hour,
                end_hour=end_hour,
            )

        normalized_code_name = _unique_penalty_name(normalized_code_name, penalties)

        penalties[normalized_code_name] = {
            "type": penalty_type,
            "basis": penalty_basis,
            "start": start_hour,
            "end": end_hour,
            "rate": raw_rule.get("rate"),
            "casual_rate": raw_rule.get("casual_rate"),
            "description": description,
            "applies_to": applies_to,
            "days": [
                day_name
                for day_name in raw_rule.get("days", [])
                if day_name in DAY_NAME_OPTIONS
            ],
        }

    return penalties


def validate_questionnaire_values(calculator_rules: dict[str, Any]) -> None:
    """Validate the extracted questionnaire values before grouping them."""
    if calculator_rules.get("apply_span_overtime") is True:
        if not isinstance(calculator_rules.get("span_overtime_hour"), (int, float)):
            raise CalculatorRulesYamlError(
                "Step 6.1 produced APPLY_SPAN_OVERTIME = True without a numeric SPAN_OVERTIME_HOUR."
            )

    for field_name in ("gap_penalty_hours", "gap_penalty_rate"):
        value = calculator_rules.get(field_name)
        if value is not None and not isinstance(value, (int, float)):
            raise CalculatorRulesYamlError(
                f"Step 6.1 produced a non-numeric value for {field_name}."
            )

    extended_overtime_days = calculator_rules.get("extended_overtime_days")
    if not isinstance(extended_overtime_days, list):
        raise CalculatorRulesYamlError(
            "Step 6.1 extended_overtime_days must be a list."
        )
    for day_name in extended_overtime_days:
        if day_name not in DAY_NAME_OPTIONS:
            raise CalculatorRulesYamlError(
                f"Step 6.1 produced an unsupported extended overtime day: {day_name!r}."
            )

    penalties = calculator_rules.get("penalties")
    if not isinstance(penalties, dict):
        raise CalculatorRulesYamlError("Step 6.1 penalties must be a mapping.")

    for penalty_name, penalty_rule in penalties.items():
        if not isinstance(penalty_rule, dict):
            raise CalculatorRulesYamlError(
                f"Penalty '{penalty_name}' must be a mapping."
            )
        if penalty_rule.get("type") not in PENALTY_TYPE_OPTIONS:
            raise CalculatorRulesYamlError(
                f"Penalty '{penalty_name}' has an unsupported type."
            )
        if not isinstance(penalty_rule.get("start"), (int, float)):
            raise CalculatorRulesYamlError(
                f"Penalty '{penalty_name}' must have a numeric start."
            )
        if not isinstance(penalty_rule.get("end"), (int, float)):
            raise CalculatorRulesYamlError(
                f"Penalty '{penalty_name}' must have a numeric end."
            )

def normalize_response_data(
    response_data: dict[str, Any],
    *,
    award_code: str,
) -> dict[str, Any]:
    """Map questionnaire answers into the persisted calculator structure."""
    questionnaire_answers = response_data.get("questionnaire_answers")
    if not isinstance(questionnaire_answers, dict):
        raise CalculatorRulesYamlError(
            "Step 6.1 model output is missing questionnaire_answers."
        )

    question_records = {
        "day_daily_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="day_worker_daily_limit_hours",
        ),
        "shift_daily_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="shift_worker_daily_limit_hours",
        ),
        "day_weekly_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="day_worker_weekly_limit_hours",
        ),
        "shift_weekly_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="shift_worker_weekly_limit_hours",
        ),
        "standard_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="standard_overtime_multiplier",
        ),
        "casual_standard_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_standard_overtime_multiplier",
        ),
        "has_two_tier_overtime": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="has_two_tier_overtime",
        ),
        "extended_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="extended_overtime_multiplier",
        ),
        "casual_extended_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_extended_overtime_multiplier",
        ),
        "higher_overtime_starts_after_hours": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="higher_overtime_starts_after_hours",
        ),
        "extended_overtime_days": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="extended_overtime_days",
        ),
        "saturday_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="saturday_overtime_multiplier",
        ),
        "casual_saturday_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_saturday_overtime_multiplier",
        ),
        "sunday_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="sunday_overtime_multiplier",
        ),
        "casual_sunday_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_sunday_overtime_multiplier",
        ),
        "public_holiday_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="public_holiday_overtime_multiplier",
        ),
        "casual_public_holiday_overtime_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_public_holiday_overtime_multiplier",
        ),
        "day_workers_have_span_overtime": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="day_workers_have_span_overtime",
        ),
        "live_span_start_hour": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="live_span_start_hour",
        ),
        "live_span_cutoff_hour": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="live_span_cutoff_hour",
        ),
        "ordinary_span_summary": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="ordinary_span_summary",
        ),
        "day_saturday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_saturday_treatment",
        ),
        "day_sunday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_sunday_treatment",
        ),
        "shift_saturday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_saturday_treatment",
        ),
        "shift_sunday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_sunday_treatment",
        ),
        "day_saturday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_saturday_penalty_loading",
        ),
        "day_sunday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_sunday_penalty_loading",
        ),
        "shift_saturday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_saturday_penalty_loading",
        ),
        "shift_sunday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_sunday_penalty_loading",
        ),
        "casual_day_saturday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_day_saturday_penalty_loading",
        ),
        "casual_day_sunday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_day_sunday_penalty_loading",
        ),
        "casual_shift_saturday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_shift_saturday_penalty_loading",
        ),
        "casual_shift_sunday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_shift_sunday_penalty_loading",
        ),
        "day_public_holiday_treatment": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_public_holiday_treatment",
        ),
        "shift_public_holiday_treatment": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_public_holiday_treatment",
        ),
        "day_public_holiday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_public_holiday_penalty_loading",
        ),
        "shift_public_holiday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_public_holiday_penalty_loading",
        ),
        "casual_day_public_holiday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_day_public_holiday_penalty_loading",
        ),
        "casual_shift_public_holiday_penalty_loading": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="casual_shift_public_holiday_penalty_loading",
        ),
        "minimum_break_required": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="minimum_break_required",
        ),
        "standard_minimum_break_hours": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="standard_minimum_break_hours",
        ),
        "breach_penalty_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="breach_penalty_multiplier",
        ),
        "casual_breach_penalty_multiplier": _normalize_optional_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="casual_breach_penalty_multiplier",
        ),
        "special_case_thresholds": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="special_case_thresholds",
        ),
        "shift_based_penalties": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="shift_based_penalties",
        ),
        "time_based_penalties": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="time_based_penalties",
        ),
        "other_penalty_notes": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="other_penalty_notes",
        ),
    }

    validation_warnings: list[str] = []

    has_two_tier = question_records["has_two_tier_overtime"]["answer"]
    minimum_break_required = question_records["minimum_break_required"]["answer"]

    casual_gap_record = question_records["casual_breach_penalty_multiplier"]
    casual_gap_is_not_applicable = (
        casual_gap_record["status"] == "not_applicable"
    )
    if minimum_break_required is True and casual_gap_is_not_applicable:
        validation_warnings.append(
            "The reviewed rules exclude casual employees from the payment for an "
            "insufficient break between shifts. The calculator cannot switch this "
            "rule off for casual employees only. It therefore uses a zero casual "
            "loading, but applying the rule may still remove other casual loadings. "
            "Review this treatment before approval."
        )

    shift_based_penalties_answer = question_records["shift_based_penalties"]["answer"] or []
    time_based_penalties_answer = question_records["time_based_penalties"]["answer"] or []

    span_overtime_is_supported = (
        question_records["day_workers_have_span_overtime"]["answer"] is True
    )
    span_overtime_cutoff = question_records["live_span_cutoff_hour"]["answer"]
    has_numeric_span_overtime_cutoff = isinstance(span_overtime_cutoff, (int, float))

    if span_overtime_is_supported and not has_numeric_span_overtime_cutoff:
        validation_warnings.append(
            "Span overtime is supported by the reviewed rules, but no single numeric "
            "span cutoff is available. The live span-overtime calculation has been "
            "disabled and requires review before it can be enabled."
        )

    normalized_rules: dict[str, Any] = {
        "ordinary_hours_limit_daily": question_records["shift_daily_limit"]["answer"],
        "ordinary_hours_limit_weekly": question_records["shift_weekly_limit"]["answer"],
        "day_worker_ordinary_hours_daily": question_records["day_daily_limit"]["answer"],
        "day_worker_ordinary_hours_weekly": question_records["day_weekly_limit"]["answer"],
        "standard_overtime_rate": question_records["standard_overtime_multiplier"]["answer"],
        "casual_standard_overtime_rate": question_records[
            "casual_standard_overtime_multiplier"
        ]["answer"],
        "extended_overtime_rate": (
            question_records["extended_overtime_multiplier"]["answer"]
            if has_two_tier is True
            else None
        ),
        "casual_extended_overtime_rate": (
            question_records["casual_extended_overtime_multiplier"]["answer"]
            if has_two_tier is True
            else None
        ),
        "sunday_overtime_rate": question_records["sunday_overtime_multiplier"]["answer"],
        "casual_sunday_overtime_rate": question_records[
            "casual_sunday_overtime_multiplier"
        ]["answer"],
        "saturday_overtime_rate": question_records["saturday_overtime_multiplier"]["answer"],
        "casual_saturday_overtime_rate": question_records[
            "casual_saturday_overtime_multiplier"
        ]["answer"],
        "public_holiday_overtime_rate": question_records[
            "public_holiday_overtime_multiplier"
        ]["answer"],
        "casual_public_holiday_overtime_rate": question_records[
            "casual_public_holiday_overtime_multiplier"
        ]["answer"],
        "apply_span_overtime": (
            span_overtime_is_supported and has_numeric_span_overtime_cutoff
        ),
        "span_overtime_hour": (
            span_overtime_cutoff
            if span_overtime_is_supported and has_numeric_span_overtime_cutoff
            else None
        ),
        "span_overtime_start_hour": (
            question_records["live_span_start_hour"]["answer"]
            if span_overtime_is_supported
            else None
        ),
        "gap_penalty_hours": (
            question_records["standard_minimum_break_hours"]["answer"]
            if minimum_break_required is True
            else None
        ),
        "gap_penalty_rate": (
            question_records["breach_penalty_multiplier"]["answer"]
            if minimum_break_required is True
            else None
        ),
        "casual_gap_penalty_rate": (
            question_records["casual_breach_penalty_multiplier"]["answer"]
            if minimum_break_required is True
            else None
        ),
        "penalties": _build_live_penalties(
            shift_based_penalties_answer,
            time_based_penalties_answer,
            validation_warnings,
        ),
        "two_tier_overtime": has_two_tier,
        "two_tier_overtime_threshold": (
            question_records["higher_overtime_starts_after_hours"]["answer"]
            if has_two_tier is True
            else None
        ),
        "extended_overtime_days": (
            question_records["extended_overtime_days"]["answer"]
            if has_two_tier is True
            else []
        ),
        "day_treatment_inputs": {
            "Saturday": {
                "day": {
                    "treatment": question_records["day_saturday_treatment"]["answer"],
                    "loading": question_records["day_saturday_penalty_loading"]["answer"],
                    "casual_loading": question_records[
                        "casual_day_saturday_penalty_loading"
                    ]["answer"],
                },
                "shift": {
                    "treatment": question_records["shift_saturday_treatment"]["answer"],
                    "loading": question_records["shift_saturday_penalty_loading"]["answer"],
                    "casual_loading": question_records[
                        "casual_shift_saturday_penalty_loading"
                    ]["answer"],
                },
            },
            "Sunday": {
                "day": {
                    "treatment": question_records["day_sunday_treatment"]["answer"],
                    "loading": question_records["day_sunday_penalty_loading"]["answer"],
                    "casual_loading": question_records[
                        "casual_day_sunday_penalty_loading"
                    ]["answer"],
                },
                "shift": {
                    "treatment": question_records["shift_sunday_treatment"]["answer"],
                    "loading": question_records["shift_sunday_penalty_loading"]["answer"],
                    "casual_loading": question_records[
                        "casual_shift_sunday_penalty_loading"
                    ]["answer"],
                },
            },
            "public_holiday": {
                "day": {
                    "treatment": question_records["day_public_holiday_treatment"]["answer"],
                    "loading": question_records[
                        "day_public_holiday_penalty_loading"
                    ]["answer"],
                    "casual_loading": question_records[
                        "casual_day_public_holiday_penalty_loading"
                    ]["answer"],
                },
                "shift": {
                    "treatment": question_records["shift_public_holiday_treatment"]["answer"],
                    "loading": question_records[
                        "shift_public_holiday_penalty_loading"
                    ]["answer"],
                    "casual_loading": question_records[
                        "casual_shift_public_holiday_penalty_loading"
                    ]["answer"],
                },
            },
        },
    }

    validate_questionnaire_values(normalized_rules)

    normalized_evidence = {
        "ordinary_hours_limit_daily": _merge_evidence_records(
            [question_records["shift_daily_limit"]],
            empty_reason="No evidence available for shift-worker daily ordinary-hours limit.",
        ),
        "ordinary_hours_limit_weekly": _merge_evidence_records(
            [question_records["shift_weekly_limit"]],
            empty_reason="No evidence available for shift-worker weekly ordinary-hours limit.",
        ),
        "day_worker_ordinary_hours_daily": _merge_evidence_records(
            [question_records["day_daily_limit"]],
            empty_reason="No evidence available for day-worker daily ordinary-hours limit.",
        ),
        "day_worker_ordinary_hours_weekly": _merge_evidence_records(
            [question_records["day_weekly_limit"]],
            empty_reason="No evidence available for day-worker weekly ordinary-hours limit.",
        ),
        "standard_overtime_rate": _merge_evidence_records(
            [question_records["standard_overtime_multiplier"]],
            empty_reason="No evidence available for standard overtime multiplier.",
        ),
        "casual_standard_overtime_rate": _merge_evidence_records(
            [question_records["casual_standard_overtime_multiplier"]],
            empty_reason="No evidence available for casual standard overtime multiplier.",
        ),
        "extended_overtime_rate": _merge_evidence_records(
            [
                question_records["has_two_tier_overtime"],
                question_records["extended_overtime_multiplier"],
            ],
            empty_reason="No evidence available for extended overtime multiplier.",
        ),
        "casual_extended_overtime_rate": _merge_evidence_records(
            [
                question_records["has_two_tier_overtime"],
                question_records["casual_extended_overtime_multiplier"],
            ],
            empty_reason="No evidence available for casual extended overtime multiplier.",
        ),
        "sunday_overtime_rate": _merge_evidence_records(
            [question_records["sunday_overtime_multiplier"]],
            empty_reason="No evidence available for Sunday overtime multiplier.",
        ),
        "casual_sunday_overtime_rate": _merge_evidence_records(
            [question_records["casual_sunday_overtime_multiplier"]],
            empty_reason="No evidence available for casual Sunday overtime multiplier.",
        ),
        "saturday_overtime_rate": _merge_evidence_records(
            [question_records["saturday_overtime_multiplier"]],
            empty_reason="No evidence available for Saturday overtime multiplier.",
        ),
        "casual_saturday_overtime_rate": _merge_evidence_records(
            [question_records["casual_saturday_overtime_multiplier"]],
            empty_reason="No evidence available for casual Saturday overtime multiplier.",
        ),
        "public_holiday_overtime_rate": _merge_evidence_records(
            [question_records["public_holiday_overtime_multiplier"]],
            empty_reason="No evidence available for public-holiday overtime multiplier.",
        ),
        "casual_public_holiday_overtime_rate": _merge_evidence_records(
            [question_records["casual_public_holiday_overtime_multiplier"]],
            empty_reason="No evidence available for casual public-holiday overtime multiplier.",
        ),
        "apply_span_overtime": _merge_evidence_records(
            [
                question_records["day_workers_have_span_overtime"],
                question_records["ordinary_span_summary"],
            ],
            empty_reason="No evidence available for span overtime.",
        ),
        "span_overtime_hour": _merge_evidence_records(
            [
                question_records["day_workers_have_span_overtime"],
                question_records["live_span_cutoff_hour"],
                question_records["ordinary_span_summary"],
            ],
            empty_reason="No evidence available for span overtime cutoff hour.",
        ),
        "span_overtime_start_hour": _merge_evidence_records(
            [
                question_records["day_workers_have_span_overtime"],
                question_records["live_span_start_hour"],
                question_records["ordinary_span_summary"],
            ],
            empty_reason="No evidence available for span overtime start hour.",
        ),
        "gap_penalty_hours": _merge_evidence_records(
            [
                question_records["minimum_break_required"],
                question_records["standard_minimum_break_hours"],
                question_records["special_case_thresholds"],
            ],
            empty_reason="No evidence available for gap-between-shifts threshold.",
        ),
        "gap_penalty_rate": _merge_evidence_records(
            [
                question_records["minimum_break_required"],
                question_records["breach_penalty_multiplier"],
                question_records["special_case_thresholds"],
            ],
            empty_reason="No evidence available for gap-between-shifts penalty multiplier.",
        ),
        "casual_gap_penalty_rate": _merge_evidence_records(
            [question_records["casual_breach_penalty_multiplier"]],
            empty_reason="No evidence available for casual gap-between-shifts loading.",
        ),
        "penalties": _merge_evidence_records(
            [
                question_records["shift_based_penalties"],
                question_records["time_based_penalties"],
                question_records["other_penalty_notes"],
            ],
            empty_reason="No evidence available for weekday penalties.",
        ),
        "day_treatment_rules": _merge_evidence_records(
            [
                question_records["day_saturday_treatment"],
                question_records["day_sunday_treatment"],
                question_records["shift_saturday_treatment"],
                question_records["shift_sunday_treatment"],
                question_records["day_saturday_penalty_loading"],
                question_records["day_sunday_penalty_loading"],
                question_records["shift_saturday_penalty_loading"],
                question_records["shift_sunday_penalty_loading"],
                question_records["casual_day_saturday_penalty_loading"],
                question_records["casual_day_sunday_penalty_loading"],
                question_records["casual_shift_saturday_penalty_loading"],
                question_records["casual_shift_sunday_penalty_loading"],
                question_records["day_public_holiday_treatment"],
                question_records["shift_public_holiday_treatment"],
                question_records["day_public_holiday_penalty_loading"],
                question_records["shift_public_holiday_penalty_loading"],
                question_records["casual_day_public_holiday_penalty_loading"],
                question_records["casual_shift_public_holiday_penalty_loading"],
            ],
            empty_reason="No evidence available for weekend rules.",
        ),
        "two_tier_overtime": _merge_evidence_records(
            [question_records["has_two_tier_overtime"]],
            empty_reason="No evidence available for two-tier overtime.",
        ),
        "two_tier_overtime_threshold": _merge_evidence_records(
            [
                question_records["has_two_tier_overtime"],
                question_records["higher_overtime_starts_after_hours"],
            ],
            empty_reason="No evidence available for the two-tier overtime threshold.",
        ),
        "extended_overtime_days": _merge_evidence_records(
            [
                question_records["has_two_tier_overtime"],
                question_records["extended_overtime_days"],
            ],
            empty_reason="No evidence available for extended overtime day selection.",
        ),
    }

    for field_name, default_value in DEFAULT_BOOLEAN_FIELDS.items():
        normalized_rules[field_name] = default_value
        normalized_evidence[field_name] = default_evidence(
            "Defaulted to True because the source rulesets do not answer this field.",
            "defaulted",
        )

    grouped_rules, grouped_evidence, missing_fields = build_grouped_calculator_rules(
        normalized_rules,
        normalized_evidence,
    )

    if missing_fields:
        validation_warnings.append(
            f"The following {len(missing_fields)} calculator rule(s) were not fully "
            "supplied by the analysis and were generated using assumptions or "
            "defaults. Review each listed rule before approval."
        )

    return {
        "schema_version": "calculator-rules-python-v2",
        "award_code": award_code,
        "calculator_rules": grouped_rules,
        "field_evidence": grouped_evidence,
        "missing_from_analysis": missing_fields,
        "validation_warnings": validation_warnings,
    }


def _day_treatment_rule(
    *,
    treatment: Any,
    ordinary_loading: Any,
    casual_loading: Any,
    overtime_rate_key: str,
) -> dict[str, Any]:
    """Translate one questionnaire weekend answer to the grouped contract."""
    is_overtime = treatment == "overtime"
    loading = ordinary_loading if treatment == "penalty" else 0

    if is_overtime:
        # DAY_TREATMENT casual_rate is an ordinary-hours loading. Overtime
        # casual rates come from PAY_RATES and must not be duplicated here.
        casual_rate = 0
    elif isinstance(casual_loading, (int, float)):
        casual_rate = casual_loading
    elif isinstance(loading, (int, float)):
        casual_rate = loading
    else:
        casual_rate = 0

    return {
        "base_classification": "overtime" if is_overtime else "ordinary",
        "ordinary_loading": loading if isinstance(loading, (int, float)) else 0,
        "casual_rate": casual_rate,
        "overtime_rate_key": overtime_rate_key,
    }


def _grouped_penalties(
    penalties: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Add the fields required by the grouped ordinary-penalties contract."""
    grouped_penalties: dict[str, Any] = {}
    missing_fields: list[dict[str, Any]] = []
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for penalty_name, penalty in penalties.items():
        penalty_rate = penalty.get("rate")
        penalty_type = penalty.get("type")
        grouped_penalty = {
            "type": penalty_type,
            "basis": "time" if penalty_type == "time_based" else penalty.get("basis"),
            "start": penalty.get("start"),
            "end": penalty.get("end"),
            "rate": penalty_rate,
            "casual_rate": (
                penalty.get("casual_rate")
                if isinstance(penalty.get("casual_rate"), (int, float))
                else penalty_rate
            ),
            "description": penalty.get("description"),
            "applies_to": penalty.get("applies_to"),
            "days": penalty.get("days") or weekdays.copy(),
        }
        grouped_penalties[penalty_name] = grouped_penalty

        if not penalty.get("days"):
            missing_fields.append(
                {
                    "field": f"ORDINARY_HOUR_PENALTIES.{penalty_name}.days",
                    "default_value": weekdays,
                    "reason": "No calendar-day scope was derived for this penalty.",
                }
            )

    return grouped_penalties, missing_fields


def build_grouped_calculator_rules(
    values: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Build the seven grouped calculator attributes required by the live contract."""
    span_overtime: dict[str, Any] = {}
    if values["apply_span_overtime"]:
        span_overtime = {
            "day": {
                "default": {
                    "start": values["span_overtime_start_hour"],
                    "end": values["span_overtime_hour"],
                    "enabled": True,
                }
            }
        }

    day_treatment_rules: dict[str, Any] = {}
    for day_name in ("Saturday", "Sunday", "public_holiday"):
        if day_name == "public_holiday":
            public_holiday_inputs = values["day_treatment_inputs"][day_name]
            has_public_holiday_treatment = any(
                public_holiday_inputs[worker_type]["treatment"]
                in {"overtime", "penalty"}
                for worker_type in WORKER_TYPE_OPTIONS
            )
            if not has_public_holiday_treatment:
                continue
        day_treatment_rules[day_name] = {}
        for worker_type in WORKER_TYPE_OPTIONS:
            treatment_input = values["day_treatment_inputs"][day_name][worker_type]
            day_treatment_rules[day_name][worker_type] = _day_treatment_rule(
                treatment=treatment_input["treatment"],
                ordinary_loading=treatment_input["loading"],
                casual_loading=treatment_input["casual_loading"],
                overtime_rate_key=day_name.lower(),
            )

    ordinary_hour_penalties, penalty_missing_fields = _grouped_penalties(
        values["penalties"]
    )

    grouped_rules = {
        "SHIFT_RULES": {
            "default_break_hours": 0.5,
            "minimum_paid_shift_hours": {},
        },
        "ORDINARY_TIME_RULES": {
            "span_overtime": span_overtime,
            "daily": {
                "variation": "worker_type",
                "day": values["day_worker_ordinary_hours_daily"],
                "shift": values["ordinary_hours_limit_daily"],
            },
            "long_day": {
                "uses_per_week": 0,
                "ordinary_limit_hours": None,
            },
            "period": {
                "variation": "worker_type",
                "day": values["day_worker_ordinary_hours_weekly"],
                "shift": values["ordinary_hours_limit_weekly"],
                "basis": "weekly",
                "max_work_days": None,
                "max_work_days_basis": "weekly",
                "part_time_uses_contracted_hours": values[
                    "use_contracted_hours_for_pt_overtime"
                ],
            },
            "ordinary_rates": {
                # Ordinary casual loading is deliberately outside the LLM analysis.
                # The required calculator field stays explicit and is flagged below.
                "casual_loading": 0
            },
        },
        "DAY_TREATMENT_RULES": day_treatment_rules,
        "PAY_RATES": {
            "overtime": {
                "weekday": {
                    "multiplier": values["standard_overtime_rate"],
                    "casual": _first_non_null(
                        values["casual_standard_overtime_rate"],
                        values["standard_overtime_rate"],
                    ),
                },
                "saturday": {
                    "multiplier": values["saturday_overtime_rate"],
                    "casual": _first_non_null(
                        values["casual_saturday_overtime_rate"],
                        values["saturday_overtime_rate"],
                    ),
                },
                "sunday": {
                    "multiplier": values["sunday_overtime_rate"],
                    "casual": _first_non_null(
                        values["casual_sunday_overtime_rate"],
                        values["sunday_overtime_rate"],
                    ),
                },
                "public_holiday": {
                    "multiplier": values["public_holiday_overtime_rate"],
                    "casual": values["casual_public_holiday_overtime_rate"],
                },
                "extended": {
                    "multiplier": values["extended_overtime_rate"],
                    "casual": _first_non_null(
                        values["casual_extended_overtime_rate"],
                        values["extended_overtime_rate"],
                    ),
                },
                "two_tier": {
                    "enabled": values["two_tier_overtime"] is True,
                    "threshold": values["two_tier_overtime_threshold"] or 0,
                    "days": values["extended_overtime_days"],
                },
            }
        },
        "GAP_BETWEEN_SHIFTS_RULE": {},
        "ORDINARY_HOUR_PENALTIES": ordinary_hour_penalties,
        "TOP_UP_RULES": {
            "part_time": values["pt_employees_entitled_to_contracted_topup"],
            "full_time": values["ft_employees_entitled_to_contracted_topup"],
        },
    }

    if values["gap_penalty_hours"]:
        grouped_rules["GAP_BETWEEN_SHIFTS_RULE"] = {
            "minimum_hours": values["gap_penalty_hours"],
            "loading": values["gap_penalty_rate"],
            "casual_rate": _first_non_null(
                values["casual_gap_penalty_rate"],
                values["gap_penalty_rate"],
            ),
        }

    grouped_evidence = {
        "SHIFT_RULES": {
            "default_break_hours": default_evidence(
                "Default from the calculator contract; not included in the current analysis.",
                "defaulted",
            ),
            "minimum_paid_shift_hours": default_evidence(
                "Disabled because minimum engagement is not included in the current analysis.",
                "defaulted",
            ),
        },
        "ORDINARY_TIME_RULES": {
            "span_overtime": evidence["span_overtime_hour"],
            "span_overtime.start": evidence["span_overtime_start_hour"],
            "daily.day": evidence["day_worker_ordinary_hours_daily"],
            "daily.shift": evidence["ordinary_hours_limit_daily"],
            "long_day": default_evidence(
                "Disabled because long-day exceptions are not included in the current analysis.",
                "defaulted",
            ),
            "period.day": evidence["day_worker_ordinary_hours_weekly"],
            "period.shift": evidence["ordinary_hours_limit_weekly"],
            "period.part_time_uses_contracted_hours": evidence[
                "use_contracted_hours_for_pt_overtime"
            ],
            "ordinary_rates.casual_loading": default_evidence(
                "Ordinary casual loading is outside the overtime-and-penalties analysis scope.",
                "not_found",
            ),
        },
        "DAY_TREATMENT_RULES": evidence["day_treatment_rules"],
        "PAY_RATES": {
            "overtime.weekday": evidence["standard_overtime_rate"],
            "overtime.weekday.casual": evidence["casual_standard_overtime_rate"],
            "overtime.saturday": evidence["saturday_overtime_rate"],
            "overtime.saturday.casual": evidence["casual_saturday_overtime_rate"],
            "overtime.sunday": evidence["sunday_overtime_rate"],
            "overtime.sunday.casual": evidence["casual_sunday_overtime_rate"],
            "overtime.public_holiday": evidence["public_holiday_overtime_rate"],
            "overtime.public_holiday.casual": evidence[
                "casual_public_holiday_overtime_rate"
            ],
            "overtime.extended": evidence["extended_overtime_rate"],
            "overtime.extended.casual": evidence["casual_extended_overtime_rate"],
            "overtime.two_tier": evidence["two_tier_overtime"],
        },
        "GAP_BETWEEN_SHIFTS_RULE": _merge_evidence_records(
            [evidence["gap_penalty_hours"], evidence["casual_gap_penalty_rate"]],
            empty_reason="No evidence available for the gap-between-shifts rule.",
        ),
        "ORDINARY_HOUR_PENALTIES": evidence["penalties"],
        "TOP_UP_RULES": {
            "part_time": evidence["pt_employees_entitled_to_contracted_topup"],
            "full_time": evidence["ft_employees_entitled_to_contracted_topup"],
        },
    }

    missing_fields = [
        {
            "field": "SHIFT_RULES.default_break_hours",
            "default_value": 0.5,
            "reason": "Not included in the current analysis.",
        },
        {
            "field": "SHIFT_RULES.minimum_paid_shift_hours",
            "default_value": {},
            "reason": "Minimum engagement is not included in the current analysis.",
        },
        {
            "field": "ORDINARY_TIME_RULES.long_day",
            "default_value": {"uses_per_week": 0, "ordinary_limit_hours": None},
            "reason": "Long-day exceptions are not included in the current analysis.",
        },
        {
            "field": "ORDINARY_TIME_RULES.period.basis",
            "default_value": "weekly",
            "reason": "Period basis is not included in the current analysis.",
        },
        {
            "field": "ORDINARY_TIME_RULES.period.max_work_days",
            "default_value": None,
            "reason": "Maximum worked days are not included in the current analysis.",
        },
        {
            "field": "ORDINARY_TIME_RULES.period.max_work_days_basis",
            "default_value": "weekly",
            "reason": "Maximum worked-days basis is not included in the current analysis.",
        },
        {
            "field": "ORDINARY_TIME_RULES.period.part_time_uses_contracted_hours",
            "default_value": values["use_contracted_hours_for_pt_overtime"],
            "reason": "Part-time contracted-hours treatment is not included in the current analysis.",
        },
        {
            "field": "TOP_UP_RULES.part_time",
            "default_value": values["pt_employees_entitled_to_contracted_topup"],
            "reason": "Part-time top-up entitlement is not included in the current analysis.",
        },
        {
            "field": "TOP_UP_RULES.full_time",
            "default_value": values["ft_employees_entitled_to_contracted_topup"],
            "reason": "Full-time top-up entitlement is not included in the current analysis.",
        },
        *penalty_missing_fields,
    ]

    analysed_fields = [
        (
            "ORDINARY_TIME_RULES.daily.day",
            grouped_rules["ORDINARY_TIME_RULES"]["daily"]["day"],
            evidence["day_worker_ordinary_hours_daily"],
        ),
        (
            "ORDINARY_TIME_RULES.span_overtime.day.default.start",
            values["span_overtime_start_hour"],
            evidence["span_overtime_start_hour"],
        ),
        (
            "ORDINARY_TIME_RULES.daily.shift",
            grouped_rules["ORDINARY_TIME_RULES"]["daily"]["shift"],
            evidence["ordinary_hours_limit_daily"],
        ),
        (
            "ORDINARY_TIME_RULES.period.day",
            grouped_rules["ORDINARY_TIME_RULES"]["period"]["day"],
            evidence["day_worker_ordinary_hours_weekly"],
        ),
        (
            "ORDINARY_TIME_RULES.period.shift",
            grouped_rules["ORDINARY_TIME_RULES"]["period"]["shift"],
            evidence["ordinary_hours_limit_weekly"],
        ),
        (
            "PAY_RATES.overtime.weekday.multiplier",
            grouped_rules["PAY_RATES"]["overtime"]["weekday"]["multiplier"],
            evidence["standard_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.weekday.casual",
            grouped_rules["PAY_RATES"]["overtime"]["weekday"]["casual"],
            evidence["casual_standard_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.saturday.multiplier",
            grouped_rules["PAY_RATES"]["overtime"]["saturday"]["multiplier"],
            evidence["saturday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.saturday.casual",
            grouped_rules["PAY_RATES"]["overtime"]["saturday"]["casual"],
            evidence["casual_saturday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.sunday.multiplier",
            grouped_rules["PAY_RATES"]["overtime"]["sunday"]["multiplier"],
            evidence["sunday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.sunday.casual",
            grouped_rules["PAY_RATES"]["overtime"]["sunday"]["casual"],
            evidence["casual_sunday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.public_holiday.multiplier",
            grouped_rules["PAY_RATES"]["overtime"]["public_holiday"]["multiplier"],
            evidence["public_holiday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.public_holiday.casual",
            grouped_rules["PAY_RATES"]["overtime"]["public_holiday"]["casual"],
            evidence["casual_public_holiday_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.extended.multiplier",
            grouped_rules["PAY_RATES"]["overtime"]["extended"]["multiplier"],
            evidence["extended_overtime_rate"],
        ),
        (
            "PAY_RATES.overtime.extended.casual",
            grouped_rules["PAY_RATES"]["overtime"]["extended"]["casual"],
            evidence["casual_extended_overtime_rate"],
        ),
        (
            "ORDINARY_TIME_RULES.ordinary_rates.casual_loading",
            grouped_rules["ORDINARY_TIME_RULES"]["ordinary_rates"]["casual_loading"],
            {
                "status": "not_found",
                "reasoning_summary": (
                    "Ordinary casual loading is outside the overtime-and-penalties "
                    "analysis scope."
                ),
            },
        ),
        (
            "GAP_BETWEEN_SHIFTS_RULE",
            grouped_rules["GAP_BETWEEN_SHIFTS_RULE"],
            evidence["gap_penalty_hours"],
        ),
        (
            "ORDINARY_HOUR_PENALTIES",
            grouped_rules["ORDINARY_HOUR_PENALTIES"],
            evidence["penalties"],
        ),
    ]

    for field_name, default_value, field_evidence in analysed_fields:
        status = str(field_evidence.get("status") or "not_found")
        if status in {"not_found", "defaulted", "needs_review"} or default_value is None:
            missing_fields.append(
                {
                    "field": field_name,
                    "default_value": default_value,
                    "reason": (
                        "The current analysis did not produce a derived value "
                        f"(evidence status: {status})."
                    ),
                }
            )

    if "public_holiday" not in grouped_rules["DAY_TREATMENT_RULES"]:
        missing_fields.append(
            {
                "field": "DAY_TREATMENT_RULES.public_holiday",
                "default_value": "not_configured",
                "reason": "The overtime and penalties analysis did not produce a usable public-holiday treatment.",
            }
        )

    gap_rule = grouped_rules["GAP_BETWEEN_SHIFTS_RULE"]
    if (
        isinstance(gap_rule.get("minimum_hours"), (int, float))
        and isinstance(gap_rule.get("loading"), (int, float))
        and not isinstance(values["casual_gap_penalty_rate"], (int, float))
    ):
        missing_fields.append(
            {
                "field": "GAP_BETWEEN_SHIFTS_RULE.casual_rate",
                "default_value": gap_rule.get("casual_rate"),
                "reason": (
                    "The gap rule was generated, but the analysis did not produce "
                    "a casual-specific treatment. Confirm whether the rule applies "
                    "to casual employees before use."
                ),
            }
        )

    day_treatment_inputs = values["day_treatment_inputs"]
    for day_name in ("Saturday", "Sunday", "public_holiday"):
        for worker_type in WORKER_TYPE_OPTIONS:
            treatment = day_treatment_inputs[day_name][worker_type]
            generated_day_rule = grouped_rules["DAY_TREATMENT_RULES"].get(day_name)
            if generated_day_rule and treatment["treatment"] not in {"overtime", "penalty"}:
                missing_fields.append(
                    {
                        "field": (
                            f"DAY_TREATMENT_RULES.{day_name}.{worker_type}."
                            "base_classification"
                        ),
                        "default_value": generated_day_rule[worker_type][
                            "base_classification"
                        ],
                        "reason": (
                            "A day-treatment rule was generated for another worker "
                            "type, but this worker type's treatment was not derived."
                        ),
                    }
                )
                continue
            if treatment["treatment"] != "penalty":
                continue
            if not isinstance(treatment["casual_loading"], (int, float)):
                generated_rule = grouped_rules["DAY_TREATMENT_RULES"].get(
                    day_name, {}
                ).get(worker_type, {})
                missing_fields.append(
                    {
                        "field": f"DAY_TREATMENT_RULES.{day_name}.{worker_type}.casual_rate",
                        "default_value": generated_rule.get("casual_rate"),
                        "reason": "No casual-specific day-treatment loading was derived.",
                    }
                )

    return grouped_rules, grouped_evidence, missing_fields


def _class_name_base_from_award_title(award_title: str) -> str:
    cleaned_title = award_title.strip().rstrip(".")
    cleaned_title = re.sub(r"^This is the\s+", "", cleaned_title, flags=re.IGNORECASE)
    cleaned_title = re.sub(r"\bAward\b.*$", "", cleaned_title, flags=re.IGNORECASE)
    cleaned_title = cleaned_title.replace("—", " ").replace("-", " ")
    words = re.findall(r"[A-Za-z0-9]+", cleaned_title)

    if not words:
        return "Award"

    return "".join(word.capitalize() for word in words)


def class_name_for_award(award_code: str, award_title: str | None = None) -> str:
    """Return the generated calculator class name for one award."""
    if award_title:
        return f"{_class_name_base_from_award_title(award_title)}Rules"

    cleaned = "".join(character for character in award_code if character.isalnum())

    if not cleaned:
        return "AwardRules"

    return f"{cleaned}Rules"


def _python_literal(value: Any) -> str:
    """Render one value as a stable Python literal."""
    return pprint.pformat(
        value,
        sort_dicts=False,
        width=88,
    )


def _commented_python_block(
    *,
    indent: str,
    label: str,
    value: Any,
) -> list[str]:
    """Render one Python literal block as commented lines."""
    rendered_value = _python_literal(value)
    rendered_lines = rendered_value.splitlines() or ["None"]

    commented_lines = [f"{indent}# {label} = {rendered_lines[0]}"]
    for continuation_line in rendered_lines[1:]:
        commented_lines.append(f"{indent}# {continuation_line}")

    return commented_lines


def calculator_rule_warning_label(field_name: str) -> str:
    """Return a readable business label for one generated calculator field."""
    labels = {
        "SHIFT_RULES.default_break_hours": "Default unpaid break",
        "SHIFT_RULES.minimum_paid_shift_hours": "Minimum paid shift",
        "ORDINARY_TIME_RULES.daily.day": "Daily ordinary-hours limit — day workers",
        "ORDINARY_TIME_RULES.daily.shift": "Daily ordinary-hours limit — shiftworkers",
        "ORDINARY_TIME_RULES.long_day": "Long-day ordinary-hours exception",
        "ORDINARY_TIME_RULES.period.basis": "Ordinary-hours period basis",
        "ORDINARY_TIME_RULES.period.max_work_days": "Maximum worked days",
        "ORDINARY_TIME_RULES.period.max_work_days_basis": (
            "Maximum worked-days period basis"
        ),
        "ORDINARY_TIME_RULES.period.part_time_uses_contracted_hours": (
            "Part-time contracted-hours overtime threshold"
        ),
        "ORDINARY_TIME_RULES.ordinary_rates.casual_loading": (
            "Ordinary-hours casual loading"
        ),
        "DAY_TREATMENT_RULES.public_holiday": "Public-holiday day treatment",
        "DAY_TREATMENT_RULES.public_holiday.shift.base_classification": (
            "Public-holiday treatment — shiftworkers"
        ),
        "GAP_BETWEEN_SHIFTS_RULE.casual_rate": (
            "Gap-between-shifts loading — casual employees"
        ),
        "PAY_RATES.overtime.public_holiday": "Public-holiday overtime rate",
        "TOP_UP_RULES.part_time": "Contracted-hours top-up — part-time employees",
        "TOP_UP_RULES.full_time": "Contracted-hours top-up — full-time employees",
    }
    if field_name in labels:
        return labels[field_name]

    readable_name = field_name.replace("_", " ").replace(".", " — ")
    return readable_name.strip().capitalize()


def calculator_rule_assumption_text(
    field_name: str,
    default_value: Any,
    reason: str,
) -> str:
    """Explain one generated assumption in plain business language."""
    explanations = {
        "SHIFT_RULES.default_break_hours": (
            "Default unpaid break: assumed to be 30 minutes because default breaks "
            "were not covered by the analysis."
        ),
        "SHIFT_RULES.minimum_paid_shift_hours": (
            "Minimum paid shift: disabled because minimum engagement was not covered "
            "by the analysis."
        ),
        "ORDINARY_TIME_RULES.long_day": (
            "Long-day exception: disabled because long-day arrangements were not "
            "covered by the analysis."
        ),
        "ORDINARY_TIME_RULES.period.basis": (
            "Ordinary-hours period: assumed to be weekly because the applicable "
            "averaging period was not determined by the analysis."
        ),
        "ORDINARY_TIME_RULES.period.max_work_days": (
            "Maximum worked days: no limit has been applied because this rule was not "
            "covered by the analysis."
        ),
        "ORDINARY_TIME_RULES.period.max_work_days_basis": (
            "Maximum-worked-days period: assumed to be weekly, although the analysis "
            "did not determine this setting."
        ),
        "ORDINARY_TIME_RULES.period.part_time_uses_contracted_hours": (
            "Part-time overtime threshold: assumed to use each employee's contracted "
            "hours because the analysis did not determine the treatment."
        ),
        "TOP_UP_RULES.part_time": (
            "Part-time contracted-hours top-up: enabled by assumption because top-up "
            "rules were outside the analysis."
        ),
        "TOP_UP_RULES.full_time": (
            "Full-time contracted-hours top-up: enabled by assumption because top-up "
            "rules were outside the analysis."
        ),
        "ORDINARY_TIME_RULES.daily.day": (
            "Daily limit for day workers: assumed to be 8 hours by mapping the "
            "reviewed 8-hour day-shift boundary to the calculator's day-worker category."
        ),
        "ORDINARY_TIME_RULES.daily.shift": (
            "Daily limit for shiftworkers: assumed to be 10 hours by mapping the "
            "reviewed 10-hour night-shift boundary to the calculator's shiftworker category."
        ),
        "ORDINARY_TIME_RULES.ordinary_rates.casual_loading": (
            "Ordinary-hours casual loading: assumed to be zero because ordinary casual "
            "loading is outside the overtime-and-penalties analysis."
        ),
        "DAY_TREATMENT_RULES.public_holiday.shift.base_classification": (
            "Public-holiday treatment for permanent shiftworkers: assumed to be "
            "ordinary hours with no loading because the reviewed rules did not provide "
            "a complete treatment. This assumption may underpay those employees."
        ),
        "GAP_BETWEEN_SHIFTS_RULE.casual_rate": (
            "Insufficient-break payment for casual employees: assumed to be zero "
            "because the reviewed payment expressly excludes casual employees."
        ),
    }
    if field_name in explanations:
        return explanations[field_name]

    rule_label = calculator_rule_warning_label(field_name)
    return (
        f"{rule_label}: assumed/default value {default_value!r} was used. {reason}"
    )


def render_python_text(data: dict[str, Any]) -> str:
    """Render one calculator rules artifact as a Python module."""
    award_code = str(data["award_code"])
    award_title = data.get("award_title")
    class_name = class_name_for_award(
        award_code,
        award_title if isinstance(award_title, str) else None,
    )
    calculator_rules = data["calculator_rules"]
    field_evidence = data["field_evidence"]
    generation_metadata = {
        "schema_version": data["schema_version"],
        "award_code": award_code,
    }
    if isinstance(award_title, str) and award_title.strip():
        generation_metadata["award_title"] = award_title.strip()
    if data.get("validation_warnings"):
        generation_metadata["validation_warnings"] = data["validation_warnings"]

    lines = [
        '"""Rule engine for award pay calculations."""',
        "",
    ]

    validation_warnings = data.get("validation_warnings", [])
    if isinstance(validation_warnings, list) and validation_warnings:
        lines.append("# IMPORTANT: REVIEW REQUIRED BEFORE USING THIS CALCULATOR")
        for warning in validation_warnings:
            lines.append(f"# - {warning}")
        lines.append("")

    missing_fields = data.get("missing_from_analysis", [])
    if isinstance(missing_fields, list) and missing_fields:
        valid_missing_fields = [
            missing_field
            for missing_field in missing_fields
            if isinstance(missing_field, dict)
        ]
        excluded_fields = [
            missing_field
            for missing_field in valid_missing_fields
            if str(missing_field.get("field") or "") in FIELDS_EXCLUDED_FROM_ANALYSIS
        ]
        assumed_fields = [
            missing_field
            for missing_field in valid_missing_fields
            if str(missing_field.get("field") or "") not in FIELDS_EXCLUDED_FROM_ANALYSIS
        ]

        warning_sections = [
            (
                "# RULES EXCLUDED FROM THE ANALYSIS",
                "# These rules were outside the overtime-and-penalties analysis and use defaults:",
                excluded_fields,
            ),
            (
                "# RULES BUILT WITH ASSUMPTIONS OR DEFAULTS",
                "# These rules were analysed but could not be mapped without an assumption:",
                assumed_fields,
            ),
        ]

        for section_header, section_explanation, section_fields in warning_sections:
            if not section_fields:
                continue
            lines.append(section_header)
            lines.append(section_explanation)
            for missing_field in section_fields:
                field_name = str(missing_field.get("field") or "Unknown field")
                default_value = missing_field.get("default_value")
                reason = str(missing_field.get("reason") or "")
                assumption_text = calculator_rule_assumption_text(
                    field_name,
                    default_value,
                    reason,
                )
                lines.append(f"# - {assumption_text}")
            lines.append("")

    lines.extend(
        [
            f"class {class_name}:",
            f'    """Business rules for award {award_code} pay calculations."""',
            "",
        ]
    )

    for class_attribute in GROUPED_CLASS_ATTRIBUTES:
        value = calculator_rules[class_attribute]
        rendered_value = _python_literal(value)
        rendered_lines = rendered_value.splitlines() or ["None"]

        if len(rendered_lines) == 1:
            lines.append(f"    {class_attribute} = {rendered_lines[0]}")
            continue

        lines.append(f"    {class_attribute} = {rendered_lines[0]}")
        for continuation_line in rendered_lines[1:]:
            lines.append(f"    {continuation_line}")

    lines.append("")
    lines.extend(
        _commented_python_block(
            indent="    ",
            label="FIELD_EVIDENCE",
            value=field_evidence,
        )
    )

    lines.append("")
    lines.extend(
        _commented_python_block(
            indent="    ",
            label="GENERATION_METADATA",
            value=generation_metadata,
        )
    )

    lines.append("")
    return "\n".join(lines)


def write_python_output(path: Path, data: dict[str, Any]) -> None:
    """Write the normalized Python module output."""
    write_text_output(path, render_python_text(data))
