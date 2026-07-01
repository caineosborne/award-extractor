"""LLM helpers for step 2.1 payment classification."""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any

from openai import OpenAI

from src.script_2_classify_payments import (
    DEFAULT_MODEL,
    classify_group,
    has_substantive_l1_content,
    load_environment,
    title_only_top_level_result,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 2.1 client."""
    load_environment()
    return OpenAI()


def selected_model(model: str | None) -> str:
    """Resolve the configured step 2.1 model."""
    return model or os.getenv("PAYMENT_CLAUSE_CLASSIFIER_MODEL", DEFAULT_MODEL)


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
