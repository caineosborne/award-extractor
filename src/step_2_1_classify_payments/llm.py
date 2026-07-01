"""LLM helpers for step 2.1 payment classification."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Mapping

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.prompts.payment_clause_classification import ALLOWED_TAGS, build_messages
from src.step_2_1_classify_payments.deterministic import (
    apply_deterministic_tag_repairs,
    has_substantive_l1_content,
    title_only_top_level_result,
    unique_items,
    direct_l2_reference_for,
    map_relative_reference_to_direct_l2,
)
from src.step_2_1_classify_payments.schema import (
    DEFAULT_MODEL,
    PROJECT_ROOT,
    PaymentClauseClassifierError,
    TopLevelGroup,
)


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load environment variables and require an OpenAI API key."""
    from dotenv import load_dotenv

    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise PaymentClauseClassifierError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 2.1 client."""
    load_environment()
    return OpenAI()


def selected_model(model: str | None) -> str:
    """Resolve the configured step 2.1 model."""
    return model or os.getenv("PAYMENT_CLAUSE_CLASSIFIER_MODEL", DEFAULT_MODEL)


def parse_response_json(output_text: str) -> Mapping[str, Any]:
    """Parse the model's JSON text into a Python mapping."""
    return json.loads(output_text)


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
        reference = direct_l2_reference_for(returned_reference, direct_references)

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


def classify_group(
    group: TopLevelGroup,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], OrderedDict[str, dict[str, Any]]]:
    """Send one top-level group to the model and validate the result."""
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

    top_result, classified = validate_group_classification(
        group,
        parse_response_json(output_text),
    )
    apply_deterministic_tag_repairs(group, top_result, classified)
    return top_result, classified


def classify_groups(
    *,
    groups: tuple[Any, ...],
    client: Any,
    model: str,
) -> tuple[OrderedDict[str, dict[str, Any]], OrderedDict[str, dict[str, Any]]]:
    """Classify each top-level group and collect the combined results."""
    top_level_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()
    classified_clauses: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for group in groups:
        if not group.descendants and not has_substantive_l1_content(group):
            top_result = title_only_top_level_result(group)
            descendant_results = OrderedDict()
        else:
            top_result, descendant_results = classify_group(group, client, model)

        top_level_clauses[group.reference] = top_result
        classified_clauses.update(descendant_results)

    return top_level_clauses, classified_clauses
