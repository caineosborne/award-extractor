import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.output_paths import (
    OVERTIME_INTERPRETATIONS_DIR,
    OVERTIME_PSEUDOCODE_DIR,
    path_in_category,
    write_text_with_archive,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERTIME_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_INTERPRETATIONS_DIR
    / "MA000018_overtime_interpretation_revised.md"
)
DEFAULT_MODEL = "gpt-5.4-mini"

CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied overtime entitlement markdown into bullet-point pseudocode.
- Only classify whether worked hours are Ordinary_Hours or Overtime_Hours.
- Treat Unallocated_Hours as the total hours worked that still need ordinary/overtime classification, assume that no hours are preallocated. 
- For this task, any hours that are not ordinary hours are overtime.
- Preserve the business meaning of the overtime triggers in the markdown, even if headings or bullet formatting have been edited by a human.

The output will be passed to system engineers to configure payroll rules - it does not need explanations (beyond the clauses) simply the code is sufficient. 

Available fields:
{fields}

Constraints:
- Assume that you are reviewing the hours worked for a fortnight, none of these hours are currently classified as overtime or ordinary. Your task is to allocate the hours as ordinary or overtime.  You are recieving the the total hours worked for the fornight, no other hours worked. 
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts. The outputs need to simply contain the amount of hours allocated to overitme, and the amount of hours as ordinary. 
- If formulas refer to a specific time (eg penalties for working after 10PM) this may be stated as a derived field only where that calculation is genuinely needed and reused in more than one rule.

Do not say "IF block occurs on a day other than Monday to Friday OR block time is before 6:00 am OR block time is after 6:00 pm. Allocate that block hour to Overtime_Hours"

Say "If the shift ends after 6pm, or starts before 6am, or is worked on the weekend. Allocate any hours between shift end and 6pm as overtime"

Shift_Segments_By_Hour
- Use the plain-English overtime trigger section as the main source for ordinary/overtime classification.
- Do not rely on a rule having an exact markdown heading or bullet label. Read the complete document for meaning.
- Apply rules only to currently Unallocated_Hours.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining Unallocated_Hours to Ordinary_Hours after all overtime triggers have been applied.
- Include source clause references in comments.
- Do not create additional fields unnecessarily - for any clauses are are reliant on times, use the existing Shift Start and Shift End fields. 
- If a rule needs an input that is not in the available fields, name it under Required additional inputs. Any fields that can be derived from the supplied data should be included as a calucation, rather than an additional data point. 
- Do not list a derived field that is just a renamed component of an existing field. For example, do not derive `Shift_Start_Time` from `Shift_Start`, `Shift_End_Time` from `Shift_End`, or `Shift_Start_Day` from `Shift_Date` unless the source rule truly requires a different representation that is not already supplied.
- Do not list straightforward calculations as separate derived fields unless they are reused across multiple rules and make the pseudocode materially clearer. For example, totals such as hours worked in the day, week, or fortnight, hours over 10 in a day, or hours outside rostered hours should usually appear as calculations inside the pseudocode rather than as standalone derived fields.
- Treat derived fields as optional. Use the `Derived Fields` section only for non-obvious reusable calculations. If no such calculations are needed, write `None`.
- Treat `Required additional inputs` narrowly. Only include facts that are not already provided and cannot be calculated directly from the supplied fields and shift records.
- Use clear payroll variables. Do not invent vague helper variables such as offsets, safe offsets, magic masks, or placeholders that hide the calculation.
- If a rule requires segmenting a shift into hour blocks, state that as a required additional input and describe the segmentation plainly.
- Prefer simple step-by-step pseudocode over dense formulas.
- If the ruleset applies to all employees,then it is not necessary to specify the employee cohort - this is only necessary where clauses only target particular cohorts. Assume all employees are affected by all rules, unless otherwise stated. 
- Do not specify clauess within the psuedo code - use rulesets that technical teams can build without being aware of the award. 
- When determining the priority, ensure that all rulesets that affect outlier situations are processed first, followed by any rules time of days are processed first, before those reviewing total hours in a day, before those that affect a week, or those that affect a longer time period.  When listing the priority ensure that the rules here match what is shown in the pseudocode section. 
- Return markdown only.

Required markdown structure:

# Overtime pseudocode

## Derived Fields

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
    "Roster_Start": "The time the employees is rostered to start work.",
    "Roster_End": "The time the employee is rostered to end work.",  
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


def select_overtime_interpretation_path(
    source_path: Path | str = DEFAULT_OVERTIME_SUMMARY_PATH,
) -> Path:
    path = Path(source_path)

    if path.exists():
        return path

    stem = path.stem
    if stem.endswith("_overtime_interpretation_4b"):
        fallback_path = path.with_name(
            stem.removesuffix("_overtime_interpretation_4b")
            + "_overtime_interpretation_revised.md"
        )
        if fallback_path.exists():
            return fallback_path

    raise CoreOvertimePseudocodeError(f"Overtime interpretation markdown not found: {path}")


def default_overtime_interpretation_path(award_code: str) -> Path:
    interpretation_dir = (
        PROJECT_ROOT / "data" / "processed" / OVERTIME_INTERPRETATIONS_DIR
    )
    manual_4b_path = interpretation_dir / f"{award_code}_overtime_interpretation_4b.md"
    if manual_4b_path.exists():
        return manual_4b_path
    return interpretation_dir / f"{award_code}_overtime_interpretation_revised.md"


def load_overtime_interpretation(source_path: Path | str) -> str:
    path = select_overtime_interpretation_path(source_path)
    if not path.exists():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown not found: {path}"
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown is empty: {path}"
        )
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
    path = select_overtime_interpretation_path(summary_path)
    stem = path.stem
    if stem.endswith("_overtime_interpretation_4b"):
        stem = stem.removesuffix("_overtime_interpretation_4b")
    elif stem.endswith("_overtime_interpretation_revised"):
        stem = stem.removesuffix("_overtime_interpretation_revised")
    elif stem.endswith("_overtime_interpretation"):
        stem = stem.removesuffix("_overtime_interpretation")
    return path_in_category(
        path,
        OVERTIME_PSEUDOCODE_DIR,
        f"{stem}_core_overtime_pseudocode.md",
    )


def build_messages(
    source_file: str,
    overtime_summary_markdown: str,
) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE.format(fields=fields)
    user_prompt = (
        f"Source overtime interpretation markdown: {source_file}\n\n"
        "Complete overtime interpretation markdown to convert:\n"
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

    source_path = select_overtime_interpretation_path(summary_path)
    summary_text = load_overtime_interpretation(source_path)

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
        default=str(default_overtime_interpretation_path("MA000018")),
        help=(
            "Path to an overtime interpretation markdown file. "
            "Use the 4B file when present, otherwise the revised overtime interpretation."
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
