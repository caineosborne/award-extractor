import argparse
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.script_4a_prompt_Overtime_System_Prompt import OVERTIME_REVIEW_DOCUMENT_SYSTEM_PROMPT


from src.output_paths import (
    OVERTIME_INTERPRETATION_FEEDBACK_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    write_text_with_archive,
)
from src.script_2_classify_payments import extract_response_text
from src.script_3_interpret_overtime import (
    DEFAULT_CLASSIFICATION_PATH,
    DEFAULT_MODEL as DEFAULT_CREATOR_MODEL,
    filter_overtime_clauses,
    load_classification,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERPRETATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_INTERPRETATIONS_DIR
    / "MA000018_overtime_interpretation.md"
)
EVALUATOR_MODEL = "anthropic/claude-sonnet-4.6"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CREATOR_RESPONSE_PATTERN = re.compile(
    r"<creator_response>\s*(?P<creator_response>.*?)\s*</creator_response>\s*"
    r"<revised_interpretation>\s*(?P<revised_interpretation>.*?)\s*</revised_interpretation>",
    re.DOTALL,
)


class OvertimeInterpretationReviewError(RuntimeError):
    """Base exception for overtime interpretation review failures."""


@dataclass(frozen=True)
class OvertimeInterpretationReviewArtifacts:
    evaluator_feedback_path: Path
    creator_response_path: Path
    revised_interpretation_path: Path
    evaluator_feedback_markdown: str
    creator_response_markdown: str
    revised_interpretation_markdown: str


def load_openrouter_api_key(env_path: Path | str = PROJECT_ROOT / ".env") -> str:
    load_dotenv(env_path)

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise OvertimeInterpretationReviewError(
            "OpenRouter API key is not set. Add OPENROUTER_API_KEY or "
            "OPEN_ROUTER_API_KEY to the root .env file or export it."
        )

    return api_key


def load_openai_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeInterpretationReviewError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def build_openrouter_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def extract_chat_completion_text(response: Any) -> str:
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
            if isinstance(content_item, Mapping):
                text = content_item.get("text")
            else:
                text = getattr(content_item, "text", None)

            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

        return "\n".join(text_parts)

    return ""


def load_text_file(path: Path | str, description: str) -> str:
    selected_path = Path(path)
    if not selected_path.exists():
        raise OvertimeInterpretationReviewError(f"{description} not found: {selected_path}")

    text = selected_path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeInterpretationReviewError(f"{description} is empty: {selected_path}")

    return text


def feedback_dir_for_interpretation(interpretation_path: Path | str) -> Path:
    return Path(interpretation_path).parent / OVERTIME_INTERPRETATION_FEEDBACK_DIR


def evaluator_feedback_path_for_interpretation(interpretation_path: Path | str) -> Path:
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_evaluator_feedback.md"


def creator_response_path_for_interpretation(interpretation_path: Path | str) -> Path:
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_creator_response.md"


def revised_output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    path = Path(interpretation_path)
    return path.with_name(f"{path.stem}_revised{path.suffix}")


def default_interpretation_path_for_award(award_code: str) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / OVERTIME_INTERPRETATIONS_DIR
        / f"{award_code}_overtime_interpretation.md"
    )


def default_classification_path_for_award(award_code: str) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "2_payment_clause_identifier"
        / f"{award_code}_payment_classification.json"
    )


def award_code_from_interpretation_path(interpretation_path: Path | str) -> str:
    stem = Path(interpretation_path).stem
    if stem.endswith("_overtime_interpretation"):
        return stem.removesuffix("_overtime_interpretation")
    if stem.endswith("_overtime_interpretation_revised"):
        return stem.removesuffix("_overtime_interpretation_revised")

    raise OvertimeInterpretationReviewError(
        "Could not derive award code from interpretation path. "
        "Pass --classification-path explicitly."
    )


def looks_like_path(value: str) -> bool:
    path = Path(value)
    return path.suffix != "" or "/" in value or "\\" in value


def resolve_interpretation_path(award_or_interpretation_path: Path | str) -> Path:
    value = str(award_or_interpretation_path)
    if looks_like_path(value):
        return Path(value)

    return default_interpretation_path_for_award(value)


def resolve_classification_path(
    award_or_interpretation_path: Path | str,
    classification_path: Path | str | None,
) -> Path:
    if classification_path:
        return Path(classification_path)

    value = str(award_or_interpretation_path)
    award_code = value
    if looks_like_path(value):
        award_code = award_code_from_interpretation_path(value)

    return default_classification_path_for_award(award_code)


def evaluation_system_prompt() -> str:
    return """You are a supervisor reviewing an Australian modern award overtime interpretation working document.

Your job is to provide useful feedback to the creator. Do not rewrite the document.
Ask questions and identify concise issues that would help the creator decide whether an update is needed.

Focus on:
- unsupported rules;
- missing material overtime trigger questions;
- confusion between overtime triggers and overtime consequences;
- unclear employee groups;
- weak clause traceability;
- assumptions that should be explicit for auditability.

Return markdown only with this structure:

# Overtime interpretation supervisor feedback

## Overall view

## Questions for the creator

## Potential issues

## Traceability notes
"""


def build_evaluator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    filtered_clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)

    user_prompt = f"""Review this overtime interpretation working document.

Do not rewrite the interpretation. Provide supervisor-style questions and concise issue notes only.

Interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Filtered payment classification source: {classification_path}

Only these clauses were tagged Ordinary Hours & Overtime and are in scope for this review:

```json
{filtered_clauses_json}
```

The interpretation was generated using this system prompt:

```text
{OVERTIME_REVIEW_DOCUMENT_SYSTEM_PROMPT}
```
"""

    return [
        {"role": "system", "content": evaluation_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]


def build_creator_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
    evaluator_feedback_markdown: str,
) -> list[dict[str, str]]:
    filtered_clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)
    user_prompt = f"""Review the supervisor feedback and decide whether the interpretation needs updating.

This is a one-pass update. Do not ask for another review cycle.

Original interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Filtered payment classification source: {classification_path}

Only these clauses were tagged Ordinary Hours & Overtime and are in scope:

```json
{filtered_clauses_json}
```

Supervisor feedback:

```markdown
{evaluator_feedback_markdown}
```

Return exactly two tagged sections:

<creator_response>
Write a short markdown decision record. Explain which feedback you accepted, which feedback you rejected, and why.
</creator_response>
<revised_interpretation>
Write the complete revised overtime interpretation working document in markdown.
</revised_interpretation>
"""

    return [
        {"role": "system", "content": OVERTIME_INTERPRETATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def parse_creator_update(output_text: str) -> tuple[str, str]:
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


def review_overtime_interpretation(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    feedback_output_path: Path | str | None = None,
    creator_response_output_path: Path | str | None = None,
    revised_output_path: Path | str | None = None,
    evaluator_model: str | None = None,
    creator_model: str | None = None,
    evaluator_client: Any | None = None,
    creator_client: Any | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> OvertimeInterpretationReviewArtifacts:
    selected_evaluator_model = evaluator_model or os.getenv(
        "OVERTIME_INTERPRETATION_EVALUATOR_MODEL",
        EVALUATOR_MODEL,
    )
    selected_creator_model = creator_model or os.getenv(
        "OVERTIME_INTERPRETATION_REVIEW_CREATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )

    if evaluator_client is None:
        api_key = load_openrouter_api_key()
        evaluator_client = build_openrouter_client(api_key)
    if creator_client is None:
        load_openai_environment()
        creator_client = OpenAI()

    if status_callback:
        status_callback("Loading interpretation and filtered overtime clauses")

    selected_interpretation_path = Path(interpretation_path)
    selected_classification_path = Path(classification_path)
    interpretation_markdown = load_text_file(
        selected_interpretation_path,
        "Overtime interpretation markdown",
    )
    classification_data = load_classification(selected_classification_path)
    overtime_clauses = filter_overtime_clauses(classification_data)
    if not overtime_clauses:
        raise OvertimeInterpretationReviewError(
            f"No Ordinary Hours or Overtime clauses found in: {selected_classification_path}"
        )

    if status_callback:
        status_callback(f"Awaiting evaluator model: {selected_evaluator_model}")

    evaluator_response = evaluator_client.chat.completions.create(
        model=selected_evaluator_model,
        messages=build_evaluator_messages(
            interpretation_path=selected_interpretation_path,
            interpretation_markdown=interpretation_markdown,
            classification_path=selected_classification_path,
            overtime_clauses=overtime_clauses,
        ),
    )
    evaluator_feedback_markdown = extract_chat_completion_text(evaluator_response)
    if not evaluator_feedback_markdown:
        raise OvertimeInterpretationReviewError(
            "OpenRouter evaluator response did not include output text."
        )

    if status_callback:
        status_callback("Evaluator processed feedback")
        status_callback(f"Awaiting creator update model: {selected_creator_model}")

    creator_response = creator_client.responses.create(
        model=selected_creator_model,
        input=build_creator_messages(
            interpretation_path=selected_interpretation_path,
            interpretation_markdown=interpretation_markdown,
            classification_path=selected_classification_path,
            overtime_clauses=overtime_clauses,
            evaluator_feedback_markdown=evaluator_feedback_markdown,
        ),
    )
    creator_output_text = extract_response_text(creator_response)
    if not creator_output_text:
        raise OvertimeInterpretationReviewError(
            "Creator response did not include output text."
        )

    if status_callback:
        status_callback("Creator processed feedback")

    creator_response_markdown, revised_interpretation_markdown = parse_creator_update(
        creator_output_text
    )

    if status_callback:
        status_callback("Writing feedback, creator response, and revised interpretation")

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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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
        "--feedback-output-path",
        default=None,
        help="Optional path for evaluator feedback markdown.",
    )
    parser.add_argument(
        "--creator-response-output-path",
        default=None,
        help="Optional path for the creator decision response markdown.",
    )
    parser.add_argument(
        "--revised-output-path",
        default=None,
        help="Optional path for the revised overtime interpretation markdown.",
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


def main() -> None:
    args = parse_args()
    interpretation_path = resolve_interpretation_path(args.award_or_interpretation_path)
    classification_path = resolve_classification_path(
        args.award_or_interpretation_path,
        args.classification_path,
    )

    print(f"Starting overtime interpretation review for {interpretation_path}")
    print(f"Using classification source {classification_path}")

    artifacts = review_overtime_interpretation(
        interpretation_path=interpretation_path,
        classification_path=classification_path,
        feedback_output_path=args.feedback_output_path,
        creator_response_output_path=args.creator_response_output_path,
        revised_output_path=args.revised_output_path,
        evaluator_model=args.evaluator_model,
        creator_model=args.creator_model,
        status_callback=lambda message: print(f"Status: {message}"),
    )

    print(f"Evaluator feedback saved to {artifacts.evaluator_feedback_path}")
    print(f"Creator response saved to {artifacts.creator_response_path}")
    print(f"Revised overtime interpretation saved to {artifacts.revised_interpretation_path}")


if __name__ == "__main__":
    main()
