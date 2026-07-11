"""LLM helpers for step 6.1 calculator Python generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.pipeline_runtime import build_openai_client, load_openai_environment
from src.common.prompt_logging import log_llm_error, log_llm_prompt, log_llm_response
from src.prompts.step_6_1_generate_calculator_yaml import build_messages

from .core import (
    DEFAULT_MODEL,
    CalculatorRulesYamlError,
    calculator_rules_response_json_schema,
)


def load_environment(env_path: Path | str = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load and validate the OpenAI environment used by step 6.1."""
    load_openai_environment(env_path=env_path, error_type=CalculatorRulesYamlError)


def load_client() -> OpenAI:
    """Load the OpenAI client for step 6.1."""
    load_environment()
    return build_openai_client()


def selected_model(model: str | None) -> str:
    """Resolve the configured model for step 6.1."""
    return model or os.getenv("CALCULATOR_RULES_MODEL", DEFAULT_MODEL)


def request_calculator_rules(
    *,
    client: Any,
    model: str,
    award_code: str,
    creation_json_path: Path,
    creation_rules: list[dict[str, Any]],
    consequence_json_path: Path,
    consequence_rules: list[dict[str, Any]],
    penalties_json_path: Path,
    penalties_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Request the structured questionnaire answers from the model."""
    messages = build_messages(
        award_code=award_code,
        creation_json_path=creation_json_path,
        creation_rules=creation_rules,
        consequence_json_path=consequence_json_path,
        consequence_rules=consequence_rules,
        penalties_json_path=penalties_json_path,
        penalties_rules=penalties_rules,
    )
    log_llm_prompt(f"6.1 Calculator Rules Questionnaire - {award_code}", messages)
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "medium"},
            max_output_tokens=16000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "calculator_rules_questionnaire",
                    "schema": calculator_rules_response_json_schema(),
                    "strict": True,
                }
            },
        )
    except Exception as exc:
        log_llm_error(f"6.1 Calculator Rules Questionnaire Error - {award_code}", exc)
        raise CalculatorRulesYamlError(
            f"OpenAI calculator questionnaire request failed: {exc}"
        ) from exc

    output_text = extract_response_text(response)
    log_llm_response(
        f"6.1 Calculator Rules Questionnaire Response - {award_code}",
        response,
        output_text,
    )
    if not output_text:
        raise CalculatorRulesYamlError("OpenAI response did not include output text.")

    try:
        loaded = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise CalculatorRulesYamlError(
            f"Step 6.1 model output was not valid JSON: {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise CalculatorRulesYamlError("Step 6.1 model output must be a JSON object.")

    return loaded
