"""Deterministic helpers for step 4.1 ruleset formatting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.output_paths import award_output_dir, write_text_with_archive
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.script_4a_summarize_overtime import (
    DEFAULT_AWARD_CODE,
    DEFAULT_TEMPLATE_PATH,
    OvertimeEntitlementSummaryError,
    load_text_file,
    looks_like_path,
    strip_validation_notes_preamble,
    strip_wrapping_markdown_fence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Step4FormattingInputs:
    """Prepared deterministic inputs for step 4.1 formatting."""

    interpretation_path: Path
    template_path: Path
    output_path: Path
    ruleset_key: str
    interpretation_markdown: str
    template_markdown: str


def default_interpretation_path_for_award(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    """Return the preferred interpretation source for one award code."""
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_interpretation.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        explicit_revised_path = award_dir / f"{award_code}_overtime_creation_ruleset_revised.md"
        if explicit_revised_path.exists():
            return explicit_revised_path
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        explicit_revised_path = award_dir / f"{award_code}_overtime_consequence_ruleset_revised.md"
        if explicit_revised_path.exists():
            return explicit_revised_path
    revised_path = award_dir / f"{award_code}_overtime_interpretation_revised.md"
    if revised_path.exists():
        return revised_path

    return award_dir / f"{award_code}_overtime_interpretation.md"


def resolve_interpretation_path(
    award_or_interpretation_path: Path | str,
    ruleset_key: str | None = None,
) -> Path:
    """Resolve either an award code or an explicit interpretation path."""
    value = str(award_or_interpretation_path)
    if looks_like_path(value):
        return Path(value)

    return default_interpretation_path_for_award(value, ruleset_key)


def output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Build the canonical formatted output path for one interpretation."""
    path = Path(interpretation_path)
    stem = path.stem

    if stem.endswith("_overtime_creation_ruleset_revised"):
        stem = stem.removesuffix("_overtime_creation_ruleset_revised")
        return path.with_name(f"{stem}_overtime_creation_ruleset_overtime_entitlements.md")

    if stem.endswith("_overtime_consequence_ruleset_revised"):
        stem = stem.removesuffix("_overtime_consequence_ruleset_revised")
        return path.with_name(
            f"{stem}_overtime_consequence_ruleset_overtime_entitlements.md"
        )

    if stem.endswith("_overtime_interpretation_revised"):
        stem = stem.removesuffix("_overtime_interpretation_revised")
    elif stem.endswith("_overtime_interpretation"):
        stem = stem.removesuffix("_overtime_interpretation")

    return award_output_dir(path) / f"{stem}_overtime_entitlements.md"


def resolve_formatting_inputs(
    *,
    interpretation_path: Path | str = DEFAULT_AWARD_CODE,
    output_path: Path | str | None = None,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    ruleset_key: str | None = None,
) -> Step4FormattingInputs:
    """Load and validate the deterministic inputs for step 4.1."""
    selected_interpretation_path = resolve_interpretation_path(
        interpretation_path,
        ruleset_key,
    )
    selected_template_path = Path(template_path)
    try:
        effective_ruleset_key = ruleset_key or infer_overtime_ruleset_key_from_path(
            selected_interpretation_path
        )
    except ValueError:
        effective_ruleset_key = OVERTIME_CREATION_RULESET

    interpretation_markdown = load_text_file(
        selected_interpretation_path,
        "Overtime interpretation markdown",
    )
    interpretation_markdown = strip_validation_notes_preamble(interpretation_markdown)
    template_markdown = load_text_file(
        selected_template_path,
        "Template markdown",
    )
    destination = (
        Path(output_path)
        if output_path is not None
        else output_path_for_interpretation(selected_interpretation_path)
    )
    return Step4FormattingInputs(
        interpretation_path=selected_interpretation_path,
        template_path=selected_template_path,
        output_path=destination,
        ruleset_key=effective_ruleset_key,
        interpretation_markdown=interpretation_markdown,
        template_markdown=template_markdown,
    )


def write_formatted_output(destination: Path, output_text: str) -> str:
    """Clean and write the formatted ruleset output."""
    cleaned_output = strip_wrapping_markdown_fence(output_text)
    write_text_with_archive(destination, cleaned_output)
    return cleaned_output
