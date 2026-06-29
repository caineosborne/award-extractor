"""Step 2 payment classifier.

Prompt ownership:
- Uses `src/prompts/payment_clause_classification.py`.
"""

import argparse
import json
import os
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.output_paths import (
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    timestamped_archive_path,
    write_text_with_archive,
)
from src.prompts.payment_clause_classification import (
    ALLOWED_TAGS,
    SYSTEM_PROMPT,
    build_user_prompt,
)


# 1. Imports / constants

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AWARD_PATH = (
    PROJECT_ROOT / "data" / "processed" / "MA000018" / "MA000018.json"
)
DEFAULT_MODEL = "gpt-5.4-mini"
SCHEMA_VERSION = "payment-classification-v2"
CONTENT_KEY = "_content"
PLACEHOLDER_PREFIX = "No Level"
SUBSTANTIVE_L1_MINIMUM_CHARACTERS = 30


@dataclass(frozen=True)
class DeterministicTagRule:
    """One explicit post-classification tagging rule for auditability."""

    rule_name: str
    tag_to_add: str
    patterns: tuple[str, ...]


EXPLICIT_OVERTIME_TRIGGER_RULES: tuple[DeterministicTagRule, ...] = (
    DeterministicTagRule(
        rule_name="explicit_overtime_will_be_paid",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bovertime will be paid\b",
            r"\bpaid overtime\b",
            r"\bovertime is payable\b",
        ),
    ),
    DeterministicTagRule(
        rule_name="explicit_paid_at_overtime_rates",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bpaid at overtime rates?\b",
            r"\bpayment of overtime\b",
        ),
    ),
    DeterministicTagRule(
        rule_name="explicit_overtime_provisions_apply",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(r"\bovertime provisions\b.*\bapply\b",),
    ),
    DeterministicTagRule(
        rule_name="explicit_without_payment_of_overtime",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(r"\bwithout payment of overtime\b",),
    ),
    DeterministicTagRule(
        rule_name="explicit_excess_hours_reference_to_overtime",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bfor work in excess of\b[\s\S]*\bovertime\b",
            r"\bfor work in excess of\b[\s\S]*\bpenalties specified\b",
        ),
    ),
)


class PaymentClauseClassifierError(RuntimeError):
    """Raised when the classifier cannot continue with the current award."""


# 2. Data structures


@dataclass(frozen=True)
class ClauseItem:
    """Store one clause that may be sent to the model for tagging."""

    reference: str
    title: str
    text: str
    node: Mapping[str, Any]


@dataclass(frozen=True)
class TopLevelGroup:
    """Store one top-level clause and the direct L2 clauses grouped under it."""

    reference: str
    title: str
    text: str
    descendants: tuple[ClauseItem, ...]


@dataclass(frozen=True)
class DeterministicTagAdjustment:
    """Record one deterministic tag repair applied after model classification."""

    reference: str
    tag_added: str
    rule_names: tuple[str, ...]


# 3. Small helpers


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load environment variables and require an OpenAI API key."""
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise PaymentClauseClassifierError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_award(award_path: Path | str = DEFAULT_AWARD_PATH) -> OrderedDict[str, Any]:
    """Read the processed award JSON file and preserve key order."""
    path = Path(award_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def output_path_for_award(award_path: Path | str) -> Path:
    """Build the default output path for a classified award file."""
    path = Path(award_path)
    return path_in_category(
        path,
        PAYMENT_CLAUSE_IDENTIFIER_DIR,
        f"{path.stem}_payment_classification.json",
    )


def timestamped_output_path(
    output_path: Path | str,
    timestamp: datetime | None = None,
) -> Path:
    """Build the archive path used for timestamped output snapshots."""
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
    # Read the raw content list that was stored on this clause node in the award JSON.
    content = node.get(CONTENT_KEY, [])
    if isinstance(content, list):
        lines: list[str] = []
        for item in content:
            # Convert each content item into text so it can be used in prompts and outputs.
            formatted_item = format_content_item(item)
            # Ignore blank lines so downstream text is easier to read.
            if formatted_item.strip():
                lines.append(formatted_item)
        return lines

    if content:
        # Some nodes store a single content value instead of a list.
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


# 4. Award parsing / grouping


def flatten_clause(reference: str, node: Mapping[str, Any]) -> str:
    """Turn one clause subtree into labelled plain text for the model prompt."""
    lines: list[str] = []

    def walk(current_reference: str, current_node: Mapping[str, Any]) -> None:
        # Add each text line with its clause reference so the model can see where it came from.
        for line in clause_content_lines(current_node):
            lines.append(f"{current_reference}: {line}")

        # Walk into nested clause nodes so the full subtree is included in the prompt text.
        for child_key, child_node in child_clause_nodes(current_node):
            if is_placeholder_key(child_key):
                # Placeholder wrappers do not change the clause reference, so keep the same label.
                walk(current_reference, child_node)
            else:
                # Build the child's full clause reference before walking into that child node.
                child_reference = format_child_reference(current_reference, child_key)
                walk(child_reference, child_node)

    walk(reference, node)
    return "\n".join(lines)


def collect_descendants(parent_reference: str, node: Mapping[str, Any]) -> tuple[ClauseItem, ...]:
    """Collect direct L2 clauses under one top-level clause."""
    descendants: list[ClauseItem] = []

    def collect_direct(current_reference: str, current_node: Mapping[str, Any]) -> None:
        # Look at the nested clause nodes directly below the current node.
        for child_key, child_node in child_clause_nodes(current_node):
            if is_placeholder_key(child_key):
                # Skip wrapper levels and keep looking until we reach real clause references.
                collect_direct(current_reference, child_node)
                continue

            # Convert the child key into the full clause reference used everywhere else.
            child_reference = format_child_reference(current_reference, child_key)
            descendants.append(
                ClauseItem(
                    reference=child_reference,
                    # Use the first content line as the display title for this clause.
                    title=clause_title(child_node),
                    # Flatten the full child subtree so lower levels stay attached to this direct L2 clause.
                    text=flatten_clause(child_reference, child_node),
                    node=child_node,
                )
            )

    collect_direct(parent_reference, node)
    return tuple(descendants)


def build_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
    """Group the award into top-level clauses and their direct L2 descendants."""
    groups: list[TopLevelGroup] = []

    # The processed award is structured by Parts first, so start at that level.
    for _part_heading, part_node in child_clause_nodes(award):
        # Within each Part, group work around each top-level clause reference.
        for top_reference, top_node in child_clause_nodes(part_node):
            if is_placeholder_key(top_reference):
                continue

            groups.append(
                TopLevelGroup(
                    reference=top_reference,
                    # Keep the top-level heading text for output and reviewer context.
                    title=clause_title(top_node),
                    # Flatten the whole top-level subtree for the model's top-level decision.
                    text=flatten_clause(top_reference, top_node),
                    # Also keep the direct L2 clauses separately because they are tagged individually.
                    descendants=collect_descendants(top_reference, top_node),
                )
            )

    return tuple(groups)


def iter_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
    """Return top-level clause groups using the legacy helper name used by tests."""
    return build_top_level_groups(award)


def classification_payload_for_group(group: TopLevelGroup) -> dict[str, Any]:
    """Build the user-prompt payload for one top-level group."""
    return {
        "top_level_clause": {
            "reference": group.reference,
            "title": group.title,
            "text": group.text,
        },
        "direct_l2_clauses": [
            {
                "reference": descendant.reference,
                "title": descendant.title,
                "text": descendant.text,
            }
            for descendant in group.descendants
        ],
    }


def top_level_payload(group: TopLevelGroup) -> dict[str, Any]:
    """Return the classification payload using the legacy helper name."""
    return classification_payload_for_group(group)


def l1_body_text(group: TopLevelGroup) -> str:
    """Return top-level clause text without the heading line."""
    body_lines: list[str] = []

    # The flattened text includes the heading line, so inspect it line by line.
    for line in group.text.splitlines():
        # Split off the "reference:" label and keep only the human-readable clause text.
        _separator, _prefix, text = line.partition(":")
        normalized_text = text.strip()
        # Ignore the title line because it does not add substantive rule content.
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


# 5. Model classification


def build_messages(group: TopLevelGroup) -> list[dict[str, str]]:
    """Build the system and user messages for one model request."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        # Build the user prompt from the grouped clause data for this one model call.
        {
            "role": "user",
            "content": build_user_prompt(classification_payload_for_group(group)),
        },
    ]


def response_json_schema() -> dict[str, Any]:
    """Define the JSON schema the model must follow."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "top_level_clause": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "reference": {"type": "string"},
                    "title": {"type": "string"},
                    "payment_relevant": {"type": "boolean"},
                    "definition_relevant": {"type": "boolean"},
                    "requires_l2_classification": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "reference",
                    "title",
                    "payment_relevant",
                    "definition_relevant",
                    "requires_l2_classification",
                    "reason",
                ],
            },
            "classified_clauses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "reference": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(ALLOWED_TAGS)},
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["reference", "tags", "reason"],
                },
            },
        },
        "required": ["top_level_clause", "classified_clauses"],
    }


def parse_response_json(output_text: str) -> Mapping[str, Any]:
    """Parse the model's JSON text into a Python mapping."""
    return json.loads(output_text)


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
    # Read the model's top-level decision for this clause group.
    top = classification.get("top_level_clause")
    if top.get("reference") != group.reference:
        raise PaymentClauseClassifierError(
            f"Expected top-level reference {group.reference}, got {top.get('reference')}."
        )

    # Normalize the model booleans into plain Python values.
    payment_relevant = bool(top.get("payment_relevant"))
    definition_relevant = bool(top.get("definition_relevant"))
    requires_l2_classification = payment_relevant or definition_relevant

    # Store the top-level result in the output shape used by this script.
    top_result = {
        "title": str(top.get("title") or group.title),
        "payment_relevant": payment_relevant,
        "definition_relevant": definition_relevant,
        "requires_l2_classification": requires_l2_classification,
        "reason": str(top.get("reason") or ""),
    }

    # Index direct descendants by reference so returned clause tags can be matched back to source text.
    descendants_by_reference = {item.reference: item for item in group.descendants}
    direct_references = set(descendants_by_reference)
    # Read the list of clause-level classifications returned by the model.
    classified_raw = classification["classified_clauses"]

    if not payment_relevant and not definition_relevant and classified_raw:
        raise PaymentClauseClassifierError(
            f"Clause {group.reference} is not payment or definition relevant but returned classified clauses."
        )

    classified: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for item in classified_raw:
        # Take the clause reference exactly as the model returned it.
        returned_reference = item["reference"]
        # Map that reference back to the owning direct L2 clause used by downstream outputs.
        reference = map_to_direct_l2_reference(
            returned_reference,
            direct_references,
        )

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
            # Allow the model to classify the L1 clause itself when the real content lives on L1.
            reference = group.reference

        if reference is None:
            raise PaymentClauseClassifierError(
                f"Unknown classified clause reference: {returned_reference}"
            )

        if reference == group.reference:
            # Use the top-level flattened text when the classification belongs to the L1 clause itself.
            source_text = group.text
        else:
            # Otherwise attach the classification to the direct L2 clause text that was grouped for tagging.
            source_text = descendants_by_reference[reference].text

        # Keep the model's reason text so the output stays explainable to a reviewer.
        reason = str(item.get("reason") or "")
        if returned_reference != reference:
            # Record when a nested reference was folded back into its owning direct L2 clause.
            reason = (
                f"{reason} Returned nested reference {returned_reference}; "
                f"classified under {reference}."
            ).strip()

        if reference in classified:
            # Merge tags if the model mentioned the same direct clause more than once.
            classified[reference]["tags"] = unique_items(
                [*classified[reference]["tags"], *item["tags"]]
            )
            if reason and reason not in classified[reference]["reason"]:
                # Keep both reasons when they add new explanation.
                existing_reason = classified[reference]["reason"]
                classified[reference]["reason"] = f"{existing_reason} {reason}".strip()
            continue

        # Store the first result for this reference together with the exact source text it applies to.
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


def classify_group(
    group: TopLevelGroup,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    """Send one top-level group to the model and validate the result."""
    # Ask the model to classify this top-level clause and return strict JSON.
    response = client.responses.create(
        model=model,
        input=build_messages(group),
        text={
            "format": {
                "type": "json_schema",
                "name": "payment_clause_classification",
                "schema": response_json_schema(),
                "strict": True,
            }
        },
    )

    output_text = extract_response_text(response)
    if not output_text:
        raise PaymentClauseClassifierError(
            f"OpenAI response for clause {group.reference} did not include output text."
        )

    # Parse the JSON text and verify that the references make sense for this clause group.
    top_result, classified = validate_group_classification(
        group,
        parse_response_json(output_text),
    )
    apply_deterministic_tag_repairs(group, top_result, classified)
    return top_result, classified


# 6. Output writing


def classify_award(
    award_path: Path | str = DEFAULT_AWARD_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OrderedDict[str, Any]:
    """Classify one award file and write the JSON result to disk."""
    # Pick the explicit model first, then the environment override, then the hard-coded default.
    selected_model = model or os.getenv("PAYMENT_CLAUSE_CLASSIFIER_MODEL", DEFAULT_MODEL)

    if client is None:
        # Load credentials only when this function is creating its own API client.
        load_environment()
        client = OpenAI()

    source_path = Path(award_path)
    # Read the processed award JSON that will be classified.
    award = load_award(source_path)
    # Break the award into top-level groups so each model call handles one clause family.
    groups = build_top_level_groups(award)

    top_level_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()
    classified_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for group in groups:
        if not group.descendants and not has_substantive_l1_content(group):
            # Skip model use when the clause is only a heading with no real text to classify.
            top_result = title_only_top_level_result(group)
            descendant_results = OrderedDict()
        else:
            # Otherwise classify the group with the model and validate the returned references.
            top_result, descendant_results = classify_group(group, client, selected_model)

        # Save the top-level decision under the clause reference.
        top_level_clauses[group.reference] = top_result
        # Add any clause-level tags returned for this top-level group.
        classified_clauses.update(descendant_results)

    result: OrderedDict[str, Any] = OrderedDict()
    result["source_file"] = str(source_path)
    result["model"] = selected_model
    result["schema_version"] = SCHEMA_VERSION
    result["top_level_clauses"] = top_level_clauses
    result["classified_clauses"] = classified_clauses

    # Use the caller's output path if provided, otherwise build the standard project path.
    destination = Path(output_path) if output_path else output_path_for_award(source_path)
    # Serialize the result in a reviewer-friendly JSON format.
    output_json = json.dumps(result, indent=2, ensure_ascii=False)
    # Write the latest output and archive a timestamped copy.
    write_text_with_archive(destination, output_json)

    return result


# 7. Main orchestration


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the payment classifier script."""
    parser = argparse.ArgumentParser(
        description="Classify payment-relevant clauses in a processed award JSON file."
    )
    parser.add_argument(
        "award_path",
        nargs="?",
        default=str(DEFAULT_AWARD_PATH),
        help=(
            "Path to a processed full award JSON file, for example "
            "data/processed/1_fetch_award/MA000018.json."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the payment classification JSON output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to PAYMENT_CLAUSE_CLASSIFIER_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Run the classifier from the command line and print a short summary."""
    # Read the CLI inputs that control which award and model to use.
    args = parse_args()
    # Run the end-to-end classification workflow.
    result = classify_award(
        award_path=args.award_path,
        output_path=args.output_path,
        model=args.model,
    )
    # Recompute the destination path so the CLI summary prints the saved location.
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_award(args.award_path)
    )
    print(f"Payment classification saved to {destination}")
    print(
        f"Classified {len(result['top_level_clauses'])} top-level clauses and "
        f"{len(result['classified_clauses'])} descendant clauses."
    )


if __name__ == "__main__":
    main()
