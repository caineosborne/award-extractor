"""Step 2.2 stage 3: classify shortlisted overtime-related clauses."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.overtime_clause_classification import (
    DEFAULT_MODEL,
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    classification_response_json_schema,
    select_overtime_creation_clauses,
    validate_overtime_clause_classifications,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)
from src.prompts.step_2_2_classify_overtime_clauses import (
    build_clause_classification_messages,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return a client."""
    from .step_1_load_inputs import load_environment

    load_environment()
    return OpenAI()


def model_name(selected_model: str | None) -> str:
    """Resolve the configured model for step 2.2."""
    return selected_model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)


def parse_response_json(output_text: str) -> dict[str, Any]:
    """Parse a JSON response body for the step 2.2 classifier."""
    try:
        data = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OvertimeInterpretationError(
            "Clause classification response was not valid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise OvertimeInterpretationError(
            "Clause classification response must be a JSON object."
        )

    return data


def classify_overtime_clauses(
    overtime_clauses: Mapping[str, Any],
    client: Any,
    model: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Ask the model to classify each shortlisted clause by overtime role."""
    config = overtime_ruleset_config(ruleset_key)
    response = client.responses.create(
        model=model,
        input=build_clause_classification_messages(overtime_clauses, ruleset_key),
        text={
            "format": {
                "type": "json_schema",
                "name": config.clause_classification_schema_name,
                "schema": classification_response_json_schema(ruleset_key),
                "strict": True,
            }
        },
    )

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeInterpretationError(
            "OpenAI classification response did not include output text."
        )

    return validate_overtime_clause_classifications(
        parse_response_json(output_text),
        overtime_clauses,
        ruleset_key,
    )
