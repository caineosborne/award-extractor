"""Step 2.1 stage 4: validate LLM classification output."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Mapping

from .schema import (
    PaymentClauseClassifierError,
    SUBSTANTIVE_L1_MINIMUM_CHARACTERS,
    TopLevelGroup,
)


def resolve_direct_l2_reference(
    group_reference: str,
    returned_reference: str,
    direct_references: set[str],
) -> str | None:
    """Map direct or relative L2 references back to the owning direct L2 clause."""
    for direct_reference in sorted(direct_references, key=len, reverse=True):
        if returned_reference == direct_reference:
            return direct_reference

        if returned_reference.startswith(f"{direct_reference}("):
            return direct_reference

        if returned_reference.startswith(f"{direct_reference}."):
            return direct_reference

        dotted_prefix = f"{group_reference}."
        if direct_reference.startswith(dotted_prefix):
            relative_reference = direct_reference.removeprefix(dotted_prefix)
            if returned_reference == relative_reference:
                return direct_reference
            if returned_reference.startswith(f"{relative_reference}("):
                return direct_reference
            if returned_reference.startswith(f"{relative_reference}."):
                return direct_reference

        bracket_prefix = f"{group_reference}("
        if direct_reference.startswith(bracket_prefix) and direct_reference.endswith(")"):
            relative_reference = direct_reference[len(bracket_prefix) : -1]
            if returned_reference == relative_reference:
                return direct_reference
            if returned_reference.startswith(f"{relative_reference}("):
                return direct_reference
            if returned_reference.startswith(f"{relative_reference}."):
                return direct_reference

    return None


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
        reference = resolve_direct_l2_reference(
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
            classified[reference]["tags"] = _unique_items(
                [*classified[reference]["tags"], *item["tags"]]
            )
            if reason and reason not in classified[reference]["reason"]:
                existing_reason = classified[reference]["reason"]
                classified[reference]["reason"] = f"{existing_reason} {reason}".strip()
            continue

        classified[reference] = {
            "text": source_text,
            "tags": _unique_items(item["tags"]),
            "reason": reason,
        }

    return top_result, classified


def _unique_items(value: list[str]) -> list[str]:
    """Remove duplicates while keeping the model's original order."""
    unique: list[str] = []
    for item in value:
        if item not in unique:
            unique.append(item)
    return unique
