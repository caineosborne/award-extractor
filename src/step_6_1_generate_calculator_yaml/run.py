"""Run step 6.1 calculator questionnaire and Python generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.output_paths import write_text_output

from .core import (
    CalculatorRulesYamlError,
    CalculatorYamlInputs,
    align_questionnaire_to_calculator_contract,
    award_title_from_award_json_path,
    normalize_response_data,
    summarized_rules,
    write_python_output,
)
from .llm import load_client, request_calculator_rules, selected_model


def _load_json_file(path: Path, file_label: str) -> dict[str, Any]:
    if not path.exists():
        raise CalculatorRulesYamlError(f"{file_label} was not found: {path}")

    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except json.JSONDecodeError as exc:
        raise CalculatorRulesYamlError(
            f"{file_label} is not valid JSON: {path}"
        ) from exc

    if not isinstance(loaded, dict):
        raise CalculatorRulesYamlError(f"{file_label} must be a JSON object: {path}")

    return loaded


def load_inputs(
    *,
    award_code: str,
    creation_json_path: Path | str,
    consequence_json_path: Path | str,
    penalties_json_path: Path | str,
    output_path: Path | str,
) -> CalculatorYamlInputs:
    """Load and validate the upstream step 3.2 JSON artifacts."""
    selected_creation_path = Path(creation_json_path)
    selected_consequence_path = Path(consequence_json_path)
    selected_penalties_path = Path(penalties_json_path)

    return CalculatorYamlInputs(
        award_code=award_code,
        creation_json_path=selected_creation_path,
        consequence_json_path=selected_consequence_path,
        penalties_json_path=selected_penalties_path,
        output_path=Path(output_path),
        award_title=award_title_from_award_json_path(
            selected_creation_path.parent / "1_2_award.json"
        ),
        creation_artifact=_load_json_file(
            selected_creation_path,
            "Step 3.2 overtime creation ruleset JSON",
        ),
        consequence_artifact=_load_json_file(
            selected_consequence_path,
            "Step 3.2 overtime consequence ruleset JSON",
        ),
        penalties_artifact=_load_json_file(
            selected_penalties_path,
            "Step 3.2 penalties ruleset JSON",
        ),
    )


def generate_calculator_rules_yaml(
    *,
    award_code: str,
    creation_json_path: Path | str,
    consequence_json_path: Path | str,
    penalties_json_path: Path | str,
    output_path: Path | str,
    client: Any | None = None,
    model: str | None = None,
) -> Path:
    """Run step 6.1 and write the calculator Python output."""
    print(f"Step 6.1: Loading step 3.2 reviewed JSON sources for {award_code}")
    inputs = load_inputs(
        award_code=award_code,
        creation_json_path=creation_json_path,
        consequence_json_path=consequence_json_path,
        penalties_json_path=penalties_json_path,
        output_path=output_path,
    )
    active_client = client or load_client()
    active_model = selected_model(model)
    print(f"Step 6.1: Deriving calculator Python rules with model {active_model}")

    response_data = request_calculator_rules(
        client=active_client,
        model=active_model,
        award_code=award_code,
        creation_json_path=inputs.creation_json_path,
        creation_rules=summarized_rules(inputs.creation_artifact),
        consequence_json_path=inputs.consequence_json_path,
        consequence_rules=summarized_rules(inputs.consequence_artifact),
        penalties_json_path=inputs.penalties_json_path,
        penalties_rules=summarized_rules(inputs.penalties_artifact),
    )
    response_data = align_questionnaire_to_calculator_contract(response_data)
    questionnaire_path = inputs.output_path.with_name(
        f"{inputs.output_path.stem}_questionnaire.json"
    )
    write_text_output(questionnaire_path, json.dumps(response_data, indent=2))

    normalized_data = normalize_response_data(
        response_data,
        award_code=award_code,
    )
    for warning in normalized_data.get("validation_warnings", []):
        print(f"Step 6.1 warning: {warning}")
    if inputs.award_title is not None:
        normalized_data["award_title"] = inputs.award_title
    write_python_output(inputs.output_path, normalized_data)
    print(f"Step 6.1: Wrote calculator Python rules to {inputs.output_path}")
    print(f"Step 6.1: Wrote calculator questionnaire JSON to {questionnaire_path}")
    return inputs.output_path
