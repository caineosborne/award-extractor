import argparse
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    creator_response_path_for_interpretation,
    default_classification_path_for_award,
    default_interpretation_path_for_award,
    evaluator_feedback_path_for_interpretation,
    resolve_classification_path,
    resolve_interpretation_path,
    resolve_overtime_clause_classification_path,
    revised_output_path_for_interpretation,
)
from src.common.model_call_budget import log_model_call_budget
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_io import load_json_object, load_text_file as load_text_document
from src.common.pipeline_runtime import (
    build_openrouter_client as create_openrouter_client,
    load_openai_environment as require_openai_environment,
    load_openrouter_api_key as require_openrouter_api_key,
)
from src.script_2_classify_payments import extract_response_text
from src.script_3_interpret_overtime import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_MODEL as DEFAULT_CREATOR_MODEL,
    load_classification,
)
from src.script_3b_shared_prompts import (
    build_full_evaluator_review_prompt,
    build_minimal_creator_revision_prompt,
    build_relevant_clause_excerpt_markdown,
    build_script_3_creator_prompt_context,
    evaluation_system_prompt,
)


# 1. Imports / constants

DEFAULT_INTERPRETATION_PATH = default_interpretation_path_for_award("MA000018")
EVALUATOR_MODEL = "anthropic/claude-sonnet-4.6"
CREATOR_RESPONSE_PATTERN = re.compile(
    r"<creator_response>\s*(?P<creator_response>.*?)\s*</creator_response>\s*"
    r"<revised_interpretation>\s*(?P<revised_interpretation>.*?)\s*</revised_interpretation>",
    re.DOTALL,
)
DEFAULT_INTER_CALL_DELAY_SECONDS = 30.0


class OvertimeInterpretationReviewError(RuntimeError):
    """Base exception for overtime interpretation review failures."""


# 2. Data structures


@dataclass(frozen=True)
class OvertimeInterpretationReviewArtifacts:
    """Store the output paths and text produced by the step-3B review workflow."""

    evaluator_feedback_path: Path
    creator_response_path: Path
    revised_interpretation_path: Path
    evaluator_feedback_markdown: str
    creator_response_markdown: str
    revised_interpretation_markdown: str


# 3. Environment / file helpers


def extract_chat_response_text(response: Any) -> str:
    """Extract plain text from a chat-completions style response object."""
    choices = getattr(response, "choices", None)
    if not choices:
        return ""

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []

        for content_item in content:
            # OpenRouter content blocks may be dicts or SDK objects, so handle both shapes.
            if isinstance(content_item, Mapping):
                text = content_item.get("text")
            else:
                text = getattr(content_item, "text", None)

            # Keep only non-empty text blocks when assembling the response body.
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

        return "\n".join(text_parts)

    return ""


def extract_chat_completion_text(response: Any) -> str:
    """Return chat response text using the legacy helper name."""
    return extract_chat_response_text(response)


def load_openrouter_api_key(env_path: Path | str = PROJECT_ROOT / ".env") -> str:
    """Load the OpenRouter API key used for evaluator calls."""
    return require_openrouter_api_key(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def load_openai_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load the OpenAI environment used for creator calls."""
    require_openai_environment(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def build_openrouter_client(api_key: str) -> OpenAI:
    """Build the OpenRouter-backed client used by the evaluator model."""
    return create_openrouter_client(api_key)


def load_text_file(path: Path | str, description: str) -> str:
    """Load a required text artifact for the review workflow."""
    return load_text_document(
        path,
        description,
        error_type=OvertimeInterpretationReviewError,
    )


def load_json_file(path: Path | str, description: str) -> dict[str, Any]:
    """Load a required JSON artifact for the review workflow."""
    return load_json_object(
        path,
        description,
        error_type=OvertimeInterpretationReviewError,
    )


def load_review_source_artifacts(
    interpretation_path: Path | str,
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> tuple[Path, Path, Path, str, dict[str, Any], dict[str, Any]]:
    """Load and validate all source artifacts needed for the step-3B review."""
    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    selected_overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        selected_classification_path,
        overtime_clause_classification_path,
    )

    # Load the interpretation markdown that the evaluator will review.
    interpretation_markdown = load_text_file(
        selected_interpretation_path,
        "Overtime interpretation markdown",
    )
    # Load the payment-classification JSON from step 2.
    classification_data = load_classification(selected_classification_path)
    classified_clauses = classification_data.get("classified_clauses")
    if not classified_clauses:
        raise OvertimeInterpretationReviewError(
            f"No classified clauses found in: {selected_classification_path}"
        )

    # Load the intermediate clause-classification JSON from step 3.
    overtime_clause_classification = load_json_file(
        selected_overtime_clause_classification_path,
        "Script 3 overtime clause classification JSON",
    )

    return (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    )


def load_review_sources(
    interpretation_path: Path | str,
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> tuple[Path, Path, Path, str, dict[str, Any], dict[str, Any]]:
    """Return review source artifacts using the legacy helper name."""
    return load_review_source_artifacts(
        interpretation_path,
        classification_path,
        overtime_clause_classification_path,
    )


# 4. Prompt building / parsing


def build_review_evaluator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build the evaluator prompt set for the step-3B review."""
    return [
        {"role": "system", "content": evaluation_system_prompt()},
        {
            "role": "user",
            # Build the full evaluator review prompt from the interpretation and source artifacts.
            "content": build_full_evaluator_review_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                classification_path=classification_path,
                payment_classification=payment_classification,
                overtime_clause_classification_path=overtime_clause_classification_path,
                overtime_clause_classification=overtime_clause_classification,
            ),
        },
    ]


def build_evaluator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return evaluator messages using the legacy helper name."""
    return build_review_evaluator_messages(
        interpretation_path=interpretation_path,
        interpretation_markdown=interpretation_markdown,
        classification_path=classification_path,
        payment_classification=payment_classification,
        overtime_clause_classification_path=overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
    )


def build_review_creator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    prior_creator_decision_markdown: str | None = None,
) -> list[dict[str, str]]:
    """Build the creator prompt set used to revise the interpretation."""
    # Extract only the clause excerpts that matter to the evaluator's feedback.
    relevant_clause_excerpt_markdown = build_relevant_clause_excerpt_markdown(
        interpretation_markdown=interpretation_markdown,
        payment_classification=payment_classification,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        prior_creator_decision_markdown=prior_creator_decision_markdown,
    )

    # Rebuild the original script-3 creator prompt context for consistency with the source workflow.
    creator_prompt_context = build_script_3_creator_prompt_context(
        classification_path,
        payment_classification,
        overtime_clause_classification,
    )

    return [
        # Reuse the original system message from the step-3 creator context.
        creator_prompt_context["interpretation_messages"][0],
        {
            "role": "user",
            # Ask the creator model to revise the interpretation in response to evaluator feedback.
            "content": build_minimal_creator_revision_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                relevant_clause_excerpt_markdown=relevant_clause_excerpt_markdown,
                evaluator_feedback_markdown=evaluator_feedback_markdown,
                prior_creator_decision_markdown=prior_creator_decision_markdown,
            ),
        },
    ]


def build_creator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    prior_creator_decision_markdown: str | None = None,
) -> list[dict[str, str]]:
    """Return creator messages using the legacy helper name."""
    return build_review_creator_messages(
        interpretation_path=interpretation_path,
        interpretation_markdown=interpretation_markdown,
        classification_path=classification_path,
        payment_classification=payment_classification,
        overtime_clause_classification_path=overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        prior_creator_decision_markdown=prior_creator_decision_markdown,
    )


def split_creator_update_sections(output_text: str) -> tuple[str, str]:
    """Split the creator output into the response section and revised interpretation."""
    match = CREATOR_RESPONSE_PATTERN.search(output_text)
    if not match:
        raise OvertimeInterpretationReviewError(
            "Creator response did not include the required creator_response and "
            "revised_interpretation tagged sections."
        )

    creator_response = match.group("creator_response").strip()
    revised_interpretation = match.group("revised_interpretation").strip()

    if not creator_response:
        raise OvertimeInterpretationReviewError("Creator response section is empty.")
    if not revised_interpretation:
        raise OvertimeInterpretationReviewError("Revised interpretation section is empty.")

    return creator_response, revised_interpretation


def parse_creator_update(output_text: str) -> tuple[str, str]:
    """Return the split creator output using the legacy helper name."""
    return split_creator_update_sections(output_text)


# 5. Review orchestration


def review_overtime_interpretation(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    overtime_clause_classification_path: Path | str | None = None,
    feedback_output_path: Path | str | None = None,
    creator_response_output_path: Path | str | None = None,
    revised_output_path: Path | str | None = None,
    evaluator_model: str | None = None,
    creator_model: str | None = None,
    evaluator_client: Any | None = None,
    creator_client: Any | None = None,
    status_callback: Callable[[str], None] | None = None,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
) -> OvertimeInterpretationReviewArtifacts:
    """Run the one-pass evaluator and creator review workflow for step 3B."""
    # Pick explicit model overrides first, then environment variables, then defaults.
    selected_evaluator_model = evaluator_model or os.getenv(
        "OVERTIME_INTERPRETATION_EVALUATOR_MODEL",
        EVALUATOR_MODEL,
    )
    selected_creator_model = creator_model or os.getenv(
        "OVERTIME_INTERPRETATION_REVIEW_CREATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )

    if evaluator_client is None:
        # Build the OpenRouter client only when this function owns evaluator setup.
        evaluator_client = build_openrouter_client(load_openrouter_api_key())
    if creator_client is None:
        # Load OpenAI credentials only when this function owns creator setup.
        load_openai_environment()
        creator_client = OpenAI()

    if status_callback:
        status_callback("Loading interpretation and Script 2/3 classification sources")

    # Load the interpretation and both supporting classification artifacts.
    (
        selected_interpretation_path,
        selected_classification_path,
        selected_overtime_clause_classification_path,
        interpretation_markdown,
        classification_data,
        overtime_clause_classification,
    ) = load_review_source_artifacts(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
    )

    # Build the evaluator prompt from the current interpretation and its source evidence.
    evaluator_messages = build_review_evaluator_messages(
        interpretation_path=selected_interpretation_path,
        interpretation_markdown=interpretation_markdown,
        classification_path=selected_classification_path,
        payment_classification=classification_data,
        overtime_clause_classification_path=selected_overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
    )

    if status_callback:
        status_callback(f"Awaiting evaluator model: {selected_evaluator_model}")

    # Log the evaluator model-call budget before sending the request.
    log_model_call_budget(
        status_callback,
        call_label="script_3b_evaluator_review",
        model=selected_evaluator_model,
        payload=evaluator_messages,
    )
    evaluator_response = evaluator_client.chat.completions.create(
        model=selected_evaluator_model,
        messages=evaluator_messages,
    )
    # Extract the evaluator's markdown feedback from the OpenRouter response.
    evaluator_feedback_markdown = extract_chat_response_text(evaluator_response)
    if not evaluator_feedback_markdown:
        raise OvertimeInterpretationReviewError(
            "OpenRouter evaluator response did not include output text."
        )

    if status_callback:
        status_callback("Evaluator processed feedback")
        status_callback(f"Awaiting creator update model: {selected_creator_model}")

    if inter_call_delay_seconds > 0:
        if status_callback:
            status_callback(
                "Waiting "
                f"{inter_call_delay_seconds:.1f} seconds before creator update."
            )
        # Pause between calls when requested so the review workflow is easier to monitor and budget.
        time.sleep(inter_call_delay_seconds)

    # Build the creator prompt from the original interpretation plus evaluator feedback.
    creator_messages = build_review_creator_messages(
        interpretation_path=selected_interpretation_path,
        interpretation_markdown=interpretation_markdown,
        classification_path=selected_classification_path,
        payment_classification=classification_data,
        overtime_clause_classification_path=selected_overtime_clause_classification_path,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
    )
    # Log the creator model-call budget before sending the revision request.
    log_model_call_budget(
        status_callback,
        call_label="script_3b_creator_revision",
        model=selected_creator_model,
        payload=creator_messages,
    )
    creator_response = creator_client.responses.create(
        model=selected_creator_model,
        input=creator_messages,
    )
    # Extract the tagged creator output from the OpenAI response.
    creator_output_text = extract_response_text(creator_response)
    if not creator_output_text:
        raise OvertimeInterpretationReviewError(
            "Creator response did not include output text."
        )

    # Split the creator output into the decision record and revised interpretation markdown.
    creator_response_markdown, revised_interpretation_markdown = split_creator_update_sections(
        creator_output_text
    )

    feedback_path = (
        Path(feedback_output_path)
        if feedback_output_path
        else evaluator_feedback_path_for_interpretation(selected_interpretation_path)
    )
    creator_response_path = (
        Path(creator_response_output_path)
        if creator_response_output_path
        else creator_response_path_for_interpretation(selected_interpretation_path)
    )
    revised_path = (
        Path(revised_output_path)
        if revised_output_path
        else revised_output_path_for_interpretation(selected_interpretation_path)
    )

    if status_callback:
        status_callback("Writing feedback, creator response, and revised interpretation")

    # Save each output artifact separately so the review trail remains auditable.
    write_text_with_archive(feedback_path, evaluator_feedback_markdown)
    write_text_with_archive(creator_response_path, creator_response_markdown)
    write_text_with_archive(revised_path, revised_interpretation_markdown)

    if status_callback:
        status_callback("Review update complete")

    return OvertimeInterpretationReviewArtifacts(
        evaluator_feedback_path=feedback_path,
        creator_response_path=creator_response_path,
        revised_interpretation_path=revised_path,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        creator_response_markdown=creator_response_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
    )


# 6. Main orchestration


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the one-pass step-3B review command."""
    parser = argparse.ArgumentParser(
        description="Run one-pass supervisor feedback and creator update for a step 3 overtime interpretation."
    )
    parser.add_argument(
        "award_or_interpretation_path",
        nargs="?",
        default="MA000018",
        help=(
            "Award code such as MA000002, or a path to an overtime interpretation "
            "markdown file."
        ),
    )
    parser.add_argument(
        "--classification-path",
        default=None,
        help=(
            "Optional path to the payment classification JSON file. If omitted, "
            "the path is derived from the award code or interpretation filename."
        ),
    )
    parser.add_argument(
        "--overtime-clause-classification-path",
        default=None,
        help=(
            "Optional path to the Script 3 intermediate overtime clause classification "
            "JSON. If omitted, the path is derived from the payment classification path."
        ),
    )
    parser.add_argument(
        "--evaluator-model",
        default=None,
        help=f"OpenRouter evaluator model to use. Defaults to {EVALUATOR_MODEL}.",
    )
    parser.add_argument(
        "--creator-model",
        default=None,
        help=(
            "OpenAI creator model to use. Defaults to "
            f"OVERTIME_INTERPRETATION_REVIEW_CREATOR_MODEL or {DEFAULT_CREATOR_MODEL}."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the one-pass step-3B review workflow from the command line."""
    # Read the CLI inputs that determine which interpretation and supporting files to review.
    args = parse_args(argv)
    # Resolve the interpretation markdown path from either an award code or an explicit file path.
    interpretation_path = resolve_interpretation_path(args.award_or_interpretation_path)
    # Resolve the payment-classification source that belongs to this interpretation.
    classification_path = resolve_classification_path(
        args.award_or_interpretation_path,
        args.classification_path,
    )
    # Resolve the step-3 clause-classification source that belongs to the payment classification.
    overtime_clause_classification_path = resolve_overtime_clause_classification_path(
        classification_path,
        args.overtime_clause_classification_path,
    )

    print(f"Starting overtime interpretation review for {interpretation_path}")
    print(f"Using classification source {classification_path}")
    print(f"Using overtime clause classification source {overtime_clause_classification_path}")

    # Run the evaluator-plus-creator review loop and print status updates as it progresses.
    artifacts = review_overtime_interpretation(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        evaluator_model=args.evaluator_model,
        creator_model=args.creator_model,
        status_callback=lambda message: print(f"Status: {message}"),
    )

    print(f"Evaluator feedback saved to {artifacts.evaluator_feedback_path}")
    print(f"Creator response saved to {artifacts.creator_response_path}")
    print(f"Revised overtime interpretation saved to {artifacts.revised_interpretation_path}")


if __name__ == "__main__":
    main()
