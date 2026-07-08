"""Step 2.1 stage 5: apply deterministic classification repairs."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .schema import (
    ClauseItem,
    DeterministicTagAdjustment,
    EXPLICIT_OVERTIME_TRIGGER_RULES,
    TopLevelGroup,
)
from .step_4_validate_classification import has_substantive_l1_content


def unique_items(value: list[str]) -> list[str]:
    """Remove duplicates while keeping the model's original order."""
    unique: list[str] = []
    for item in value:
        if item not in unique:
            unique.append(item)
    return unique


def deterministic_overtime_rule_names(clause_text: str) -> list[str]:
    """Return the named explicit-overtime rules matched by the clause text."""
    normalized_text = clause_text.lower()
    matched_rule_names: list[str] = []

    for rule in EXPLICIT_OVERTIME_TRIGGER_RULES:
        for pattern in rule.patterns:
            if re.search(pattern, normalized_text, flags=re.IGNORECASE):
                matched_rule_names.append(rule.rule_name)
                break

    return matched_rule_names


def apply_deterministic_tag_repairs(
    group: TopLevelGroup,
    top_result: dict[str, Any],
    classified: OrderedDict[str, dict[str, Any]],
) -> list[DeterministicTagAdjustment]:
    """Repair missed explicit overtime tags using named deterministic rules."""
    adjustments: list[DeterministicTagAdjustment] = []

    clause_items_by_reference: OrderedDict[str, ClauseItem] = OrderedDict(
        (item.reference, item) for item in group.descendants
    )
    if not clause_items_by_reference and has_substantive_l1_content(group):
        clause_items_by_reference[group.reference] = ClauseItem(
            reference=group.reference,
            title=group.title,
            text=group.text,
            node=OrderedDict(),
        )

    for reference, clause_item in clause_items_by_reference.items():
        matched_rule_names = deterministic_overtime_rule_names(clause_item.text)
        if not matched_rule_names:
            continue

        existing_record = classified.get(reference)
        if existing_record is None:
            existing_record = {
                "text": clause_item.text,
                "tags": [],
                "reason": "",
            }
            classified[reference] = existing_record

        if "Ordinary Hours & Overtime" in existing_record["tags"]:
            continue

        existing_record["tags"] = unique_items(
            [*existing_record["tags"], "Ordinary Hours & Overtime"]
        )
        existing_record["deterministic_tag_adjustments"] = [
            {
                "tag_added": "Ordinary Hours & Overtime",
                "rule_names": matched_rule_names,
            }
        ]

        deterministic_reason = (
            "Deterministic tag repair applied: added `Ordinary Hours & Overtime` "
            "because the clause text matched the explicit overtime-trigger rule(s) "
            + ", ".join(matched_rule_names)
            + "."
        )
        existing_reason = str(existing_record.get("reason") or "").strip()
        existing_record["reason"] = (
            f"{existing_reason} {deterministic_reason}".strip()
            if existing_reason
            else deterministic_reason
        )

        adjustments.append(
            DeterministicTagAdjustment(
                reference=reference,
                tag_added="Ordinary Hours & Overtime",
                rule_names=tuple(matched_rule_names),
            )
        )

    if adjustments:
        top_result["payment_relevant"] = True
        top_result["requires_l2_classification"] = True
        adjustment_references = ", ".join(
            adjustment.reference for adjustment in adjustments
        )
        deterministic_summary = (
            "Deterministic explicit-overtime tagging added `Ordinary Hours & Overtime` "
            f"to: {adjustment_references}."
        )
        existing_top_reason = str(top_result.get("reason") or "").strip()
        top_result["reason"] = (
            f"{existing_top_reason} {deterministic_summary}".strip()
            if existing_top_reason
            else deterministic_summary
        )

    return adjustments
