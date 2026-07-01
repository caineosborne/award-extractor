"""Run step 3.2 ruleset review."""

from __future__ import annotations

from typing import Any

from src.prompts.overtime_interpretation_review import (
    build_review_creator_messages,
    build_review_evaluator_messages,
)

from .core import DEFAULT_INTER_CALL_DELAY_SECONDS, OvertimeInterpretationReviewArtifacts
from .deterministic import load_review_inputs, write_review_outputs
from .llm import (
    load_client,
    request_creator_revision,
    request_evaluator_feedback,
    selected_review_models,
)


def run_evaluator_review(
    *,
    inputs,
    evaluator_client: Any,
    evaluator_model: str,
    evaluator_max_output_tokens: int,
    status_callback=None,
) -> tuple[dict[str, Any], str]:
    """Run the evaluator review step for step 3.2."""
    evaluator_messages = build_review_evaluator_messages(
        interpretation_path=inputs.selected_interpretation_path,
        original_rules_artifact=inputs.original_rules_artifact,
        interpretation_markdown=inputs.interpretation_markdown,
        classification_path=inputs.selected_classification_path,
        payment_classification=inputs.classification_data,
        overtime_clause_classification_path=inputs.selected_overtime_clause_classification_path,
        overtime_clause_classification=inputs.overtime_clause_classification,
        ruleset_key=inputs.selected_ruleset_key,
    )
    return request_evaluator_feedback(
        evaluator_client=evaluator_client,
        evaluator_model=evaluator_model,
        evaluator_max_output_tokens=evaluator_max_output_tokens,
        evaluator_messages=evaluator_messages,
        original_rules=inputs.original_rules_artifact["rules"],
        status_callback=status_callback,
        ruleset_key=inputs.selected_ruleset_key,
    )


def run_creator_review(
    *,
    inputs,
    evaluator_feedback_data: dict[str, Any],
    evaluator_feedback_markdown: str,
    creator_client: Any,
    creator_model: str,
    creator_max_output_tokens: int,
    status_callback=None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    """Run the creator revision step for step 3.2."""
    creator_messages = build_review_creator_messages(
        interpretation_path=inputs.selected_interpretation_path,
        original_rules_artifact=inputs.original_rules_artifact,
        interpretation_markdown=inputs.interpretation_markdown,
        classification_path=inputs.selected_classification_path,
        payment_classification=inputs.classification_data,
        overtime_clause_classification_path=inputs.selected_overtime_clause_classification_path,
        overtime_clause_classification=inputs.overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        ruleset_key=inputs.selected_ruleset_key,
    )
    return request_creator_revision(
        creator_client=creator_client,
        creator_model=creator_model,
        creator_max_output_tokens=creator_max_output_tokens,
        creator_messages=creator_messages,
        original_rules=inputs.original_rules_artifact["rules"],
        original_rendered_markdown=inputs.interpretation_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        status_callback=status_callback,
        inter_call_delay_seconds=inter_call_delay_seconds,
    )


def recreate_revised_ruleset(
    *,
    inputs,
    evaluator_feedback_data: dict[str, Any],
    evaluator_feedback_markdown: str,
    creator_response_data: dict[str, Any],
    creator_response_markdown: str,
    revised_interpretation_markdown: str,
    reviewed_rules_artifact: dict[str, Any],
    feedback_output_path=None,
    creator_response_output_path=None,
    revised_output_path=None,
) -> OvertimeInterpretationReviewArtifacts:
    """Write the final revised ruleset artifacts for step 3.2."""
    return write_review_outputs(
        inputs=inputs,
        evaluator_feedback_data=evaluator_feedback_data,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_response_data=creator_response_data,
        creator_response_markdown=creator_response_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
        reviewed_rules_artifact=reviewed_rules_artifact,
        feedback_output_path=feedback_output_path,
        creator_response_output_path=creator_response_output_path,
        revised_output_path=revised_output_path,
    )


def review_ruleset(
    *,
    interpretation_path,
    classification_path,
    overtime_clause_classification_path=None,
    feedback_output_path=None,
    creator_response_output_path=None,
    revised_output_path=None,
    evaluator_model: str | None = None,
    creator_model: str | None = None,
    evaluator_client: Any | None = None,
    creator_client: Any | None = None,
    status_callback=None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
    ruleset_key: str | None = None,
) -> OvertimeInterpretationReviewArtifacts:
    """Run step 3.2 and return the written artifact paths."""
    inputs = load_review_inputs(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        ruleset_key=ruleset_key,
    )
    (
        selected_evaluator_model,
        selected_creator_model,
        selected_evaluator_max_output_tokens,
        selected_creator_max_output_tokens,
    ) = selected_review_models(
        evaluator_model=evaluator_model,
        creator_model=creator_model,
    )
    active_evaluator_client = evaluator_client or load_client()
    active_creator_client = creator_client or load_client()

    if status_callback:
        status_callback("Loading interpretation and step 2/3 classification sources")
        status_callback(f"Awaiting evaluator model: {selected_evaluator_model}")

    evaluator_feedback_data, evaluator_feedback_markdown = run_evaluator_review(
        inputs=inputs,
        evaluator_client=active_evaluator_client,
        evaluator_model=selected_evaluator_model,
        evaluator_max_output_tokens=selected_evaluator_max_output_tokens,
        status_callback=status_callback,
    )

    if status_callback:
        status_callback("Evaluator processed feedback")
        status_callback(f"Awaiting creator update model: {selected_creator_model}")

    (
        creator_response_data,
        reviewed_rules_artifact,
        creator_response_markdown,
        revised_interpretation_markdown,
        last_validation_error,
    ) = run_creator_review(
        inputs=inputs,
        evaluator_feedback_data=evaluator_feedback_data,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_client=active_creator_client,
        creator_model=selected_creator_model,
        creator_max_output_tokens=selected_creator_max_output_tokens,
        status_callback=status_callback,
        inter_call_delay_seconds=inter_call_delay_seconds,
    )

    if status_callback:
        if last_validation_error and reviewed_rules_artifact is not None:
            status_callback(
                "Writing feedback and revised interpretation. "
                "Any creator validation failure has been recorded for manual review."
            )
        else:
            status_callback("Writing feedback, creator response, and revised interpretation")

    artifacts = recreate_revised_ruleset(
        inputs=inputs,
        evaluator_feedback_data=evaluator_feedback_data,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_response_data=creator_response_data,
        creator_response_markdown=creator_response_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
        reviewed_rules_artifact=reviewed_rules_artifact,
        feedback_output_path=feedback_output_path,
        creator_response_output_path=creator_response_output_path,
        revised_output_path=revised_output_path,
    )

    if status_callback:
        status_callback("Review update complete")

    return artifacts
