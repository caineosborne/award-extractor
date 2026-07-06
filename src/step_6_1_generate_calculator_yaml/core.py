"""Shared logic for step 6.1 calculator YAML generation."""

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
    "saturday_penalty_rate",
    "sunday_penalty_rate",
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
    "saturday_penalty_rate": "SATURDAY_PENALTY_RATE",
    "sunday_penalty_rate": "SUNDAY_PENALTY_RATE",
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


class CalculatorRulesYamlError(RuntimeError):
    """Raised when step 6.1 cannot produce a valid calculator YAML artifact."""


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
    """Return the strict evidence schema for one calculator field."""
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
        },
        "required": [
            "status",
            "source_ruleset_keys",
            "source_rule_ids",
            "clause_references",
            "reasoning_summary",
        ],
    }


def _nullable_number_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "number"},
            {"type": "null"},
        ]
    }


def _nullable_boolean_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "boolean"},
            {"type": "null"},
        ]
    }


def _nullable_object_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "object", "additionalProperties": True},
            {"type": "null"},
        ]
    }


def calculator_rules_response_json_schema() -> dict[str, Any]:
    """Return the strict JSON schema expected from the step 6.1 model."""
    calculator_rules_properties: dict[str, Any] = {
        "ordinary_hours_limit_daily": _nullable_number_schema(),
        "ordinary_hours_limit_weekly": _nullable_number_schema(),
        "day_worker_ordinary_hours_daily": _nullable_number_schema(),
        "day_worker_ordinary_hours_weekly": _nullable_number_schema(),
        "standard_overtime_rate": _nullable_number_schema(),
        "extended_overtime_rate": _nullable_number_schema(),
        "sunday_overtime_rate": _nullable_number_schema(),
        "saturday_overtime_rate": _nullable_number_schema(),
        "saturday_penalty_rate": _nullable_number_schema(),
        "sunday_penalty_rate": _nullable_number_schema(),
        "apply_span_overtime": _nullable_boolean_schema(),
        "span_overtime_hour": _nullable_number_schema(),
        "gap_penalty_hours": _nullable_number_schema(),
        "gap_penalty_rate": _nullable_number_schema(),
        "penalties": _nullable_object_schema(),
        "hours_pen_rules": _nullable_object_schema(),
        "weekend_rules": _nullable_object_schema(),
        "two_tier_overtime": _nullable_boolean_schema(),
        "two_tier_overtime_threshold": _nullable_number_schema(),
    }

    field_evidence_properties = {
        field_name: evidence_schema()
        for field_name in calculator_rules_properties
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "calculator_rules": {
                "type": "object",
                "additionalProperties": False,
                "properties": calculator_rules_properties,
                "required": list(calculator_rules_properties),
            },
            "field_evidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": field_evidence_properties,
                "required": list(field_evidence_properties),
            },
        },
        "required": ["calculator_rules", "field_evidence"],
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
    }


def unwrap_rule_value(raw_value: Any) -> Any:
    """Flatten review-oriented calculator field wrappers into plain values."""
    if not isinstance(raw_value, dict):
        return raw_value

    if "value" in raw_value:
        return raw_value.get("value")

    cleaned_mapping = {
        key: value
        for key, value in raw_value.items()
        if key not in {"evidence_status", "unit"}
    }

    if len(cleaned_mapping) == 1 and "value" in cleaned_mapping:
        return cleaned_mapping["value"]

    return cleaned_mapping


def normalize_response_data(
    response_data: dict[str, Any],
    *,
    award_code: str,
    known_rule_ids: dict[str, set[str]],
) -> dict[str, Any]:
    """Normalize the model response into the persisted calculator structure."""
    calculator_rules = response_data.get("calculator_rules", {})
    field_evidence = response_data.get("field_evidence", {})

    if not isinstance(calculator_rules, dict):
        raise CalculatorRulesYamlError("Step 6.1 model output is missing calculator_rules.")
    if not isinstance(field_evidence, dict):
        raise CalculatorRulesYamlError("Step 6.1 model output is missing field_evidence.")

    normalized_rules: dict[str, Any] = {}
    normalized_evidence: dict[str, dict[str, Any]] = {}

    for field_name in SCALAR_RULE_FIELDS:
        normalized_rules[field_name] = unwrap_rule_value(
            calculator_rules.get(field_name)
        )
    for field_name in OBJECT_RULE_FIELDS:
        normalized_object_value = unwrap_rule_value(calculator_rules.get(field_name))
        normalized_rules[field_name] = normalized_object_value or {}

    for field_name, default_value in DEFAULT_BOOLEAN_FIELDS.items():
        normalized_rules[field_name] = default_value
        normalized_evidence[field_name] = default_evidence(
            "Defaulted to True because the source rulesets do not answer this field.",
            "defaulted",
        )

    for field_name in (*SCALAR_RULE_FIELDS, *OBJECT_RULE_FIELDS):
        raw_evidence = field_evidence.get(field_name)
        if not isinstance(raw_evidence, dict):
            status = "not_found" if normalized_rules[field_name] in (None, {}) else "needs_review"
            normalized_evidence[field_name] = default_evidence(
                "No field evidence was returned by the model response.",
                status,
            )
            continue

        source_ruleset_keys = [
            str(value).strip()
            for value in raw_evidence.get("source_ruleset_keys", [])
            if str(value).strip()
        ]
        source_rule_ids = [
            str(value).strip()
            for value in raw_evidence.get("source_rule_ids", [])
            if str(value).strip()
        ]
        clause_references = [
            str(value).strip()
            for value in raw_evidence.get("clause_references", [])
            if str(value).strip()
        ]
        reasoning_summary = str(raw_evidence.get("reasoning_summary") or "").strip()
        status = str(raw_evidence.get("status") or "").strip() or "needs_review"

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

        normalized_evidence[field_name] = {
            "status": status,
            "source_ruleset_keys": sorted(resolved_ruleset_keys),
            "source_rule_ids": source_rule_ids,
            "clause_references": clause_references,
            "reasoning_summary": reasoning_summary or "No reasoning summary provided.",
        }

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
    class_name = class_name_for_award(award_code, award_title if isinstance(award_title, str) else None)
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
