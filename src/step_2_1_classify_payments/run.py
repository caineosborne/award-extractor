"""Run step 2.1 payment classification."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from src.script_2_classify_payments import DEFAULT_AWARD_PATH

from .deterministic import (
    build_result_artifact,
    resolve_classification_inputs,
    write_result,
)
from .llm import classify_groups, load_openai_client, selected_model


def classify_payments(
    award_path: str = str(DEFAULT_AWARD_PATH),
    output_path: str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> OrderedDict[str, Any]:
    """Run step 2.1 and write the payment classification artifact."""
    inputs = resolve_classification_inputs(
        award_path=award_path,
        output_path=output_path,
    )
    active_model = selected_model(model)
    active_client = client or load_openai_client()
    top_level_clauses, classified_clauses = classify_groups(
        groups=inputs.groups,
        client=active_client,
        model=active_model,
    )
    result = build_result_artifact(
        source_path=inputs.source_path,
        model=active_model,
        top_level_clauses=top_level_clauses,
        classified_clauses=classified_clauses,
    )
    write_result(inputs.destination, result)
    return result
