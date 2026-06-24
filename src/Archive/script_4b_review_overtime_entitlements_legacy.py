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

from src.common.output_paths import (
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    write_text_with_archive,
)
from src.common.llm_io import extract_response_text
from src.script_3_interpret_overtime import filter_overtime_clauses, load_classification
from src.script_3b_review_overtime_interpretation import (
    build_openrouter_client,
    extract_chat_completion_text,
)
from src.Archive.script_4a_summarize_overtime_legacy import (
    DEFAULT_MODEL as DEFAULT_CREATOR_MODEL,
    load_overtime_interpretation,
    strip_wrapping_markdown_fence,
)
from src.Archive.script_4a_summarize_overtime_prompt_legacy import (
    OVERTIME_ENTITLEMENT_SYSTEM_PROMPT,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENTITLEMENTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_ENTITLEMENTS_DIR
    / "MA000018_overtime_entitlements.md"
)
EVALUATOR_MODEL = "anthropic/claude-sonnet-4.6"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_FORMATTER_MODEL = "deepseek/deepseek-v4-pro"
UPDATED_ANSWER_PATTERN = re.compile(
    r"<updated_answer>\s*(?P<updated_answer>.*?)\s*</updated_answer>",
    re.DOTALL,
)


class OvertimeEntitlementReviewError(RuntimeError):
    """Base exception for overtime entitlement review failures."""


@dataclass(frozen=True)
class OvertimeEntitlementReviewArtifacts:
    initial_answer_path: Path
    review_feedback_path: Path
    updated_answer_path: Path
    final_answer_path: Path
    initial_answer_markdown: str
    review_feedback_markdown: str
    updated_answer_markdown: str
    final_answer_markdown: str


def load_openrouter_api_key(env_path: Path | str = PROJECT_ROOT / ".env") -> str:
    load_dotenv(env_path)

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise OvertimeEntitlementReviewError(
            "OpenRouter API key is not set. Add OPENROUTER_API_KEY or "
            "OPEN_ROUTER_API_KEY to the root .env file or export it."
        )

    return api_key


def load_openai_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeEntitlementReviewError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_text_file(path: Path | str, description: str) -> str:
    selected_path = Path(path)
    if not selected_path.exists():
        raise OvertimeEntitlementReviewError(f"{description} not found: {selected_path}")

    text = selected_path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeEntitlementReviewError(f"{description} is empty: {selected_path}")

    return text


def looks_like_path(value: str) -> bool:
    path = Path(value)
    return path.suffix != "" or "/" in value or "\\" in value


def award_code_from_entitlements_path(entitlements_path: Path | str) -> str:
    stem = Path(entitlements_path).stem
    if stem.endswith("_overtime_entitlements"):
        return stem.removesuffix("_overtime_entitlements")

    raise OvertimeEntitlementReviewError(
        "Could not derive award code from entitlements path. "
        "Pass --classification-path and --interpretation-path explicitly."
    )


def default_entitlements_path_for_award(award_code: str) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / OVERTIME_ENTITLEMENTS_DIR
        / f"{award_code}_overtime_entitlements.md"
    )


def default_classification_path_for_award(award_code: str) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / PAYMENT_CLAUSE_IDENTIFIER_DIR
        / f"{award_code}_payment_classification.json"
    )


def default_interpretation_path_for_award(award_code: str) -> Path:
    interpretation_dir = PROJECT_ROOT / "data" / "processed" / OVERTIME_INTERPRETATIONS_DIR
    revised_path = interpretation_dir / f"{award_code}_overtime_interpretation_revised.md"
    if revised_path.exists():
        return revised_path

    return interpretation_dir / f"{award_code}_overtime_interpretation.md"


def resolve_entitlements_path(award_or_entitlements_path: Path | str) -> Path:
    value = str(award_or_entitlements_path)
    if looks_like_path(value):
        return Path(value)

    return default_entitlements_path_for_award(value)


def resolve_classification_path(
    award_or_entitlements_path: Path | str,
    classification_path: Path | str | None,
) -> Path:
    if classification_path:
        return Path(classification_path)

    value = str(award_or_entitlements_path)
    award_code = value
    if looks_like_path(value):
        award_code = award_code_from_entitlements_path(value)

    return default_classification_path_for_award(award_code)


def resolve_interpretation_path(
    award_or_entitlements_path: Path | str,
    interpretation_path: Path | str | None,
) -> Path:
    if interpretation_path:
        return Path(interpretation_path)

    value = str(award_or_entitlements_path)
    award_code = value
    if looks_like_path(value):
        award_code = award_code_from_entitlements_path(value)

    return default_interpretation_path_for_award(award_code)


def initial_answer_path_for_entitlements(entitlements_path: Path | str) -> Path:
    path = Path(entitlements_path)
    return path.with_name(f"{path.stem}_initial_answer{path.suffix}")


def review_feedback_path_for_entitlements(entitlements_path: Path | str) -> Path:
    path = Path(entitlements_path)
    return path.with_name(f"{path.stem}_review_feedback{path.suffix}")


def updated_answer_path_for_entitlements(entitlements_path: Path | str) -> Path:
    path = Path(entitlements_path)
    return path.with_name(f"{path.stem}_updated_answer{path.suffix}")


def final_answer_path_for_entitlements(entitlements_path: Path | str) -> Path:
    path = Path(entitlements_path)
    return path.with_name(f"{path.stem}_final{path.suffix}")


def output_path_for_entitlements(entitlements_path: Path | str) -> Path:
    return final_answer_path_for_entitlements(entitlements_path)


def output_path_for_classification(classification_path: Path | str) -> Path:
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")

    return path_in_category(
        path,
        OVERTIME_ENTITLEMENTS_DIR,
        f"{stem}_overtime_entitlements_final.md",
    )


def accuracy_evaluation_system_prompt() -> str:
    return """You are a supervisor reviewing an Australian modern award overtime entitlement document.

Your job is to validate the format, accuracy, and reliability of the output. Do not rewrite the document.

Focus on:
- whether all ordinary hours and overtime calculation rules from the supplied sources are included;
- whether overtime triggers are separated from overtime consequences;
- whether rule priority and allocation logic are complete and internally consistent;
- whether the document is self-sufficient for audit review;
- whether important terms are explained where needed;
- whether clause references and award-specific facts align to the supplied sources;
- whether the output follows the expected 4A format.

Return markdown only with this structure:

# Overtime entitlement review feedback

## Overall view

## Accuracy and completeness issues

## Format and self-sufficiency issues

## Calculation and allocation checks

## Source alignment notes
"""


def build_accuracy_evaluator_messages(
    entitlements_path: Path | str,
    entitlements_markdown: str,
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
) -> list[dict[str, str]]:
    filtered_clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)
    user_prompt = f"""Review this step 4A overtime entitlement markdown.

Do not rewrite the document. Provide supervisor-style feedback only.

Initial answer source: {entitlements_path}

```markdown
{entitlements_markdown}
```

Overtime interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Filtered payment classification source: {classification_path}

Only these clauses were tagged Ordinary Hours & Overtime and are in scope for this review:

```json
{filtered_clauses_json}
```

The entitlement document was generated using this system prompt:

```text
{OVERTIME_ENTITLEMENT_SYSTEM_PROMPT}
```
"""

    return [
        {"role": "system", "content": accuracy_evaluation_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]


def build_update_messages(
    entitlements_path: Path | str,
    entitlements_markdown: str,
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    overtime_clauses: Mapping[str, Any],
    review_feedback_markdown: str,
) -> list[dict[str, str]]:
    filtered_clauses_json = json.dumps(overtime_clauses, indent=2, ensure_ascii=False)
    user_prompt = f"""Update the step 4A overtime entitlement markdown using the supervisor feedback.

This is a one-pass update. Do not ask for another review cycle.

Original 4A entitlement source: {entitlements_path}

```markdown
{entitlements_markdown}
```

Overtime interpretation source: {interpretation_path}

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
{review_feedback_markdown}
```

Return exactly one tagged section:

<updated_answer>
Write the complete updated overtime entitlement document in markdown.
</updated_answer>
"""

    return [
        {"role": "system", "content": OVERTIME_ENTITLEMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_formatting_messages(updated_answer_markdown: str) -> list[dict[str, str]]:
    system_prompt = """You improve a markdown overtime entitlement document for human readers.

Use only the supplied markdown. Do not look back to award source material, classification data, or interpretation documents.

Your job is wording and formatting only:
- make the document simple and clear;
- preserve the business meaning, clause references, rates, thresholds, employee groups, and assumptions already present;
- keep ordinary hours and overtime rules easy to scan;
- use concise markdown headings and bullets;
- do not add new source claims;
- do not remove audit-relevant caveats or assumptions;
- do not wrap the answer in a markdown code fence.

Return markdown only."""

    user_prompt = f"""Format this updated overtime entitlement document for human review.

```markdown
{updated_answer_markdown}
```
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_updated_answer(output_text: str) -> str:
    match = UPDATED_ANSWER_PATTERN.search(output_text)
    if match:
        updated_answer = match.group("updated_answer").strip()
        if not updated_answer:
            raise OvertimeEntitlementReviewError("Updated answer section is empty.")

        return updated_answer

    updated_answer = strip_wrapping_markdown_fence(output_text)
    if not updated_answer:
        raise OvertimeEntitlementReviewError(
            "Creator response did not include the required updated_answer tagged section "
            "or usable markdown."
        )

    return updated_answer


def review_overtime_entitlements(
    entitlements_path: Path | str = DEFAULT_ENTITLEMENTS_PATH,
    classification_path: Path | str | None = None,
    interpretation_path: Path | str | None = None,
    initial_output_path: Path | str | None = None,
    feedback_output_path: Path | str | None = None,
    updated_output_path: Path | str | None = None,
    final_output_path: Path | str | None = None,
    evaluator_model: str | None = None,
    creator_model: str | None = None,
    formatter_model: str | None = None,
    evaluator_client: Any | None = None,
    creator_client: Any | None = None,
    formatter_client: Any | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> OvertimeEntitlementReviewArtifacts:
    selected_evaluator_model = evaluator_model or os.getenv(
        "OVERTIME_ENTITLEMENT_EVALUATOR_MODEL",
        EVALUATOR_MODEL,
    )
    selected_creator_model = creator_model or os.getenv(
        "OVERTIME_ENTITLEMENT_REVIEW_CREATOR_MODEL",
        DEFAULT_CREATOR_MODEL,
    )
    selected_formatter_model = formatter_model or os.getenv(
        "OVERTIME_ENTITLEMENT_FORMATTER_MODEL",
        DEFAULT_FORMATTER_MODEL,
    )

    if evaluator_client is None:
        api_key = load_openrouter_api_key()
        evaluator_client = build_openrouter_client(api_key)
    if creator_client is None or formatter_client is None:
        load_openai_environment()
    if creator_client is None:
        creator_client = OpenAI()
    if formatter_client is None:
        formatter_client = OpenAI()

    selected_entitlements_path = Path(entitlements_path)
    selected_classification_path = Path(classification_path) if classification_path else None
    selected_interpretation_path = Path(interpretation_path) if interpretation_path else None

    if selected_classification_path is None or selected_interpretation_path is None:
        award_code = award_code_from_entitlements_path(selected_entitlements_path)
        if selected_classification_path is None:
            selected_classification_path = default_classification_path_for_award(award_code)
        if selected_interpretation_path is None:
            selected_interpretation_path = default_interpretation_path_for_award(award_code)

    if status_callback:
        status_callback("Loading 4A entitlement markdown and review sources")

    initial_path = (
        Path(initial_output_path)
        if initial_output_path
        else initial_answer_path_for_entitlements(selected_entitlements_path)
    )
    feedback_path = (
        Path(feedback_output_path)
        if feedback_output_path
        else review_feedback_path_for_entitlements(selected_entitlements_path)
    )
    updated_path = (
        Path(updated_output_path)
        if updated_output_path
        else updated_answer_path_for_entitlements(selected_entitlements_path)
    )
    final_path = (
        Path(final_output_path)
        if final_output_path
        else final_answer_path_for_entitlements(selected_entitlements_path)
    )

    initial_answer_markdown = load_text_file(
        selected_entitlements_path,
        "Overtime entitlement markdown",
    )
    interpretation_markdown = load_overtime_interpretation(selected_interpretation_path)
    classification_data = load_classification(selected_classification_path)
    overtime_clauses = filter_overtime_clauses(classification_data)
    if not overtime_clauses:
        raise OvertimeEntitlementReviewError(
            f"No Ordinary Hours or Overtime clauses found in: {selected_classification_path}"
        )

    if status_callback:
        status_callback(f"Awaiting accuracy evaluator model: {selected_evaluator_model}")

    evaluator_response = evaluator_client.chat.completions.create(
        model=selected_evaluator_model,
        messages=build_accuracy_evaluator_messages(
            entitlements_path=selected_entitlements_path,
            entitlements_markdown=initial_answer_markdown,
            interpretation_path=selected_interpretation_path,
            interpretation_markdown=interpretation_markdown,
            classification_path=selected_classification_path,
            overtime_clauses=overtime_clauses,
        ),
    )
    review_feedback_markdown = extract_chat_completion_text(evaluator_response)
    if not review_feedback_markdown:
        raise OvertimeEntitlementReviewError(
            "OpenRouter evaluator response did not include output text."
        )

    write_text_with_archive(initial_path, initial_answer_markdown)
    write_text_with_archive(feedback_path, review_feedback_markdown)

    if status_callback:
        status_callback(f"Awaiting entitlement update model: {selected_creator_model}")

    creator_response = creator_client.responses.create(
        model=selected_creator_model,
        input=build_update_messages(
            entitlements_path=selected_entitlements_path,
            entitlements_markdown=initial_answer_markdown,
            interpretation_path=selected_interpretation_path,
            interpretation_markdown=interpretation_markdown,
            classification_path=selected_classification_path,
            overtime_clauses=overtime_clauses,
            review_feedback_markdown=review_feedback_markdown,
        ),
    )
    creator_output_text = extract_response_text(creator_response)
    if not creator_output_text:
        raise OvertimeEntitlementReviewError(
            "Creator response did not include output text."
        )
    updated_answer_markdown = parse_updated_answer(creator_output_text)

    if status_callback:
        status_callback(f"Awaiting final formatting model: {selected_formatter_model}")

    formatter_response = formatter_client.responses.create(
        model=selected_formatter_model,
        input=build_formatting_messages(updated_answer_markdown),
    )
    final_answer_markdown = extract_response_text(formatter_response)
    if not final_answer_markdown:
        raise OvertimeEntitlementReviewError(
            "Formatter response did not include output text."
        )

    if status_callback:
        status_callback("Writing updated answer and final markdown")

    write_text_with_archive(updated_path, updated_answer_markdown)
    write_text_with_archive(final_path, final_answer_markdown)

    if status_callback:
        status_callback("4B entitlement review complete")

    return OvertimeEntitlementReviewArtifacts(
        initial_answer_path=initial_path,
        review_feedback_path=feedback_path,
        updated_answer_path=updated_path,
        final_answer_path=final_path,
        initial_answer_markdown=initial_answer_markdown,
        review_feedback_markdown=review_feedback_markdown,
        updated_answer_markdown=updated_answer_markdown,
        final_answer_markdown=final_answer_markdown,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run accuracy review and final formatting for a step 4A overtime entitlement document."
    )
    parser.add_argument(
        "award_or_entitlements_path",
        nargs="?",
        default="MA000018",
        help=(
            "Award code such as MA000002, or a path to an overtime entitlement "
            "markdown file."
        ),
    )
    parser.add_argument(
        "--classification-path",
        default=None,
        help=(
            "Optional path to the payment classification JSON file. If omitted, "
            "the path is derived from the award code or entitlement filename."
        ),
    )
    parser.add_argument(
        "--interpretation-path",
        default=None,
        help=(
            "Optional path to the overtime interpretation markdown. If omitted, "
            "award codes prefer the revised 3B interpretation if it exists."
        ),
    )
    parser.add_argument(
        "--initial-output-path",
        default=None,
        help="Optional path for the copied initial 4A answer markdown.",
    )
    parser.add_argument(
        "--feedback-output-path",
        default=None,
        help="Optional path for accuracy review feedback markdown.",
    )
    parser.add_argument(
        "--updated-output-path",
        default=None,
        help="Optional path for the source-aware updated entitlement markdown.",
    )
    parser.add_argument(
        "--final-output-path",
        default=None,
        help="Optional path for the final human-readable entitlement markdown.",
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
            f"OVERTIME_ENTITLEMENT_REVIEW_CREATOR_MODEL or {DEFAULT_CREATOR_MODEL}."
        ),
    )
    parser.add_argument(
        "--formatter-model",
        default=None,
        help=(
            "OpenAI formatter model to use. Defaults to "
            f"OVERTIME_ENTITLEMENT_FORMATTER_MODEL or {DEFAULT_FORMATTER_MODEL}."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    entitlements_path = resolve_entitlements_path(args.award_or_entitlements_path)
    classification_path = resolve_classification_path(
        args.award_or_entitlements_path,
        args.classification_path,
    )
    interpretation_path = resolve_interpretation_path(
        args.award_or_entitlements_path,
        args.interpretation_path,
    )

    print(f"Starting overtime entitlement review for {entitlements_path}")
    print(f"Using classification source {classification_path}")
    print(f"Using interpretation source {interpretation_path}")

    artifacts = review_overtime_entitlements(
        entitlements_path=entitlements_path,
        classification_path=classification_path,
        interpretation_path=interpretation_path,
        initial_output_path=args.initial_output_path,
        feedback_output_path=args.feedback_output_path,
        updated_output_path=args.updated_output_path,
        final_output_path=args.final_output_path,
        evaluator_model=args.evaluator_model,
        creator_model=args.creator_model,
        formatter_model=args.formatter_model,
        status_callback=lambda message: print(f"Status: {message}"),
    )

    print(f"Initial answer saved to {artifacts.initial_answer_path}")
    print(f"Review feedback saved to {artifacts.review_feedback_path}")
    print(f"Updated answer saved to {artifacts.updated_answer_path}")
    print(f"Final markdown saved to {artifacts.final_answer_path}")


if __name__ == "__main__":
    main()
