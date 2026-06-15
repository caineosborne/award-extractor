import argparse
import json
import os
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.payment_clause_classifier_prompt import (
    ALLOWED_TAGS,
    PAYMENT_EFFECTS,
    SYSTEM_PROMPT,
    build_user_prompt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AWARD_PATH = PROJECT_ROOT / "data" / "processed" / "MA000018.json"
DEFAULT_MODEL = "gpt-5.4-mini"
SCHEMA_VERSION = "payment-classification-v1"
CONTENT_KEY = "_content"
PLACEHOLDER_PREFIX = "No Level"


class PaymentClauseClassifierError(RuntimeError):
    """Base exception for payment clause classifier failures."""


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
    if not path.exists():
        raise PaymentClauseClassifierError(f"Award JSON not found: {path}")

    try:
        with path.open(encoding="utf-8") as award_file:
            award = json.load(award_file, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as exc:
        raise PaymentClauseClassifierError(f"Award JSON is not valid JSON: {path}") from exc

    if not isinstance(award, OrderedDict):
        raise PaymentClauseClassifierError(f"Award JSON must contain an object: {path}")

    return award


def output_path_for_award(award_path: Path | str) -> Path:
    path = Path(award_path)
    return path.with_name(f"{path.stem}_payment_classification.json")


def child_nodes(mapping: Mapping[str, Any]):
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, Mapping):
            yield str(key), value


def is_placeholder_key(key: str) -> bool:
    return key.startswith(PLACEHOLDER_PREFIX)


def is_lettered_key(key: str) -> bool:
    return len(key) <= 3 and key.isalpha()


def format_child_reference(parent_reference: str, child_key: str) -> str:
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
    descendants: list[ClauseItem] = []

    def walk(current_reference: str, current_node: Mapping[str, Any]) -> None:
        for child_key, child_node in child_nodes(current_node):
            if is_placeholder_key(child_key):
                walk(current_reference, child_node)
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
            walk(child_reference, child_node)

    walk(parent_reference, node)
    return tuple(descendants)


def iter_top_level_groups(award: Mapping[str, Any]) -> tuple[TopLevelGroup, ...]:
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
        "descendants": [
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
                    "payment_effects": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(PAYMENT_EFFECTS)},
                    },
                    "requires_descendant_classification": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "reference",
                    "title",
                    "payment_effects",
                    "requires_descendant_classification",
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
                        "payment_effects": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(PAYMENT_EFFECTS)},
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["reference", "tags", "payment_effects", "reason"],
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
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise PaymentClauseClassifierError("OpenAI response was not valid JSON.") from exc

    if not isinstance(parsed, Mapping):
        raise PaymentClauseClassifierError("OpenAI response JSON must be an object.")
    return parsed


def normalize_effects(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PaymentClauseClassifierError(f"{context} payment_effects must be a non-empty array.")

    effects: list[str] = []
    for item in value:
        if item not in PAYMENT_EFFECTS:
            raise PaymentClauseClassifierError(f"{context} has invalid payment effect: {item}")
        if item not in effects:
            effects.append(item)

    if "none" in effects and len(effects) > 1:
        effects = [effect for effect in effects if effect != "none"]
    return effects


def normalize_tags(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PaymentClauseClassifierError(f"{context} tags must be a non-empty array.")

    tags: list[str] = []
    for item in value:
        if item not in ALLOWED_TAGS:
            raise PaymentClauseClassifierError(f"{context} has invalid tag: {item}")
        if item not in tags:
            tags.append(item)
    return tags


def validate_group_classification(
    group: TopLevelGroup,
    classification: Mapping[str, Any],
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    top = classification.get("top_level_clause")
    if not isinstance(top, Mapping):
        raise PaymentClauseClassifierError("OpenAI response missing top_level_clause object.")
    if top.get("reference") != group.reference:
        raise PaymentClauseClassifierError(
            f"Expected top-level reference {group.reference}, got {top.get('reference')}."
        )

    top_effects = normalize_effects(top.get("payment_effects"), f"Clause {group.reference}")
    requires_descendants = bool(top.get("requires_descendant_classification"))
    if top_effects == ["none"]:
        requires_descendants = False

    top_result = {
        "title": str(top.get("title") or group.title),
        "payment_effects": top_effects,
        "requires_descendant_classification": requires_descendants,
        "reason": str(top.get("reason") or ""),
    }

    descendants_by_reference = {item.reference: item for item in group.descendants}
    classified_raw = classification.get("classified_clauses")
    if not isinstance(classified_raw, list):
        raise PaymentClauseClassifierError("classified_clauses must be an array.")
    if top_effects == ["none"] and classified_raw:
        raise PaymentClauseClassifierError(
            f"Clause {group.reference} has no payment effects but returned classified clauses."
        )

    classified: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for item in classified_raw:
        if not isinstance(item, Mapping):
            raise PaymentClauseClassifierError("Each classified clause must be an object.")
        reference = item.get("reference")
        if not isinstance(reference, str) or reference not in descendants_by_reference:
            raise PaymentClauseClassifierError(f"Unknown classified clause reference: {reference}")

        classified[reference] = {
            "text": descendants_by_reference[reference].text,
            "tags": normalize_tags(item.get("tags"), f"Clause {reference}"),
            "payment_effects": normalize_effects(item.get("payment_effects"), f"Clause {reference}"),
            "reason": str(item.get("reason") or ""),
        }

    return top_result, classified


def classify_group(
    group: TopLevelGroup,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    try:
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
    except Exception as exc:
        raise PaymentClauseClassifierError(
            f"OpenAI request failed for clause {group.reference}."
        ) from exc

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
    groups = iter_top_level_groups(award)
    if not groups:
        raise PaymentClauseClassifierError(f"No top-level clauses found in award JSON: {source_path}")

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
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
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
