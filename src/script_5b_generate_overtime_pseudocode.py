import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.common.output_paths import (
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_PSEUDOCODE_DIR,
    path_in_category,
    write_text_with_archive,
)
from src.script_2_classify_payments import extract_response_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERTIME_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_ENTITLEMENTS_DIR
    / "MA000018_overtime_entitlements.md"
)
DEFAULT_MODEL = "gpt-5.4-mini"

CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied overtime entitlement markdown into bullet-point pseudocode.
- Only classify whether worked hours are Ordinary_Hours or Overtime_Hours.
- Treat Unallocated_Hours as the total hours worked that still need ordinary/overtime classification.
- For this task, any hours that are not ordinary hours are overtime.
- Preserve the business meaning of the overtime triggers in the markdown, even if headings or bullet formatting have been edited by a human.

Available fields:
{fields}

Constraints:
- Focus on core payments only: if an hour is worked, decide whether it is ordinary or overtime.
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts.
- Do not stack a penalty or allowance with overtime unless the entitlement summary expressly says that affects the hour classification.
- Use the plain-English overtime trigger section as the main source for ordinary/overtime classification.
- Use payment consequences, other considerations, clause interpretation, and assumptions only where they clarify whether an hour is ordinary or overtime.
- Do not rely on a rule having an exact markdown heading or bullet label. Read the complete document for meaning.
- Apply rules only to currently Unallocated_Hours.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining Unallocated_Hours to Ordinary_Hours after all overtime triggers have been applied.
- Include source clause references in comments.
- If a rule needs an input that is not in the available fields, name it under Required additional inputs.
- Use clear payroll variables. Do not invent vague helper variables such as offsets, safe offsets, magic masks, or placeholders that hide the calculation.
- If a rule requires segmenting a shift into hour blocks, state that as a required additional input and describe the segmentation plainly.
- Prefer simple step-by-step pseudocode over dense formulas.
- Return markdown only.

Required markdown structure:

# Overtime pseudocode

## Required additional inputs

## Rule priority

## Pseudocode

## Implementation notes
"""

PSEUDOCODE_FIELDS = {
    "Shift_Date": "The calendar date on which the shift starts.",
    "Shift_Day": "The named day associated with the shift.",
    "Shift_Start": "The shift start time.",
    "Shift_End": "The shift end time.",
    "Day_of_Week": "The day of the week for the shift date.",
    "Employee Type - Shift Worker/Day Worker": (
        "Whether the employee is classified as a shift worker or day worker."
    ),
    "Employee Type - Full Time/PartTime/Casual": (
        "Whether the employee is full-time, part-time, or casual."
    ),
    "Unallocated_Hours": (
        "The hours in the shift that have not yet been allocated by another clause."
    ),
}


class CoreOvertimePseudocodeError(RuntimeError):
    """Base exception for core overtime pseudocode failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise CoreOvertimePseudocodeError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_overtime_summary(summary_path: Path | str) -> str:
    path = Path(summary_path)
    if not path.exists():
        raise CoreOvertimePseudocodeError(f"Overtime summary markdown not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise CoreOvertimePseudocodeError(f"Overtime summary markdown is empty: {path}")
    return text


def first_top_level_bullets(markdown: str, count: int = 5) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- "):
            if current:
                selected.append("\n".join(current))
                if len(selected) == count:
                    break
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)

    if len(selected) < count and current:
        selected.append("\n".join(current))

    if len(selected) < count:
        raise CoreOvertimePseudocodeError(
            f"Expected at least {count} top-level bullets, found {len(selected)}."
        )

    return "\n".join(selected[:count])


def overtime_rule_bullets(markdown: str) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- Overtime - "):
            if current:
                selected.append("\n".join(current))
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)
            continue

        if current and line.startswith("- "):
            selected.append("\n".join(current))
            current = []

    if current:
        selected.append("\n".join(current))

    if not selected:
        raise CoreOvertimePseudocodeError(
            "Expected at least one top-level 'Overtime - ' entitlement bullet."
        )

    return "\n".join(selected)


def output_path_for_summary(summary_path: Path | str) -> Path:
    path = Path(summary_path)
    stem = path.stem
    if stem.endswith("_overtime_entitlements"):
        stem = stem.removesuffix("_overtime_entitlements")
    return path_in_category(
        path,
        OVERTIME_PSEUDOCODE_DIR,
        f"{stem}_core_overtime_pseudocode.md",
    )


def build_messages(source_file: str, overtime_summary_markdown: str) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE.format(fields=fields)
    user_prompt = (
        f"Source overtime entitlement summary: {source_file}\n\n"
        "Complete overtime entitlement markdown to convert:\n"
        f"{overtime_summary_markdown}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_core_overtime_pseudocode(
    summary_path: Path | str = DEFAULT_OVERTIME_SUMMARY_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("CORE_OVERTIME_PSEUDOCODE_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(summary_path)
    summary_text = load_overtime_summary(source_path)

    try:
        response = client.responses.create(
            model=selected_model,
            input=build_messages(str(source_path), summary_text),
        )
    except Exception as exc:
        raise CoreOvertimePseudocodeError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise CoreOvertimePseudocodeError("OpenAI response did not include output text.")

    destination = Path(output_path) if output_path else output_path_for_summary(source_path)
    write_text_with_archive(destination, output_text)
    return output_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate core ordinary/overtime pseudocode from an overtime entitlement summary."
    )
    parser.add_argument(
        "summary_path",
        nargs="?",
        default=str(DEFAULT_OVERTIME_SUMMARY_PATH),
        help=(
            "Path to an overtime entitlements markdown file, for example "
            "data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown core overtime pseudocode output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to CORE_OVERTIME_PSEUDOCODE_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    generate_core_overtime_pseudocode(
        summary_path=args.summary_path,
        output_path=args.output_path,
        model=args.model,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_summary(args.summary_path)
    )
    print(f"Core overtime pseudocode saved to {destination}")


if __name__ == "__main__":
    main()
