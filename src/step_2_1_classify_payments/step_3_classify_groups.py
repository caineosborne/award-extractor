"""Step 2.1 stage 3: classify clause groups with the LLM."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Mapping

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.prompts.step_2_1_classify_payments import (
    PAYMENT_CLASSIFICATION_ALLOWED_TAGS,
    build_messages,
)

from .step_4_validate_classification import (
    has_substantive_l1_content,
    title_only_top_level_result,
    validate_group_classification,
)
from .step_5_apply_repairs import apply_deterministic_tag_repairs
from .schema import DEFAULT_MODEL, PROJECT_ROOT, PaymentClauseClassifierError, TopLevelGroup


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
                            "items": {
                                "type": "string",
                                "enum": list(PAYMENT_CLASSIFICATION_ALLOWED_TAGS),
                            },
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["reference", "tags", "reason"],
                },
            },
        },
        "required": ["top_level_clause", "classified_clauses"],
    }


def classify_group(
    group: TopLevelGroup,
    client: Any,
    model: str,
) -> Mapping[str, Any]:
    """Send one top-level group to the model and parse the result."""
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

    return parse_response_json(output_text)


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
            classification = classify_group(group, client, model)
            top_result, descendant_results = validate_group_classification(
                group,
                classification,
            )
            apply_deterministic_tag_repairs(group, top_result, descendant_results)

        top_level_clauses[group.reference] = top_result
        classified_clauses.update(descendant_results)

    return top_level_clauses, classified_clauses
