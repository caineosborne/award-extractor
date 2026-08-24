"""Run step 3.2 ruleset review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.common.prompt_logging import configure_prompt_log
from .schema import (
    DEFAULT_INTER_CALL_DELAY_SECONDS,
    OvertimeInterpretationReviewArtifacts,
)
from .step_1_load_inputs import load_review_inputs
from .step_2_run_reviewer import (
    load_client,
    resolve_review_models,
    run_evaluator_review,
)
from .step_3_run_creator import run_creator_review
from .step_4_write_outputs import write_review_outputs


def _print_status(message: str) -> None:
    print(f"Step 3.2: {message}")


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
    active_status_callback = status_callback or _print_status
    classification_file = Path(classification_path)
    configure_prompt_log(
        classification_file.parent / f"{classification_file.parent.name}.log"
    )
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
    ) = resolve_review_models(
        evaluator_model=evaluator_model,
        creator_model=creator_model,
    )
    active_evaluator_client = evaluator_client or load_client()
    active_creator_client = creator_client or load_client()

    active_status_callback("Loading interpretation and step 2/3 classification sources")
    active_status_callback(f"Awaiting evaluator model: {selected_evaluator_model}")

    evaluator_feedback_data, evaluator_feedback_markdown = run_evaluator_review(
        inputs=inputs,
        evaluator_client=active_evaluator_client,
        evaluator_model=selected_evaluator_model,
        evaluator_max_output_tokens=selected_evaluator_max_output_tokens,
        status_callback=active_status_callback,
    )

    active_status_callback("Evaluator processed feedback")
    active_status_callback(f"Awaiting creator update model: {selected_creator_model}")

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
        status_callback=active_status_callback,
        inter_call_delay_seconds=inter_call_delay_seconds,
    )

    if last_validation_error and reviewed_rules_artifact is not None:
        active_status_callback(
            "Writing feedback and revised interpretation. "
            "Any creator validation failure has been recorded for manual review."
        )
    else:
        active_status_callback("Writing feedback, creator response, and revised interpretation")

    artifacts = write_review_outputs(
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

    active_status_callback(f"Wrote evaluator review to {artifacts.evaluator_feedback_path}")
    active_status_callback(f"Wrote creator response to {artifacts.creator_response_path}")
    active_status_callback(
        f"Wrote revised ruleset to {artifacts.revised_interpretation_path}"
    )
    active_status_callback("Review update complete")

    return artifacts
