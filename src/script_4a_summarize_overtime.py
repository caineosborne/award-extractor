import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.common.output_paths import (
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    path_in_category,
    write_text_with_archive,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "resources" / "Template.md"
DEFAULT_AWARD_CODE = "MA000018"

FORMATTER_SYSTEM_PROMPT = """You convert an overtime interpretation working document into a polished
human-readable overtime guide.

Requirements:
- Use only the supplied interpretation document for award-specific facts.
- Follow the supplied template heading structure and heading order.
- Keep the output concise and easy to scan.
- Use short markdown bullet points under each heading.
- Preserve employee groups, thresholds, assumptions, and clause references from the source.
- Do not invent rules, clause references, or categories that are not supported by the source.
- If the source does not support a section in the template, leave a single bullet with `-`.
- Return markdown only.
- Do not wrap the answer in a markdown code fence.
"""


class OvertimeEntitlementSummaryError(RuntimeError):
    """Raised when the overtime formatter cannot complete its work."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeEntitlementSummaryError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_text_file(path: Path | str, description: str) -> str:
    selected_path = Path(path)
    if not selected_path.exists():
        raise OvertimeEntitlementSummaryError(f"{description} not found: {selected_path}")

    text = selected_path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeEntitlementSummaryError(f"{description} is empty: {selected_path}")

    return text


def looks_like_path(value: str) -> bool:
    path = Path(value)
    return path.suffix != "" or "/" in value or "\\" in value


def default_interpretation_path_for_award(award_code: str) -> Path:
    interpretation_dir = PROJECT_ROOT / "data" / "processed" / OVERTIME_INTERPRETATIONS_DIR
    revised_path = interpretation_dir / f"{award_code}_overtime_interpretation_revised.md"
    if revised_path.exists():
        return revised_path

    return interpretation_dir / f"{award_code}_overtime_interpretation.md"


def resolve_interpretation_path(award_or_interpretation_path: Path | str) -> Path:
    value = str(award_or_interpretation_path)
    if looks_like_path(value):
        return Path(value)

    return default_interpretation_path_for_award(value)


def output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    path = Path(interpretation_path)
    stem = path.stem

    if stem.endswith("_overtime_interpretation_revised"):
        stem = stem.removesuffix("_overtime_interpretation_revised")
    elif stem.endswith("_overtime_interpretation"):
        stem = stem.removesuffix("_overtime_interpretation")

    return path_in_category(
        path,
        OVERTIME_ENTITLEMENTS_DIR,
        f"{stem}_overtime_entitlements.md",
    )


def strip_wrapping_markdown_fence(text: str) -> str:
    stripped_text = text.strip()
    lines = stripped_text.splitlines()

    if len(lines) < 2:
        return stripped_text

    opening_line = lines[0].strip().lower()
    closing_line = lines[-1].strip()
    is_markdown_fence = opening_line in ("```markdown", "```md", "```")

    if is_markdown_fence and closing_line == "```":
        return "\n".join(lines[1:-1]).strip()

    return stripped_text


def build_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    template_path: Path | str,
    template_markdown: str,
) -> list[dict[str, str]]:
    user_prompt = f"""Format the supplied overtime interpretation into the supplied template.

Interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Template source: {template_path}

```markdown
{template_markdown}
```

Use the template headings exactly as provided. Replace placeholder bullets with source-based content.
Do not add headings outside the template. If a template section is not supported by the source,
leave a single bullet with `-`.
"""
    return [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    text_parts: list[str] = []

    for item in output:
        if getattr(item, "type", None) != "message":
            continue

        for content_item in getattr(item, "content", []):
            if getattr(content_item, "type", None) == "output_text":
                text = getattr(content_item, "text", "")
                if text:
                    text_parts.append(text)

    return "\n".join(text_parts).strip()


def summarize_overtime_entitlements(
    interpretation_path: Path | str,
    output_path: Path | str | None = None,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    selected_interpretation_path = Path(interpretation_path)
    selected_template_path = Path(template_path)

    interpretation_markdown = load_text_file(
        selected_interpretation_path,
        "Overtime interpretation markdown",
    )
    template_markdown = load_text_file(
        selected_template_path,
        "Template markdown",
    )

    response = client.responses.create(
        model=selected_model,
        input=build_messages(
            selected_interpretation_path,
            interpretation_markdown,
            selected_template_path,
            template_markdown,
        ),
    )
    output_text = extract_response_text(response)

    if not output_text:
        raise OvertimeEntitlementSummaryError("OpenAI response did not include output text.")

    cleaned_output = strip_wrapping_markdown_fence(output_text)
    destination = (
        Path(output_path)
        if output_path is not None
        else output_path_for_interpretation(selected_interpretation_path)
    )
    write_text_with_archive(destination, cleaned_output)
    return cleaned_output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Format a revised overtime interpretation into a polished markdown guide."
    )
    parser.add_argument(
        "award_or_interpretation_path",
        nargs="?",
        default=DEFAULT_AWARD_CODE,
        help=(
            "Award code such as MA000018, or a path to an overtime interpretation "
            "markdown file. Award codes prefer the revised interpretation file if it exists."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the formatted overtime markdown output.",
    )
    parser.add_argument(
        "--template-path",
        default=str(DEFAULT_TEMPLATE_PATH),
        help=f"Optional markdown template path. Defaults to {DEFAULT_TEMPLATE_PATH}.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to OVERTIME_ENTITLEMENT_SUMMARY_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    interpretation_path = resolve_interpretation_path(args.award_or_interpretation_path)
    summarize_overtime_entitlements(
        interpretation_path=interpretation_path,
        output_path=args.output_path,
        template_path=args.template_path,
        model=args.model,
    )

    destination = (
        Path(args.output_path)
        if args.output_path is not None
        else output_path_for_interpretation(interpretation_path)
    )
    print(f"Formatted overtime guide saved to {destination}")


if __name__ == "__main__":
    main()
