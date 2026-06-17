import argparse
import json
import os
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.payment_clause_classifier_prompt import (
    ALLOWED_TAGS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from src.output_paths import (
    FETCH_AWARD_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    timestamped_archive_path,
    write_text_with_archive,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AWARD_PATH = (
    PROJECT_ROOT / "data" / "processed" / FETCH_AWARD_DIR / "MA000018.json"
)
DEFAULT_MODEL = "gpt-5.4-mini"
SCHEMA_VERSION = "payment-classification-v2"
CONTENT_KEY = "_content"
PLACEHOLDER_PREFIX = "No Level"


class PaymentClauseClassifierError(RuntimeError):
    """Raised when the classifier cannot continue with the current award."""


@dataclass(frozen=True)
class ClauseItem:
    reference: str
    title: str
    text: str
    node: Mapping[str, Any]


@dataclass(frozen=True)
class TopLevelGroup:
    reference: str
    title: str
    text: str
    descendants: tuple[ClauseItem, ...]


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise PaymentClauseClassifierError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_award(award_path: Path | str = DEFAULT_AWARD_PATH) -> OrderedDict[str, Any]:
    path = Path(award_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def output_path_for_award(award_path: Path | str) -> Path:
    path = Path(award_path)
    return path_in_category(
        path,
        PAYMENT_CLAUSE_IDENTIFIER_DIR,
        f"{path.stem}_payment_classification.json",
    )


def timestamped_output_path(output_path: Path | str, timestamp: datetime | None = None) -> Path:
    return timestamped_archive_path(output_path, timestamp)


def child_nodes(mapping: Mapping[str, Any]):
    """Yield nested clause dictionaries and skip the text-only _content entry."""
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, Mapping):
            yield str(key), value


def is_placeholder_key(key: str) -> bool:
    # The award JSON sometimes inserts "No Level ..." wrappers that are not real clauses.
    return key.startswith(PLACEHOLDER_PREFIX)


def is_lettered_key(key: str) -> bool:
    return len(key) <= 3 and key.isalpha()


def format_child_reference(parent_reference: str, child_key: str) -> str:
    # Lettered children are stored as "a", "b", etc. but cited as "24.1(a)".
    if is_lettered_key(child_key):
        return f"{parent_reference}({child_key})"
    return child_key


def format_content_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    return json.dumps(item, ensure_ascii=False)


def content_lines(node: Mapping[str, Any]) -> list[str]:
    content = node.get(CONTENT_KEY, [])
    if isinstance(content, list):
        return [format_content_item(item) for item in content if format_content_item(item).strip()]
    if content:
        formatted = format_content_item(content)
        return [formatted] if formatted.strip() else []
    return []


def clause_title(node: Mapping[str, Any]) -> str:
    lines = content_lines(node)
    return lines[0] if lines else ""


def flatten_clause(reference: str, node: Mapping[str, Any]) -> str:
    """Convert a clause subtree into labelled text for the model prompt."""
    lines: list[str] = []

    def walk(current_reference: str, current_node: Mapping[str, Any]) -> None:
        for line in content_lines(current_node):
            lines.append(f"{current_reference}: {line}")

        for child_key, child_node in child_nodes(current_node):
            if is_placeholder_key(child_key):
                walk(current_reference, child_node)
            else:
                walk(format_child_reference(current_reference, child_key), child_node)

    walk(reference, node)
    return "\n".join(lines)


def collect_descendants(parent_reference: str, node: Mapping[str, Any]) -> tuple[ClauseItem, ...]:
    """Collect direct L2 clauses below a top-level clause.

    Each returned item contains the full flattened subtree for that L2 clause, so lower-level
    subclauses are considered under the L2 tags without being returned as separate classifications.
    """
    descendants: list[ClauseItem] = []

    def collect_direct(current_reference: str, current_node: Mapping[str, Any]) -> None:
        for child_key, child_node in child_nodes(current_node):
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


def iter_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
    """Build one model request group for each top-level clause under each award Part."""
    groups: list[TopLevelGroup] = []
    for _part_heading, part_node in child_nodes(award):
        for top_reference, top_node in child_nodes(part_node):
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


def top_level_payload(group: TopLevelGroup) -> dict[str, Any]:
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


def build_messages(group: TopLevelGroup) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(top_level_payload(group))},
    ]


def response_json_schema() -> dict[str, Any]:
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


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    text_parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for content_item in content:
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text)

    return "\n".join(text_parts)


def parse_response_json(output_text: str) -> Mapping[str, Any]:
    return json.loads(output_text)


def unique_items(value: list[str]) -> list[str]:
    """Preserve model order while removing duplicates."""
    unique: list[str] = []
    for item in value:
        if item not in unique:
            unique.append(item)
    return unique


def validate_group_classification(
    group: TopLevelGroup,
    classification: Mapping[str, Any],
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    """Attach model output back to the clause text it classified.

    The OpenAI JSON schema handles shape and tag validation. This function only
    checks references that are specific to the current group and normalizes duplicate values.
    """
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
    classified_raw = classification["classified_clauses"]
    if not payment_relevant and not definition_relevant and classified_raw:
        raise PaymentClauseClassifierError(
            f"Clause {group.reference} is not payment or definition relevant but returned classified clauses."
        )

    classified: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for item in classified_raw:
        reference = item["reference"]
        if reference not in descendants_by_reference:
            raise PaymentClauseClassifierError(f"Unknown classified clause reference: {reference}")

        classified[reference] = {
            "text": descendants_by_reference[reference].text,
            "tags": unique_items(item["tags"]),
            "reason": str(item.get("reason") or ""),
        }

    return top_result, classified


def classify_group(
    group: TopLevelGroup,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
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

    return validate_group_classification(group, parse_response_json(output_text))


def classify_award(
    award_path: Path | str = DEFAULT_AWARD_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OrderedDict[str, Any]:
    selected_model = model or os.getenv("PAYMENT_CLAUSE_CLASSIFIER_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(award_path)
    award = load_award(source_path)
    # Each group is one top-level clause plus its direct L2 clauses. The model classifies
    # the top-level clause first, then returns any payment- or definition-relevant L2 clauses.
    groups = iter_top_level_groups(award)

    top_level_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()
    classified_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for group in groups:
        top_result, descendant_results = classify_group(group, client, selected_model)
        top_level_clauses[group.reference] = top_result
        classified_clauses.update(descendant_results)

    result: OrderedDict[str, Any] = OrderedDict()
    result["source_file"] = str(source_path)
    result["model"] = selected_model
    result["schema_version"] = SCHEMA_VERSION
    result["top_level_clauses"] = top_level_clauses
    result["classified_clauses"] = classified_clauses

    destination = Path(output_path) if output_path else output_path_for_award(source_path)
    output_json = json.dumps(result, indent=2, ensure_ascii=False)
    write_text_with_archive(destination, output_json)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify payment-relevant clauses in a processed award JSON file."
    )
    parser.add_argument(
        "award_path",
        nargs="?",
        default=str(DEFAULT_AWARD_PATH),
        help="Path to a processed full award JSON file, for example data/processed/MA000018.json.",
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
    args = parse_args()
    result = classify_award(
        award_path=args.award_path,
        output_path=args.output_path,
        model=args.model,
    )
    destination = Path(args.output_path) if args.output_path else output_path_for_award(args.award_path)
    print(f"Payment classification saved to {destination}")
    print(
        f"Classified {len(result['top_level_clauses'])} top-level clauses and "
        f"{len(result['classified_clauses'])} descendant clauses."
    )


if __name__ == "__main__":
    main()
