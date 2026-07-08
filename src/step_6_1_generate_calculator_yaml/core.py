"""Shared logic for step 6.1 calculator Python generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pprint
import re
from typing import Any

from src.common.output_naming import award_title_from_award_json_path
from src.common.output_paths import write_text_output


DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_BOOLEAN_FIELDS = {
    "use_contracted_hours_for_pt_overtime": True,
    "pt_employees_entitled_to_contracted_topup": True,
    "ft_employees_entitled_to_contracted_topup": True,
}
SCALAR_RULE_FIELDS = (
    "ordinary_hours_limit_daily",
    "ordinary_hours_limit_weekly",
    "day_worker_ordinary_hours_daily",
    "day_worker_ordinary_hours_weekly",
    "standard_overtime_rate",
    "extended_overtime_rate",
    "sunday_overtime_rate",
    "saturday_overtime_rate",
    "apply_span_overtime",
    "span_overtime_hour",
    "gap_penalty_hours",
    "gap_penalty_rate",
    "two_tier_overtime",
    "two_tier_overtime_threshold",
)
OBJECT_RULE_FIELDS = (
    "penalties",
    "hours_pen_rules",
    "weekend_rules",
)
CLASS_ATTRIBUTE_BY_RULE_FIELD = {
    "ordinary_hours_limit_daily": "ORDINARY_HOURS_LIMIT_DAILY",
    "ordinary_hours_limit_weekly": "ORDINARY_HOURS_LIMIT_WEEKLY",
    "day_worker_ordinary_hours_daily": "DAY_WORKER_ORDINARY_HOURS_DAILY",
    "day_worker_ordinary_hours_weekly": "DAY_WORKER_ORDINARY_HOURS_WEEKLY",
    "use_contracted_hours_for_pt_overtime": "USE_CONTRACTED_HOURS_FOR_PT_OVERTIME",
    "pt_employees_entitled_to_contracted_topup": "PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP",
    "ft_employees_entitled_to_contracted_topup": "FT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP",
    "standard_overtime_rate": "STANDARD_OVERTIME_RATE",
    "extended_overtime_rate": "EXTENDED_OVERTIME_RATE",
    "sunday_overtime_rate": "SUNDAY_OVERTIME_RATE",
    "saturday_overtime_rate": "SATURDAY_OVERTIME_RATE",
    "apply_span_overtime": "APPLY_SPAN_OVERTIME",
    "span_overtime_hour": "SPAN_OVERTIME_HOUR",
    "gap_penalty_hours": "GAP_PENALTY_HOURS",
    "gap_penalty_rate": "GAP_PENALTY_RATE",
    "penalties": "PENALTIES",
    "hours_pen_rules": "HOURS_PEN_RULES",
    "weekend_rules": "WEEKEND_RULES",
    "two_tier_overtime": "TWO_TIER_OVERTIME",
    "two_tier_overtime_threshold": "TWO_TIER_OVERTIME_THRESHOLD",
}
FIXED_CLASS_ATTRIBUTES = (
    ("DEFAULT_BREAK", 0.5),
)
ALL_RULE_FIELDS = (
    *SCALAR_RULE_FIELDS,
    *DEFAULT_BOOLEAN_FIELDS.keys(),
    *OBJECT_RULE_FIELDS,
)
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
PENALTY_TYPE_OPTIONS = (
    "shift_based",
    "time_based",
)
PENALTY_BASIS_OPTIONS = (
    "start",
    "end",
    "duration",
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
                "enum": ["derived", "needs_review", "defaulted", "not_found"],
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


def penalty_rule_schema() -> dict[str, Any]:
    """Return one weekday penalty rule answer shape."""
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
            "description": {"type": "string"},
            "applies_to": {
                "type": "array",
                "items": {"type": "string", "enum": list(WORKER_TYPE_OPTIONS)},
            },
        },
        "required": [
            "code_name",
            "type",
            "basis",
            "start_hour",
            "end_hour",
            "rate",
            "description",
            "applies_to",
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
            "has_two_tier_overtime": _answer_schema(_nullable_boolean_schema()),
            "extended_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "higher_overtime_starts_after_hours": _answer_schema(_nullable_number_schema()),
            "saturday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
            "sunday_overtime_multiplier": _answer_schema(_nullable_number_schema()),
        },
        "required": [
            "standard_overtime_multiplier",
            "has_two_tier_overtime",
            "extended_overtime_multiplier",
            "higher_overtime_starts_after_hours",
            "saturday_overtime_multiplier",
            "sunday_overtime_multiplier",
        ],
    }

    span = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "day_workers_have_span_overtime": _answer_schema(_nullable_boolean_schema()),
            "live_span_cutoff_hour": _answer_schema(_nullable_number_schema()),
            "ordinary_span_summary": _answer_schema(_nullable_string_schema()),
        },
        "required": [
            "day_workers_have_span_overtime",
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
        ],
    }

    gap_between_shifts = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "minimum_break_required": _answer_schema(_nullable_boolean_schema()),
            "standard_minimum_break_hours": _answer_schema(_nullable_number_schema()),
            "breach_penalty_multiplier": _answer_schema(_nullable_number_schema()),
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
                "rule_plain_text": raw_rule.get("rule_plain_text"),
                "other_scope_notes": raw_rule.get("other_scope_notes"),
            }
        )

    return summarized


def known_rule_ids_by_ruleset(inputs: CalculatorYamlInputs) -> dict[str, set[str]]:
    """Collect the known rule ids from the three step 3.2 source artifacts."""
    return {
        "overtime_creation": {
            str(rule.get("rule_id")).strip()
            for rule in inputs.creation_artifact.get("rules", [])
            if isinstance(rule, dict) and str(rule.get("rule_id")).strip()
        },
        "overtime_consequence": {
            str(rule.get("rule_id")).strip()
            for rule in inputs.consequence_artifact.get("rules", [])
            if isinstance(rule, dict) and str(rule.get("rule_id")).strip()
        },
        "penalties": {
            str(rule.get("rule_id")).strip()
            for rule in inputs.penalties_artifact.get("rules", [])
            if isinstance(rule, dict) and str(rule.get("rule_id")).strip()
        },
    }


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
    *,
    known_rule_ids: dict[str, set[str]],
) -> dict[str, Any]:
    source_ruleset_keys = [
        str(value).strip()
        for value in raw_record.get("source_ruleset_keys", [])
        if str(value).strip()
    ]
    source_rule_ids = [
        str(value).strip()
        for value in raw_record.get("source_rule_ids", [])
        if str(value).strip()
    ]
    clause_references = [
        str(value).strip()
        for value in raw_record.get("clause_references", [])
        if str(value).strip()
    ]
    reasoning_summary = str(raw_record.get("reasoning_summary") or "").strip()
    special_case_notes = str(raw_record.get("special_case_notes") or "").strip()
    status = str(raw_record.get("status") or "").strip() or "needs_review"

    resolved_ruleset_keys = set(source_ruleset_keys)
    for source_rule_id in source_rule_ids:
        matching_rulesets = {
            ruleset_key
            for ruleset_key, valid_rule_ids in known_rule_ids.items()
            if source_rule_id in valid_rule_ids
        }
        if not matching_rulesets:
            raise CalculatorRulesYamlError(
                "Step 6.1 model cited unknown rule_id "
                f"'{source_rule_id}'."
            )
        resolved_ruleset_keys.update(matching_rulesets)

    return {
        "status": status,
        "source_ruleset_keys": sorted(resolved_ruleset_keys),
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
    known_rule_ids: dict[str, set[str]],
) -> dict[str, Any]:
    record = _get_question_record(questionnaire_answers, section_name, question_name)
    normalized = _normalize_evidence_record(record, known_rule_ids=known_rule_ids)
    normalized["answer"] = record.get("answer")
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

    for match in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", normalized_text):
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        meridiem = match.group(3)

        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12

        extracted_hours.append(hour + (minute / 60))

    for match in re.finditer(r"\b(\d{1,2}):(\d{2})\b", normalized_text):
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


def _canonical_penalty_code_name(
    raw_code_name: str,
    *,
    penalty_basis: str,
    start_hour: int | float,
    end_hour: int | float,
) -> str:
    base_name = _strip_trailing_time_tokens(raw_code_name) or "penalty_window"
    start_text = _format_hour_for_identifier(start_hour)
    end_text = _format_hour_for_identifier(end_hour)
    return f"{base_name}_{penalty_basis}_{start_text}_to_{end_text}"


def _validate_penalty_time_text(
    *,
    description: str,
    start_hour: int | float,
    end_hour: int | float,
) -> None:
    explicit_hours = _extract_explicit_hours_from_text(description)
    if len(explicit_hours) < 2:
        return

    expected_start = float(start_hour)
    expected_end = float(end_hour)
    stated_start = explicit_hours[0]
    stated_end = explicit_hours[1]

    if stated_start != expected_start or stated_end != expected_end:
        raise CalculatorRulesYamlError(
            "Step 6.1 produced a weekday penalty whose structured hours do not match its "
            f"description: '{description}' implies {stated_start} to {stated_end}, "
            f"but the structured window is {expected_start} to {expected_end}."
        )


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


def _weekend_day_entry(treatment: str | None, *, overtime_rate: Any, penalty_rate: Any) -> dict[str, Any] | None:
    if treatment == "overtime":
        return {"is_overtime": True}
    if treatment == "penalty":
        # The current calculator runtime does not have a separate day-worker
        # weekend penalty branch. Use the overtime path so weekend day shifts
        # still receive the required uplift.
        return {"is_overtime": True}
    return None


def _weekend_shift_entry(
    treatment: str | None,
    *,
    overtime_rate: Any,
    penalty_rate: Any,
) -> dict[str, Any] | None:
    if treatment == "overtime":
        return {"is_overtime": True}
    if treatment == "penalty":
        return {"is_overtime": False, "rate": None, "penalty_rate": penalty_rate}
    return None


def _build_live_penalties(
    shift_based_rules: list[dict[str, Any]],
    time_based_rules: list[dict[str, Any]],
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

        applies_to = [
            worker_type
            for worker_type in raw_rule.get("applies_to", [])
            if worker_type in WORKER_TYPE_OPTIONS
        ]
        description = str(raw_rule.get("description") or "").strip()
        lower_description = description.lower()
        lower_code_name = code_name.lower()

        _validate_penalty_time_text(
            description=description,
            start_hour=start_hour,
            end_hour=end_hour,
        )

        # The current engine only applies PENALTIES on ordinary weekdays and has
        # no calendar-aware weekend/public-holiday filtering in this path.
        # Exclude any calendar-specific live rule here so it does not leak onto
        # weekday calculations.
        calendar_specific_terms = (
            "saturday",
            "sunday",
            "weekend",
            "public holiday",
            "public_holiday",
        )
        if any(term in lower_code_name or term in lower_description for term in calendar_specific_terms):
            continue

        normalized_code_name = code_name
        if _penalty_code_name_has_explicit_times(code_name):
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
            "description": description,
            "applies_to": applies_to,
        }

    return penalties


def _weekend_effective_overtime_rate(
    *,
    treatment: str | None,
    overtime_rate: Any,
    penalty_rate: Any,
) -> Any:
    if treatment == "penalty" and isinstance(penalty_rate, (int, float)):
        return 1 + penalty_rate
    return overtime_rate


def validate_calculator_rules_shape(calculator_rules: dict[str, Any]) -> None:
    """Validate the final runtime shape without changing business values."""
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

    weekend_rules = calculator_rules.get("weekend_rules")
    if not isinstance(weekend_rules, dict):
        raise CalculatorRulesYamlError("Step 6.1 weekend_rules must be a mapping.")


def normalize_response_data(
    response_data: dict[str, Any],
    *,
    award_code: str,
    known_rule_ids: dict[str, set[str]],
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
            known_rule_ids=known_rule_ids,
        ),
        "shift_daily_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="shift_worker_daily_limit_hours",
            known_rule_ids=known_rule_ids,
        ),
        "day_weekly_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="day_worker_weekly_limit_hours",
            known_rule_ids=known_rule_ids,
        ),
        "shift_weekly_limit": _normalize_question_record(
            questionnaire_answers,
            section_name="core_hours",
            question_name="shift_worker_weekly_limit_hours",
            known_rule_ids=known_rule_ids,
        ),
        "standard_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="standard_overtime_multiplier",
            known_rule_ids=known_rule_ids,
        ),
        "has_two_tier_overtime": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="has_two_tier_overtime",
            known_rule_ids=known_rule_ids,
        ),
        "extended_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="extended_overtime_multiplier",
            known_rule_ids=known_rule_ids,
        ),
        "higher_overtime_starts_after_hours": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="higher_overtime_starts_after_hours",
            known_rule_ids=known_rule_ids,
        ),
        "saturday_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="saturday_overtime_multiplier",
            known_rule_ids=known_rule_ids,
        ),
        "sunday_overtime_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="overtime",
            question_name="sunday_overtime_multiplier",
            known_rule_ids=known_rule_ids,
        ),
        "day_workers_have_span_overtime": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="day_workers_have_span_overtime",
            known_rule_ids=known_rule_ids,
        ),
        "live_span_cutoff_hour": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="live_span_cutoff_hour",
            known_rule_ids=known_rule_ids,
        ),
        "ordinary_span_summary": _normalize_question_record(
            questionnaire_answers,
            section_name="span",
            question_name="ordinary_span_summary",
            known_rule_ids=known_rule_ids,
        ),
        "day_saturday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_saturday_treatment",
            known_rule_ids=known_rule_ids,
        ),
        "day_sunday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_sunday_treatment",
            known_rule_ids=known_rule_ids,
        ),
        "shift_saturday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_saturday_treatment",
            known_rule_ids=known_rule_ids,
        ),
        "shift_sunday_treatment": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_sunday_treatment",
            known_rule_ids=known_rule_ids,
        ),
        "day_saturday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_saturday_penalty_loading",
            known_rule_ids=known_rule_ids,
        ),
        "day_sunday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_sunday_penalty_loading",
            known_rule_ids=known_rule_ids,
        ),
        "shift_saturday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_saturday_penalty_loading",
            known_rule_ids=known_rule_ids,
        ),
        "shift_sunday_penalty_loading": _normalize_question_record(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_sunday_penalty_loading",
            known_rule_ids=known_rule_ids,
        ),
        "minimum_break_required": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="minimum_break_required",
            known_rule_ids=known_rule_ids,
        ),
        "standard_minimum_break_hours": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="standard_minimum_break_hours",
            known_rule_ids=known_rule_ids,
        ),
        "breach_penalty_multiplier": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="breach_penalty_multiplier",
            known_rule_ids=known_rule_ids,
        ),
        "special_case_thresholds": _normalize_question_record(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="special_case_thresholds",
            known_rule_ids=known_rule_ids,
        ),
        "shift_based_penalties": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="shift_based_penalties",
            known_rule_ids=known_rule_ids,
        ),
        "time_based_penalties": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="time_based_penalties",
            known_rule_ids=known_rule_ids,
        ),
        "other_penalty_notes": _normalize_question_record(
            questionnaire_answers,
            section_name="weekday_penalties",
            question_name="other_penalty_notes",
            known_rule_ids=known_rule_ids,
        ),
    }

    has_two_tier = question_records["has_two_tier_overtime"]["answer"]
    minimum_break_required = question_records["minimum_break_required"]["answer"]

    shift_based_penalties_answer = question_records["shift_based_penalties"]["answer"] or []
    time_based_penalties_answer = question_records["time_based_penalties"]["answer"] or []

    weekend_rules: dict[str, Any] = {}
    day_weekend_rules: dict[str, Any] = {}
    shift_weekend_rules: dict[str, Any] = {}

    day_saturday_entry = _weekend_day_entry(
        question_records["day_saturday_treatment"]["answer"],
        overtime_rate=question_records["saturday_overtime_multiplier"]["answer"],
        penalty_rate=question_records["day_saturday_penalty_loading"]["answer"],
    )
    day_sunday_entry = _weekend_day_entry(
        question_records["day_sunday_treatment"]["answer"],
        overtime_rate=question_records["sunday_overtime_multiplier"]["answer"],
        penalty_rate=question_records["day_sunday_penalty_loading"]["answer"],
    )
    shift_saturday_entry = _weekend_shift_entry(
        question_records["shift_saturday_treatment"]["answer"],
        overtime_rate=question_records["saturday_overtime_multiplier"]["answer"],
        penalty_rate=question_records["shift_saturday_penalty_loading"]["answer"],
    )
    shift_sunday_entry = _weekend_shift_entry(
        question_records["shift_sunday_treatment"]["answer"],
        overtime_rate=question_records["sunday_overtime_multiplier"]["answer"],
        penalty_rate=question_records["shift_sunday_penalty_loading"]["answer"],
    )

    if day_saturday_entry is not None:
        day_weekend_rules["Saturday"] = day_saturday_entry
    if day_sunday_entry is not None:
        day_weekend_rules["Sunday"] = day_sunday_entry
    if shift_saturday_entry is not None:
        shift_weekend_rules["Saturday"] = shift_saturday_entry
    if shift_sunday_entry is not None:
        shift_weekend_rules["Sunday"] = shift_sunday_entry
    if day_weekend_rules:
        weekend_rules["day"] = day_weekend_rules
    if shift_weekend_rules:
        weekend_rules["shift"] = shift_weekend_rules

    normalized_rules: dict[str, Any] = {
        "ordinary_hours_limit_daily": question_records["shift_daily_limit"]["answer"],
        "ordinary_hours_limit_weekly": question_records["shift_weekly_limit"]["answer"],
        "day_worker_ordinary_hours_daily": question_records["day_daily_limit"]["answer"],
        "day_worker_ordinary_hours_weekly": question_records["day_weekly_limit"]["answer"],
        "standard_overtime_rate": question_records["standard_overtime_multiplier"]["answer"],
        "extended_overtime_rate": (
            question_records["extended_overtime_multiplier"]["answer"]
            if has_two_tier is True
            else None
        ),
        "sunday_overtime_rate": question_records["sunday_overtime_multiplier"]["answer"],
        "saturday_overtime_rate": question_records["saturday_overtime_multiplier"]["answer"],
        "apply_span_overtime": question_records["day_workers_have_span_overtime"]["answer"],
        "span_overtime_hour": (
            question_records["live_span_cutoff_hour"]["answer"]
            if question_records["day_workers_have_span_overtime"]["answer"] is True
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
        "penalties": _build_live_penalties(
            shift_based_penalties_answer,
            time_based_penalties_answer,
        ),
        "hours_pen_rules": {},
        "weekend_rules": weekend_rules,
        "two_tier_overtime": has_two_tier,
        "two_tier_overtime_threshold": (
            question_records["higher_overtime_starts_after_hours"]["answer"]
            if has_two_tier is True
            else None
        ),
    }

    validate_calculator_rules_shape(normalized_rules)

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
        "extended_overtime_rate": _merge_evidence_records(
            [
                question_records["has_two_tier_overtime"],
                question_records["extended_overtime_multiplier"],
            ],
            empty_reason="No evidence available for extended overtime multiplier.",
        ),
        "sunday_overtime_rate": _merge_evidence_records(
            [question_records["sunday_overtime_multiplier"]],
            empty_reason="No evidence available for Sunday overtime multiplier.",
        ),
        "saturday_overtime_rate": _merge_evidence_records(
            [question_records["saturday_overtime_multiplier"]],
            empty_reason="No evidence available for Saturday overtime multiplier.",
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
        "penalties": _merge_evidence_records(
            [
                question_records["shift_based_penalties"],
                question_records["time_based_penalties"],
                question_records["other_penalty_notes"],
            ],
            empty_reason="No evidence available for weekday penalties.",
        ),
        "hours_pen_rules": default_evidence(
            "No separate hours_pen_rules mapping is generated in step 6.1 yet.",
            "defaulted",
        ),
        "weekend_rules": _merge_evidence_records(
            [
                question_records["day_saturday_treatment"],
                question_records["day_sunday_treatment"],
                question_records["shift_saturday_treatment"],
                question_records["shift_sunday_treatment"],
                question_records["day_saturday_penalty_loading"],
                question_records["day_sunday_penalty_loading"],
                question_records["shift_saturday_penalty_loading"],
                question_records["shift_sunday_penalty_loading"],
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
    }

    for field_name, default_value in DEFAULT_BOOLEAN_FIELDS.items():
        normalized_rules[field_name] = default_value
        normalized_evidence[field_name] = default_evidence(
            "Defaulted to True because the source rulesets do not answer this field.",
            "defaulted",
        )

    return {
        "schema_version": "calculator-rules-python-v1",
        "award_code": award_code,
        "calculator_rules": normalized_rules,
        "field_evidence": normalized_evidence,
    }


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

    lines = [
        '"""Rule engine for award pay calculations."""',
        "",
        "",
        f"class {class_name}:",
        f'    """Business rules for award {award_code} pay calculations."""',
        "",
    ]

    for field_name in ALL_RULE_FIELDS:
        class_attribute = CLASS_ATTRIBUTE_BY_RULE_FIELD[field_name]
        value = calculator_rules[field_name]
        rendered_value = _python_literal(value)
        rendered_lines = rendered_value.splitlines() or ["None"]

        if len(rendered_lines) == 1:
            lines.append(f"    {class_attribute} = {rendered_lines[0]}")
            continue

        lines.append(f"    {class_attribute} = {rendered_lines[0]}")
        for continuation_line in rendered_lines[1:]:
            lines.append(f"    {continuation_line}")

    for class_attribute, value in FIXED_CLASS_ATTRIBUTES:
        lines.append(f"    {class_attribute} = {_python_literal(value)}")

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
