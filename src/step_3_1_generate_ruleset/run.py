"""Run step 3.1 ruleset generation."""

from __future__ import annotations

from typing import Any

from .core import DEFAULT_EXPERT_RUN_COUNT, EXPERT_RUN_LABELS, OvertimeInterpretationError, deduplicate_preserving_order
from .deterministic import (
    resolve_generation_inputs,
    write_expert_draft,
    write_merged_comparison,
    write_merged_ruleset,
)
from .llm import (
    draft_additional_expert,
    draft_expert_a,
    draft_expert_b,
    load_openai_client,
    merge_expert_drafts,
    selected_models,
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
    if expert_run_count < 1:
        raise OvertimeInterpretationError("expert_run_count must be at least 1.")

    inputs = resolve_generation_inputs(
        classification_path=classification_path,
        classification_output_path=classification_output_path,
        output_path=output_path,
        ruleset_key=ruleset_key,
    )
    selected_model, selected_comparison_model = selected_models(
        model=model,
        comparison_model=comparison_model,
    )
    active_client = client or load_openai_client()

    effective_expert_run_count = min(expert_run_count, len(EXPERT_RUN_LABELS))
    expert_rulesets: list[list[Any]] = []
    expert_validation_warnings: list[list[str]] = []
    expert_output_paths: list[dict[str, str]] = []

    expert_a_rules, expert_a_warnings = draft_expert_a(
        client=active_client,
        model=selected_model,
        source_path=inputs.source_path,
        overtime_creation_clauses=inputs.overtime_creation_clauses,
        ruleset_key=inputs.ruleset_key,
    )
    expert_rulesets.append(expert_a_rules)
    expert_validation_warnings.append(expert_a_warnings)

    if effective_expert_run_count > 1:
        expert_output_paths.append(
            write_expert_draft(
                base_markdown_path=inputs.destination,
                label=EXPERT_RUN_LABELS[0],
                source_path=inputs.source_path,
                clause_classification_path=inputs.clause_classification_path,
                rules=expert_a_rules,
                validation_warnings=expert_a_warnings,
            )
        )

        expert_b_rules, expert_b_warnings = draft_expert_b(
            client=active_client,
            model=selected_model,
            source_path=inputs.source_path,
            overtime_creation_clauses=inputs.overtime_creation_clauses,
            ruleset_key=inputs.ruleset_key,
        )
        expert_rulesets.append(expert_b_rules)
        expert_validation_warnings.append(expert_b_warnings)
        expert_output_paths.append(
            write_expert_draft(
                base_markdown_path=inputs.destination,
                label=EXPERT_RUN_LABELS[1],
                source_path=inputs.source_path,
                clause_classification_path=inputs.clause_classification_path,
                rules=expert_b_rules,
                validation_warnings=expert_b_warnings,
            )
        )

    for run_index in range(2, effective_expert_run_count):
        expert_rules, expert_warnings = draft_additional_expert(
            client=active_client,
            model=selected_model,
            source_path=inputs.source_path,
            overtime_creation_clauses=inputs.overtime_creation_clauses,
            ruleset_key=inputs.ruleset_key,
        )
        expert_rulesets.append(expert_rules)
        expert_validation_warnings.append(expert_warnings)
        expert_output_paths.append(
            write_expert_draft(
                base_markdown_path=inputs.destination,
                label=EXPERT_RUN_LABELS[run_index],
                source_path=inputs.source_path,
                clause_classification_path=inputs.clause_classification_path,
                rules=expert_rules,
                validation_warnings=expert_warnings,
            )
        )

    if effective_expert_run_count == 1:
        merged_rules = expert_rulesets[0]
        validation_warnings = expert_validation_warnings[0]
        comparison_metadata: dict[str, Any] = {}
    else:
        merged_rules, comparison_metadata, comparison_validation_warnings = (
            merge_expert_drafts(
                client=active_client,
                model=selected_comparison_model,
                source_path=inputs.source_path,
                overtime_creation_clauses=inputs.overtime_creation_clauses,
                run_a_rules=expert_rulesets[0],
                run_b_rules=expert_rulesets[1],
                ruleset_key=inputs.ruleset_key,
            )
        )
        validation_warnings = deduplicate_preserving_order(
            [
                *expert_validation_warnings[0],
                *expert_validation_warnings[1],
                *comparison_validation_warnings,
            ]
        )
        write_merged_comparison(
            markdown_destination=inputs.destination,
            source_path=inputs.source_path,
            clause_classification_path=inputs.clause_classification_path,
            expert_output_paths=expert_output_paths,
            comparison_metadata=comparison_metadata,
            validation_warnings=validation_warnings,
            rules=merged_rules,
        )

    return write_merged_ruleset(
        json_destination=inputs.json_destination,
        markdown_destination=inputs.destination,
        source_path=inputs.source_path,
        clause_classification_path=inputs.clause_classification_path,
        rules=merged_rules,
        validation_warnings=validation_warnings,
        expert_output_paths=expert_output_paths,
        comparison_metadata=comparison_metadata,
    )
