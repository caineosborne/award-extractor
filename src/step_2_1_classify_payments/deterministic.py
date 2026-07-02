"""Deterministic helpers for step 2.1 payment classification."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.common.output_paths import write_text_output
from src.step_2_1_classify_payments.schema import (
    CONTENT_KEY,
    DEFAULT_AWARD_PATH,
    EXPLICIT_OVERTIME_TRIGGER_RULES,
    PLACEHOLDER_PREFIX,
    SCHEMA_VERSION,
    SUBSTANTIVE_L1_MINIMUM_CHARACTERS,
    ClauseItem,
    DeterministicTagAdjustment,
    PaymentClauseClassifierError,
    TopLevelGroup,
)


@dataclass(frozen=True)
class Step2ClassificationInputs:
    """Prepared deterministic inputs for step 2.1 payment classification."""

    source_path: Path
    destination: Path
    award: OrderedDict[str, Any]
    groups: tuple[TopLevelGroup, ...]


def load_award(award_path: Path | str = DEFAULT_AWARD_PATH) -> OrderedDict[str, Any]:
    """Read the processed award JSON file and preserve key order."""
    path = Path(award_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def output_path_for_award(award_path: Path | str) -> Path:
    """Build the default output path for a classified award file."""
    from src.common.output_naming import classification_path_for_award_json

    return classification_path_for_award_json(award_path)


def timestamped_output_path(
    output_path: Path | str,
    timestamp=None,
) -> Path:
    from src.common.output_paths import timestamped_archive_path

    return timestamped_archive_path(output_path, timestamp)


def child_clause_nodes(mapping: Mapping[str, Any]):
    """Yield nested clause dictionaries and skip the text-only content entry."""
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, Mapping):
            yield str(key), value


def is_placeholder_key(key: str) -> bool:
    """Return True for wrapper keys that are not real clause references."""
    return key.startswith(PLACEHOLDER_PREFIX)


def is_lettered_key(key: str) -> bool:
    """Return True for short lettered subclause keys like a or b."""
    return len(key) <= 3 and key.isalpha()


def format_child_reference(parent_reference: str, child_key: str) -> str:
    """Convert a child key into the full clause reference used in outputs."""
    if is_lettered_key(child_key):
        return f"{parent_reference}({child_key})"
    return child_key


def format_content_item(item: Any) -> str:
    """Convert one content item into displayable text."""
    if isinstance(item, str):
        return item
    return json.dumps(item, ensure_ascii=False)


def clause_content_lines(node: Mapping[str, Any]) -> list[str]:
    """Return the non-empty text lines stored on a clause node."""
    content = node.get(CONTENT_KEY, [])
    if isinstance(content, list):
        lines: list[str] = []
        for item in content:
            formatted_item = format_content_item(item)
            if formatted_item.strip():
                lines.append(formatted_item)
        return lines

    if content:
        formatted_content = format_content_item(content)
        if formatted_content.strip():
            return [formatted_content]

    return []


def clause_title(node: Mapping[str, Any]) -> str:
    """Use the first content line as the clause title when available."""
    lines = clause_content_lines(node)
    return lines[0] if lines else ""


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


def flatten_clause(reference: str, node: Mapping[str, Any]) -> str:
    """Turn one clause subtree into labelled plain text for the model prompt."""
    lines: list[str] = []

    def walk(current_reference: str, current_node: Mapping[str, Any]) -> None:
        for line in clause_content_lines(current_node):
            lines.append(f"{current_reference}: {line}")

        for child_key, child_node in child_clause_nodes(current_node):
            if is_placeholder_key(child_key):
                walk(current_reference, child_node)
            else:
                child_reference = format_child_reference(current_reference, child_key)
                walk(child_reference, child_node)

    walk(reference, node)
    return "\n".join(lines)


def collect_descendants(parent_reference: str, node: Mapping[str, Any]) -> tuple[ClauseItem, ...]:
    """Collect direct L2 clauses under one top-level clause."""
    descendants: list[ClauseItem] = []

    def collect_direct(current_reference: str, current_node: Mapping[str, Any]) -> None:
        for child_key, child_node in child_clause_nodes(current_node):
            if is_placeholder_key(child_key):
                collect_direct(current_reference, child_node)
                continue

            child_reference = format_child_reference(current_reference, child_key)
            descendants.append(
                ClauseItem(
                    reference=child_reference,
                    title=clause_title(child_node),
                    text=flatten_clause(child_reference, child_node),
                    node=child_node,
                )
            )

    collect_direct(parent_reference, node)
    return tuple(descendants)


def build_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
    """Group the award into top-level clauses and their direct L2 descendants."""
    groups: list[TopLevelGroup] = []

    for _part_heading, part_node in child_clause_nodes(award):
        for top_reference, top_node in child_clause_nodes(part_node):
            if is_placeholder_key(top_reference):
                continue

            groups.append(
                TopLevelGroup(
                    reference=top_reference,
                    title=clause_title(top_node),
                    text=flatten_clause(top_reference, top_node),
                    descendants=collect_descendants(top_reference, top_node),
                )
            )

    return tuple(groups)


def iter_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
    """Return top-level clause groups using the legacy helper name used by tests."""
    return build_top_level_groups(award)


def l1_body_text(group: TopLevelGroup) -> str:
    """Return top-level clause text without the heading line."""
    body_lines: list[str] = []

    for line in group.text.splitlines():
        _separator, _prefix, text = line.partition(":")
        normalized_text = text.strip()
        if normalized_text == group.title:
            continue
        if normalized_text:
            body_lines.append(normalized_text)

    return "\n".join(body_lines)


def has_substantive_l1_content(group: TopLevelGroup) -> bool:
    """Return True when an L1 clause has body text worth classifying on its own."""
    if group.descendants:
        return False
    return len(l1_body_text(group)) > SUBSTANTIVE_L1_MINIMUM_CHARACTERS


def title_only_top_level_result(group: TopLevelGroup) -> dict[str, Any]:
    """Return the default result for a heading-only top-level clause."""
    return {
        "title": group.title,
        "payment_relevant": False,
        "definition_relevant": False,
        "requires_l2_classification": False,
        "reason": "Top-level clause contains only a heading and no direct L2 clauses.",
    }


def map_to_direct_l2_reference(reference: str, direct_references: set[str]) -> str | None:
    """Map a returned reference back to the direct L2 clause that owns it."""
    if reference in direct_references:
        return reference

    matching_direct_references = [
        direct_reference
        for direct_reference in direct_references
        if reference.startswith(f"{direct_reference}(")
        or reference.startswith(f"{direct_reference}.")
    ]

    if not matching_direct_references:
        return None

    return max(matching_direct_references, key=len)


def direct_l2_relative_reference(group_reference: str, direct_reference: str) -> str | None:
    """Return the child-only form of a direct L2 reference within one L1 group."""
    dotted_prefix = f"{group_reference}."
    if direct_reference.startswith(dotted_prefix):
        return direct_reference.removeprefix(dotted_prefix)

    bracket_prefix = f"{group_reference}("
    if direct_reference.startswith(bracket_prefix) and direct_reference.endswith(")"):
        return direct_reference[len(bracket_prefix) : -1]

    return None


def map_relative_reference_to_direct_l2(
    group_reference: str,
    returned_reference: str,
    direct_references: set[str],
) -> str | None:
    """Map child-only references like 2 or 2(a) back to the full direct L2 reference."""
    for direct_reference in direct_references:
        relative_reference = direct_l2_relative_reference(group_reference, direct_reference)
        if not relative_reference:
            continue

        if returned_reference == relative_reference:
            return direct_reference

        if returned_reference.startswith(f"{relative_reference}("):
            return direct_reference

        if returned_reference.startswith(f"{relative_reference}."):
            return direct_reference

    return None


def direct_l2_reference_for(reference: str, direct_references: set[str]) -> str | None:
    """Return the owning direct L2 reference using the legacy helper name."""
    return map_to_direct_l2_reference(reference, direct_references)


def validate_group_classification(
    group: TopLevelGroup,
    classification: Mapping[str, Any],
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    """Check model references and attach the results back to source clause text."""
    top = classification.get("top_level_clause")
    if top.get("reference") != group.reference:
        raise PaymentClauseClassifierError(
            f"Expected top-level reference {group.reference}, got {top.get('reference')}."
        )

    payment_relevant = bool(top.get("payment_relevant"))
    definition_relevant = bool(top.get("definition_relevant"))
    requires_l2_classification = payment_relevant or definition_relevant

    top_result = {
        "title": str(top.get("title") or group.title),
        "payment_relevant": payment_relevant,
        "definition_relevant": definition_relevant,
        "requires_l2_classification": requires_l2_classification,
        "reason": str(top.get("reason") or ""),
    }

    descendants_by_reference = {item.reference: item for item in group.descendants}
    direct_references = set(descendants_by_reference)
    classified_raw = classification["classified_clauses"]

    if not payment_relevant and not definition_relevant and classified_raw:
        raise PaymentClauseClassifierError(
            f"Clause {group.reference} is not payment or definition relevant but returned classified clauses."
        )

    classified: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for item in classified_raw:
        returned_reference = item["reference"]
        reference = map_to_direct_l2_reference(returned_reference, direct_references)

        if reference is None:
            reference = map_relative_reference_to_direct_l2(
                group.reference,
                returned_reference,
                direct_references,
            )

        if (
            reference is None
            and returned_reference == group.reference
            and has_substantive_l1_content(group)
        ):
            reference = group.reference

        if reference is None:
            raise PaymentClauseClassifierError(
                f"Unknown classified clause reference: {returned_reference}"
            )

        if reference == group.reference:
            source_text = group.text
        else:
            source_text = descendants_by_reference[reference].text

        reason = str(item.get("reason") or "")
        if returned_reference != reference:
            reason = (
                f"{reason} Returned nested reference {returned_reference}; "
                f"classified under {reference}."
            ).strip()

        if reference in classified:
            classified[reference]["tags"] = unique_items(
                [*classified[reference]["tags"], *item["tags"]]
            )
            if reason and reason not in classified[reference]["reason"]:
                existing_reason = classified[reference]["reason"]
                classified[reference]["reason"] = f"{existing_reason} {reason}".strip()
            continue

        classified[reference] = {
            "text": source_text,
            "tags": unique_items(item["tags"]),
            "reason": reason,
        }

    return top_result, classified


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


def build_result_artifact(
    *,
    source_path: Path,
    model: str,
    top_level_clauses: OrderedDict[str, dict[str, Any]],
    classified_clauses: OrderedDict[str, dict[str, Any]],
) -> OrderedDict[str, Any]:
    """Build the final step 2.1 JSON artifact."""
    result: OrderedDict[str, Any] = OrderedDict()
    result["source_file"] = str(source_path)
    result["model"] = model
    result["schema_version"] = SCHEMA_VERSION
    result["top_level_clauses"] = top_level_clauses
    result["classified_clauses"] = classified_clauses
    return result


def write_result(destination: Path, result: OrderedDict[str, Any]) -> None:
    """Write the current step 2.1 classification artifact."""
    output_json = json.dumps(result, indent=2, ensure_ascii=False)
    write_text_output(destination, output_json)


def resolve_classification_inputs(
    *,
    award_path: Path | str = DEFAULT_AWARD_PATH,
    output_path: Path | str | None = None,
) -> Step2ClassificationInputs:
    """Load the source award and resolve the deterministic output path."""
    source_path = Path(award_path)
    destination = (
        Path(output_path)
        if output_path is not None
        else output_path_for_award(source_path)
    )
    award = load_award(source_path)
    groups = build_top_level_groups(award)
    return Step2ClassificationInputs(
        source_path=source_path,
        destination=destination,
        award=award,
        groups=groups,
    )
