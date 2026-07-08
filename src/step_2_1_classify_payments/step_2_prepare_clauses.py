"""Step 2.1 stage 2: prepare clause groups for classification."""

from __future__ import annotations

import json
from typing import Any, Iterator, Mapping

from .schema import (
    CONTENT_KEY,
    PLACEHOLDER_PREFIX,
    ClauseItem,
    TopLevelGroup,
)


def child_clause_nodes(mapping: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
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


def clause_content_lines(node: Mapping[str, Any]) -> list[str]:
    """Return the non-empty text lines stored on a clause node."""
    content = node.get(CONTENT_KEY, [])
    if isinstance(content, list):
        raw_items = content
    elif content:
        raw_items = [content]
    else:
        return []

    lines: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            formatted_item = item
        else:
            formatted_item = json.dumps(item, ensure_ascii=False)

        if formatted_item.strip():
            lines.append(formatted_item)

    return lines


def clause_title(node: Mapping[str, Any]) -> str:
    """Use the first content line as the clause title when available."""
    lines = clause_content_lines(node)
    return lines[0] if lines else ""


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
