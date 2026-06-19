import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.script_4a_prompt_Overtime_System_Prompt import (
    OVERTIME_REVIEW_DOCUMENT_SYSTEM_PROMPT,
)
from src.script_5b_generate_overtime_pseudocode import (
    CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE,
    PSEUDOCODE_FIELDS,
)
from src.output_paths import (
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_PSEUDOCODE_DIR,
    OVERTIME_REVIEW_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
    write_text_with_archive,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / PAYMENT_CLAUSE_IDENTIFIER_DIR
    / "MA000018_payment_classification.json"
)
DEFAULT_ENTITLEMENTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_ENTITLEMENTS_DIR
    / "MA000018_overtime_entitlements.md"
)
DEFAULT_PSEUDOCODE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_PSEUDOCODE_DIR
    / "MA000018_core_overtime_pseudocode.md"
)
DEFAULT_MODEL = "qwen/qwen3-coder"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OvertimeQualityEvaluatorError(RuntimeError):
    """Base exception for overtime quality evaluator failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> str:
    load_dotenv(env_path)

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise OvertimeQualityEvaluatorError(
            "OpenRouter API key is not set. Add OPENROUTER_API_KEY or "
            "OPEN_ROUTER_API_KEY to the root .env file or export it."
        )

    return api_key


def build_openrouter_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def load_text_file(path: Path | str, description: str) -> str:
    selected_path = Path(path)
    if not selected_path.exists():
        raise OvertimeQualityEvaluatorError(f"{description} not found: {selected_path}")

    text = selected_path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeQualityEvaluatorError(f"{description} is empty: {selected_path}")

    return text


def load_classification(path: Path | str) -> dict[str, Any]:
    selected_path = Path(path)
    if not selected_path.exists():
        raise OvertimeQualityEvaluatorError(
            f"Payment classification JSON not found: {selected_path}"
        )

    with selected_path.open(encoding="utf-8") as classification_file:
        data = json.load(classification_file)

    if not isinstance(data, dict):
        raise OvertimeQualityEvaluatorError(
            f"Payment classification JSON must contain an object: {selected_path}"
        )
    if not isinstance(data.get("classified_clauses"), dict):
        raise OvertimeQualityEvaluatorError(
            "Payment classification JSON must contain a classified_clauses object."
        )

    return data


def core_overtime_pseudocode_prompt() -> str:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    return CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE.format(fields=fields)


def evaluation_system_prompt() -> str:
    return """You are a quality reviewer for Australian modern award payroll extraction artifacts.

Assess whether the supplied markdown outputs are faithful to the payment classification JSON and
to the generation instructions that produced them.

Review goals:
- Identify unsupported rules, invented employee categories, invented thresholds, invented clause references, and missing material rules.
- Check that overtime entitlement triggers are separated from payment consequences.
- Check that the pseudocode preserves the entitlement summary and only classifies worked hours as Ordinary_Hours or Overtime_Hours.
- Check that clause references in the markdown can be traced back to classified clauses in the JSON.
- Explain issues in a way an audit or assurance reviewer can follow.

Return markdown only with this structure:

# Overtime artifact quality review

## Overall assessment

## Alignment with payment classification JSON

## Overtime entitlement summary quality

## Core overtime pseudocode quality

## Material gaps or unsupported statements

## Recommended remediation
"""


def build_messages(
    classification_path: Path | str,
    classification_data: Mapping[str, Any],
    entitlements_path: Path | str,
    entitlements_markdown: str,
    pseudocode_path: Path | str,
    pseudocode_markdown: str,
) -> list[dict[str, str]]:
    classification_json = json.dumps(classification_data, indent=2, ensure_ascii=False)

    user_prompt = f"""Review these award extraction artifacts for quality.

Payment classification JSON source: {classification_path}

```json
{classification_json}
```

Overtime entitlement markdown source: {entitlements_path}

```markdown
{entitlements_markdown}
```

Core overtime pseudocode markdown source: {pseudocode_path}

```markdown
{pseudocode_markdown}
```

The overtime entitlement markdown was generated using this system prompt:

```text
{OVERTIME_ENTITLEMENT_SYSTEM_PROMPT}
```

The core overtime pseudocode markdown was generated using this system prompt:

```text
{core_overtime_pseudocode_prompt()}
```
"""

    return [
        {"role": "system", "content": evaluation_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]


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


def output_path_for_pseudocode(pseudocode_path: Path | str) -> Path:
    path = Path(pseudocode_path)
    stem = path.stem
    if stem.endswith("_core_overtime_pseudocode"):
        stem = stem.removesuffix("_core_overtime_pseudocode")
    return path_in_category(
        path,
        OVERTIME_REVIEW_DIR,
        f"{stem}_overtime_quality_review.md",
    )


def evaluate_overtime_artifact_quality(
    classification_path: Path | str = DEFAULT_CLASSIFICATION_PATH,
    entitlements_path: Path | str = DEFAULT_ENTITLEMENTS_PATH,
    pseudocode_path: Path | str = DEFAULT_PSEUDOCODE_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("OVERTIME_QUALITY_EVALUATOR_MODEL", DEFAULT_MODEL)

    if client is None:
        api_key = load_environment()
        client = build_openrouter_client(api_key)

    classification_data = load_classification(classification_path)
    entitlements_markdown = load_text_file(
        entitlements_path,
        "Overtime entitlement markdown",
    )
    pseudocode_markdown = load_text_file(
        pseudocode_path,
        "Core overtime pseudocode markdown",
    )

    response = client.chat.completions.create(
        model=selected_model,
        messages=build_messages(
            classification_path=classification_path,
            classification_data=classification_data,
            entitlements_path=entitlements_path,
            entitlements_markdown=entitlements_markdown,
            pseudocode_path=pseudocode_path,
            pseudocode_markdown=pseudocode_markdown,
        ),
    )

    output_text = extract_chat_completion_text(response)
    if not output_text:
        raise OvertimeQualityEvaluatorError(
            "OpenRouter response did not include output text."
        )

    destination = Path(output_path) if output_path else output_path_for_pseudocode(pseudocode_path)
    write_text_with_archive(destination, output_text)
    return output_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate overtime markdown artifacts against a payment classification JSON file."
        )
    )
    parser.add_argument(
        "--classification-path",
        default=str(DEFAULT_CLASSIFICATION_PATH),
        help="Path to the payment classification JSON file.",
    )
    parser.add_argument(
        "--entitlements-path",
        default=str(DEFAULT_ENTITLEMENTS_PATH),
        help="Path to the overtime entitlements markdown file.",
    )
    parser.add_argument(
        "--pseudocode-path",
        default=str(DEFAULT_PSEUDOCODE_PATH),
        help="Path to the core overtime pseudocode markdown file.",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown quality review output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenRouter model to use. Defaults to {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    evaluate_overtime_artifact_quality(
        classification_path=args.classification_path,
        entitlements_path=args.entitlements_path,
        pseudocode_path=args.pseudocode_path,
        output_path=args.output_path,
        model=args.model,
    )

    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_pseudocode(args.pseudocode_path)
    )
    print(f"Overtime artifact quality review saved to {destination}")


if __name__ == "__main__":
    main()
