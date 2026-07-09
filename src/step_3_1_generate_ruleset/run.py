"""Run step 3.1 ruleset generation."""

from __future__ import annotations

from typing import Any

from src.common.overtime_clause_classification import OvertimeInterpretationError

from .schema import DEFAULT_EXPERT_RUN_COUNT, EXPERT_A_LABEL, EXPERT_B_LABEL
from .step_1_load_inputs import (
    resolve_generation_inputs,
)
from .step_2_generate_expert_rules import (
    load_openai_client,
    request_structured_interpretation_run,
    resolve_models,
)
from .step_3_apply_deterministic_checks import validate_interpretation_rules
from .step_4_combine_expert_rules import combine_expert_rulesets
from .step_5_write_artifacts import (
    write_combination_artifact,
    write_expert_draft_artifact,
    write_final_ruleset_artifact,
)


def generate_ruleset_from_clause_classification(
    *,
    classification_path,
    output_path=None,
    classification_output_path=None,
    model: str | None = None,
    comparison_model: str | None = None,
    expert_run_count: int = DEFAULT_EXPERT_RUN_COUNT,
    client: Any | None = None,
    ruleset_key: str,
) -> str:
    """Run step 3.1 from an existing step 2.2 artifact."""
    if expert_run_count != DEFAULT_EXPERT_RUN_COUNT:
        raise OvertimeInterpretationError(
            "step 3.1 currently supports exactly two expert runs: expert A and expert B."
        )

    print(
        "Step 3.1: Loading step 2 inputs from "
        f"{classification_path}"
    )
    inputs = resolve_generation_inputs(
        classification_path=classification_path,
        classification_output_path=classification_output_path,
        output_path=output_path,
        ruleset_key=ruleset_key,
    )
    selected_model, selected_comparison_model = resolve_models(
        model=model,
        comparison_model=comparison_model,
    )
    active_client = client or load_openai_client()
    print(
        "Step 3.1: Drafting expert A and expert B with model "
        f"{selected_model}"
    )

    expert_a_output_text = request_structured_interpretation_run(
        client=active_client,
        model=selected_model,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        ruleset_key=inputs.ruleset_key,
    )
    expert_a_rules, expert_a_warnings = validate_interpretation_rules(
        expert_a_output_text,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        ruleset_key=inputs.ruleset_key,
    )
    expert_a_output_paths = write_expert_draft_artifact(
        base_markdown_path=inputs.destination,
        label=EXPERT_A_LABEL,
        source_path=inputs.source_path,
        clause_classification_path=inputs.clause_classification_path,
        rules=expert_a_rules,
        validation_warnings=expert_a_warnings,
    )

    expert_b_output_text = request_structured_interpretation_run(
        client=active_client,
        model=selected_model,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        ruleset_key=inputs.ruleset_key,
    )
    expert_b_rules, expert_b_warnings = validate_interpretation_rules(
        expert_b_output_text,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        ruleset_key=inputs.ruleset_key,
    )
    expert_b_output_paths = write_expert_draft_artifact(
        base_markdown_path=inputs.destination,
        label=EXPERT_B_LABEL,
        source_path=inputs.source_path,
        clause_classification_path=inputs.clause_classification_path,
        rules=expert_b_rules,
        validation_warnings=expert_b_warnings,
    )

    expert_output_paths = [expert_a_output_paths, expert_b_output_paths]

    print(
        "Step 3.1: Combining expert drafts with comparison model "
        f"{selected_comparison_model}"
    )
    merged_rules, comparison_metadata, validation_warnings = combine_expert_rulesets(
        client=active_client,
        model=selected_comparison_model,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        expert_a_rules=expert_a_rules,
        expert_b_rules=expert_b_rules,
        ruleset_key=inputs.ruleset_key,
    )
    write_combination_artifact(
        markdown_destination=inputs.destination,
        source_path=inputs.source_path,
        clause_classification_path=inputs.clause_classification_path,
        expert_output_paths=expert_output_paths,
        comparison_metadata=comparison_metadata,
        validation_warnings=validation_warnings,
        rules=merged_rules,
    )

    rendered_markdown = write_final_ruleset_artifact(
        json_destination=inputs.json_destination,
        markdown_destination=inputs.destination,
        source_path=inputs.source_path,
        clause_classification_path=inputs.clause_classification_path,
        rules=merged_rules,
        validation_warnings=validation_warnings,
        expert_output_paths=expert_output_paths,
        comparison_metadata=comparison_metadata,
    )
    print(f"Step 3.1: Wrote ruleset markdown to {inputs.destination}")
    print(f"Step 3.1: Wrote ruleset JSON to {inputs.json_destination}")
    return rendered_markdown
