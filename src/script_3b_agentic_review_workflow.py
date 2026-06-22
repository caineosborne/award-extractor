import asyncio
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, Runner, function_tool
from openai import RateLimitError
from pydantic import BaseModel, Field

from src.common.model_call_budget import is_large_model_call, log_model_call_budget
from src.common.output_paths import write_text_with_archive
from src.common.pipeline_runtime import load_openai_environment as require_openai_environment
from src.script_3_interpret_overtime import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_MODEL as DEFAULT_CREATOR_MODEL,
    build_messages as build_overtime_interpretation_messages,
    classification_output_path_for_classification,
    filter_overtime_clauses,
    filter_overtime_creation_clauses,
    load_classification,
    validate_overtime_clause_classifications,
)
from src.script_3b_review_overtime_interpretation import (
    DEFAULT_INTER_CALL_DELAY_SECONDS as REVIEW_DEFAULT_INTER_CALL_DELAY_SECONDS,
    DEFAULT_INTERPRETATION_PATH,
    OvertimeInterpretationReviewError,
    build_evaluator_messages,
    feedback_dir_for_interpretation,
    load_json_file,
    load_text_file,
    revised_output_path_for_interpretation,
)
from src.script_3b_shared_prompts import (
    build_agentic_creator_instructions,
    build_minimal_pass_fail_evaluator_prompt,
)


DEFAULT_MAX_FEEDBACK_CYCLES = 3
DEFAULT_INTER_CALL_DELAY_SECONDS = REVIEW_DEFAULT_INTER_CALL_DELAY_SECONDS
DEFAULT_RATE_LIMIT_MAX_ATTEMPTS = 6
DEFAULT_RATE_LIMIT_FALLBACK_DELAY_SECONDS = 15.0
RATE_LIMIT_DELAY_BUFFER_SECONDS = 2.0


class AgenticReviewFinalOutput(BaseModel):
    conversation_markdown: str = Field(
        description="Markdown summary of the creator/evaluator review conversation."
    )
    revised_interpretation_markdown: str = Field(
        description="Complete final revised overtime interpretation in markdown."
    )


@dataclass(frozen=True)
class AgenticOvertimeInterpretationReviewArtifacts:
    conversation_path: Path
    revised_interpretation_path: Path
    conversation_markdown: str
    revised_interpretation_markdown: str
    evaluator_feedback_cycles: int


@dataclass
class AgenticReviewContext:
    evaluator_agent: Agent
    evaluator_input_builder: Callable[[str, int], str]
    transcript_entries: list[tuple[str, str, str]] = field(default_factory=list)
    feedback_cycles_used: int = 0
    max_feedback_cycles: int = DEFAULT_MAX_FEEDBACK_CYCLES
    runner_run: Callable[..., Awaitable[Any]] = Runner.run
    status_callback: Callable[[str], None] | None = None
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS
    latest_substantive_feedback_markdown: str = ""


def load_openai_environment(env_path: Path | str = Path(__file__).resolve().parents[1] / ".env") -> None:
    """Load and validate the OpenAI environment for agentic review."""
    require_openai_environment(
        env_path=env_path,
        error_type=OvertimeInterpretationReviewError,
    )


def agentic_conversation_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default saved conversation path for agentic review output."""
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_agentic_review_conversation.md"


def rate_limit_delay_seconds(
    error: RateLimitError,
    fallback_delay_seconds: float = DEFAULT_RATE_LIMIT_FALLBACK_DELAY_SECONDS,
) -> float:
    """Estimate a safe retry delay from a model rate limit response."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after) + RATE_LIMIT_DELAY_BUFFER_SECONDS
            except ValueError:
                pass

    message = str(error)
    retry_match = re.search(r"try again in ([0-9.]+)s", message, re.IGNORECASE)
    if retry_match:
        return float(retry_match.group(1)) + RATE_LIMIT_DELAY_BUFFER_SECONDS

    return fallback_delay_seconds


async def run_agent_with_rate_limit_retries(
    runner_run: Callable[..., Awaitable[Any]],
    agent: Agent,
    input_text: str,
    *,
    max_attempts: int = DEFAULT_RATE_LIMIT_MAX_ATTEMPTS,
    fallback_delay_seconds: float = DEFAULT_RATE_LIMIT_FALLBACK_DELAY_SECONDS,
    status_callback: Callable[[str], None] | None = None,
    **runner_kwargs: Any,
) -> Any:
    """Run an agent call with bounded retries for model rate limits."""
    for attempt_number in range(1, max_attempts + 1):
        try:
            return await runner_run(agent, input_text, **runner_kwargs)
        except RateLimitError as exc:
            if attempt_number == max_attempts:
                raise

            delay_seconds = rate_limit_delay_seconds(exc, fallback_delay_seconds)
            if status_callback:
                status_callback(
                    "Rate limit reached. Waiting "
                    f"{delay_seconds:.1f} seconds before retry "
                    f"{attempt_number + 1}/{max_attempts}."
                )
            await asyncio.sleep(delay_seconds)

    raise OvertimeInterpretationReviewError("Agent run did not return a result.")


def load_relevant_overtime_creation_clauses(
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
) -> list[Any]:
    """Load the subset of source clauses that can create overtime entitlement."""
    overtime_clauses = filter_overtime_clauses(payment_classification)
    clause_classifications = validate_overtime_clause_classifications(
        overtime_clause_classification,
        overtime_clauses,
    )
    return filter_overtime_creation_clauses(clause_classifications)


def build_agentic_source_context(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
) -> str:
    """Build the source context supplied to the creator agent."""
    interpretation_messages = build_overtime_interpretation_messages(
        str(classification_path),
        load_relevant_overtime_creation_clauses(
            classification_path,
            payment_classification,
            overtime_clause_classification,
        ),
    )

    return f"""Original Script 3 interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Relevant source clauses for the first pass:

```markdown
{interpretation_messages[1]["content"]}
```
"""


def build_evaluator_agent(evaluator_model: str) -> Agent:
    """Create the evaluator agent used by the creator review loop."""
    return Agent(
        name="Overtime interpretation evaluator",
        model=evaluator_model,
        instructions=(
            "You are a supervisor reviewing an Australian modern award overtime "
            "creation interpretation. Follow the requested output format exactly. "
            "For substantive reviews, provide concise feedback only and do not rewrite "
            "the document. For pass/fail gate checks, return JSON only."
        ),
    )


def build_evaluator_input_builder(
    interpretation_path: Path | str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
) -> Callable[[str, int], str]:
    """Build the function that prepares evaluator input for each feedback cycle."""
    def build_input(current_draft_markdown: str, feedback_cycle: int) -> str:
        messages = build_evaluator_messages(
            interpretation_path=interpretation_path,
            interpretation_markdown=current_draft_markdown,
            classification_path=classification_path,
            payment_classification=payment_classification,
            overtime_clause_classification_path=overtime_clause_classification_path,
            overtime_clause_classification=overtime_clause_classification,
        )
        return (
            f"Feedback cycle {feedback_cycle}.\n\n"
            f"{messages[0]['content']}\n\n"
            f"{messages[1]['content']}"
        )

    return build_input


def format_transcript(entries: list[tuple[str, str, str]]) -> str:
    """Format the creator and evaluator exchange as markdown audit notes."""
    lines = ["# Agentic overtime interpretation review conversation"]

    if not entries:
        lines.append("")
        lines.append("No evaluator feedback was requested before finalisation.")
        return "\n".join(lines).strip()

    for cycle_label, creator_request, evaluator_response in entries:
        lines.extend(
            [
                "",
                f"## {cycle_label}",
                "",
                "### Creator request",
                "",
                creator_request.strip(),
                "",
                "### Evaluator feedback",
                "",
                evaluator_response.strip(),
            ]
        )

    return "\n".join(lines).strip()


def final_output_to_artifact_text(final_output: Any, fallback_conversation: str) -> tuple[str, str]:
    """Convert structured agent output into persisted conversation and revision text."""
    if not isinstance(final_output, AgenticReviewFinalOutput):
        raise OvertimeInterpretationReviewError(
            "Creator agent did not return the required structured final output."
        )

    revised_interpretation = final_output.revised_interpretation_markdown.strip()
    if not revised_interpretation:
        raise OvertimeInterpretationReviewError("Revised interpretation section is empty.")

    conversation_markdown = final_output.conversation_markdown.strip()
    if not conversation_markdown:
        conversation_markdown = fallback_conversation

    return conversation_markdown, revised_interpretation


def create_evaluator_feedback_tool(context: AgenticReviewContext):
    """Create the tool the creator agent uses to request evaluator feedback."""
    @function_tool
    async def request_evaluator_feedback(
        current_draft_markdown: str,
        creator_question_or_focus: str,
        prior_creator_decision_markdown: str | None = None,
    ) -> str:
        """Ask the evaluator to review the current overtime interpretation draft."""
        if context.feedback_cycles_used >= context.max_feedback_cycles:
            return (
                "Maximum evaluator feedback cycles have already been used. "
                "Finalize the revised interpretation now."
            )

        context.feedback_cycles_used += 1
        cycle_label = f"Feedback cycle {context.feedback_cycles_used}"
        creator_request = creator_question_or_focus.strip()
        if context.feedback_cycles_used == 1:
            evaluator_input = context.evaluator_input_builder(
                current_draft_markdown,
                context.feedback_cycles_used,
            )
        else:
            evaluator_input = build_minimal_pass_fail_evaluator_prompt(
                current_draft_markdown=current_draft_markdown,
                evaluator_feedback_markdown=context.latest_substantive_feedback_markdown,
                prior_creator_decision_markdown=prior_creator_decision_markdown
                or creator_request,
            )

        if (
            context.inter_call_delay_seconds > 0
            and is_large_model_call(evaluator_input)
        ):
            if context.status_callback:
                context.status_callback(
                    "Waiting "
                    f"{context.inter_call_delay_seconds:.1f} seconds before evaluator review."
                )
            await asyncio.sleep(context.inter_call_delay_seconds)

        log_model_call_budget(
            context.status_callback,
            call_label="script_3b_agentic_evaluator",
            model=str(getattr(context.evaluator_agent, "model", "unknown-model")),
            payload=evaluator_input,
        )
        result = await run_agent_with_rate_limit_retries(
            context.runner_run,
            context.evaluator_agent,
            evaluator_input,
            status_callback=context.status_callback,
            max_turns=2,
        )
        evaluator_feedback = str(result.final_output).strip()
        if not evaluator_feedback:
            raise OvertimeInterpretationReviewError(
                "Evaluator agent response did not include output text."
            )

        if context.feedback_cycles_used == 1:
            context.latest_substantive_feedback_markdown = evaluator_feedback

        context.transcript_entries.append(
            (cycle_label, creator_request, evaluator_feedback)
        )
        return evaluator_feedback

    return request_evaluator_feedback


async def run_agentic_overtime_interpretation_review_async(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    overtime_clause_classification_path: Path | str | None = None,
    conversation_output_path: Path | str | None = None,
    revised_output_path: Path | str | None = None,
    creator_model: str | None = None,
    evaluator_model: str | None = None,
    max_feedback_cycles: int = DEFAULT_MAX_FEEDBACK_CYCLES,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
    runner_run: Callable[..., Awaitable[Any]] = Runner.run,
    status_callback: Callable[[str], None] | None = None,
) -> AgenticOvertimeInterpretationReviewArtifacts:
    """Run the full asynchronous agentic review workflow for step 3B."""
    if max_feedback_cycles < 1:
        raise OvertimeInterpretationReviewError("max_feedback_cycles must be at least 1.")

    selected_creator_model = creator_model or os.getenv(
        "OVERTIME_INTERPRETATION_AGENTIC_CREATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )
    selected_evaluator_model = evaluator_model or os.getenv(
        "OVERTIME_INTERPRETATION_AGENTIC_EVALUATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )

    if status_callback:
        status_callback("Loading interpretation and Script 2/3 classification sources")

    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    selected_overtime_clause_classification_path = (
        Path(overtime_clause_classification_path)
        if overtime_clause_classification_path
        else classification_output_path_for_classification(selected_classification_path)
    )
    interpretation_markdown = load_text_file(
        selected_interpretation_path,
        "Overtime interpretation markdown",
    )
    classification_data = load_classification(selected_classification_path)
    overtime_clause_classification = load_json_file(
        selected_overtime_clause_classification_path,
        "Script 3 overtime clause classification JSON",
    )
    source_context = build_agentic_source_context(
        interpretation_path=selected_interpretation_path,
        interpretation_markdown=interpretation_markdown,
        classification_path=selected_classification_path,
        payment_classification=classification_data,
        overtime_clause_classification=overtime_clause_classification,
    )

    evaluator_agent = build_evaluator_agent(selected_evaluator_model)
    review_context = AgenticReviewContext(
        evaluator_agent=evaluator_agent,
        evaluator_input_builder=build_evaluator_input_builder(
            interpretation_path=selected_interpretation_path,
            classification_path=selected_classification_path,
            payment_classification=classification_data,
            overtime_clause_classification_path=selected_overtime_clause_classification_path,
            overtime_clause_classification=overtime_clause_classification,
        ),
        max_feedback_cycles=max_feedback_cycles,
        runner_run=runner_run,
        status_callback=status_callback,
        inter_call_delay_seconds=inter_call_delay_seconds,
    )
    evaluator_tool = create_evaluator_feedback_tool(review_context)
    creator_agent = Agent(
        name="Overtime interpretation creator",
        model=selected_creator_model,
        instructions=build_agentic_creator_instructions(max_feedback_cycles),
        tools=[evaluator_tool],
        output_type=AgenticReviewFinalOutput,
    )

    creator_input = f"""Review and revise the existing Script 3 first draft.

Use the evaluator feedback tool before finalising unless the draft clearly needs no evaluator input.

{source_context}
"""

    if status_callback:
        status_callback(f"Awaiting creator agent: {selected_creator_model}")

    if inter_call_delay_seconds > 0 and is_large_model_call(creator_input):
        if status_callback:
            status_callback(
                "Waiting "
                f"{inter_call_delay_seconds:.1f} seconds before creator agent."
            )
        await asyncio.sleep(inter_call_delay_seconds)

    log_model_call_budget(
        status_callback,
        call_label="script_3b_agentic_creator",
        model=selected_creator_model,
        payload=creator_input,
    )
    creator_result = await run_agent_with_rate_limit_retries(
        runner_run,
        creator_agent,
        creator_input,
        status_callback=status_callback,
        max_turns=(max_feedback_cycles * 3) + 4,
    )

    captured_transcript = format_transcript(review_context.transcript_entries)
    creator_conversation_markdown, revised_interpretation_markdown = final_output_to_artifact_text(
        creator_result.final_output,
        captured_transcript,
    )
    conversation_markdown = captured_transcript
    if creator_conversation_markdown != captured_transcript:
        conversation_markdown = (
            f"{captured_transcript}\n\n"
            "## Creator final decision record\n\n"
            f"{creator_conversation_markdown}"
        )

    conversation_path = (
        Path(conversation_output_path)
        if conversation_output_path
        else agentic_conversation_path_for_interpretation(selected_interpretation_path)
    )
    revised_path = (
        Path(revised_output_path)
        if revised_output_path
        else revised_output_path_for_interpretation(selected_interpretation_path)
    )

    if status_callback:
        status_callback("Writing agentic conversation and revised interpretation")

    write_text_with_archive(conversation_path, conversation_markdown)
    write_text_with_archive(revised_path, revised_interpretation_markdown)

    if status_callback:
        status_callback("Agentic review complete")

    return AgenticOvertimeInterpretationReviewArtifacts(
        conversation_path=conversation_path,
        revised_interpretation_path=revised_path,
        conversation_markdown=conversation_markdown,
        revised_interpretation_markdown=revised_interpretation_markdown,
        evaluator_feedback_cycles=review_context.feedback_cycles_used,
    )


def run_agentic_overtime_interpretation_review(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    overtime_clause_classification_path: Path | str | None = None,
    conversation_output_path: Path | str | None = None,
    revised_output_path: Path | str | None = None,
    creator_model: str | None = None,
    evaluator_model: str | None = None,
    max_feedback_cycles: int = DEFAULT_MAX_FEEDBACK_CYCLES,
    inter_call_delay_seconds: float = DEFAULT_INTER_CALL_DELAY_SECONDS,
    runner_run: Callable[..., Awaitable[Any]] = Runner.run,
    status_callback: Callable[[str], None] | None = None,
) -> AgenticOvertimeInterpretationReviewArtifacts:
    """Run the synchronous wrapper around the agentic step-3B review workflow."""
    return asyncio.run(
        run_agentic_overtime_interpretation_review_async(
            interpretation_path=interpretation_path,
            classification_path=classification_path,
            overtime_clause_classification_path=overtime_clause_classification_path,
            conversation_output_path=conversation_output_path,
            revised_output_path=revised_output_path,
            creator_model=creator_model,
            evaluator_model=evaluator_model,
            max_feedback_cycles=max_feedback_cycles,
            inter_call_delay_seconds=inter_call_delay_seconds,
            runner_run=runner_run,
            status_callback=status_callback,
        )
    )
