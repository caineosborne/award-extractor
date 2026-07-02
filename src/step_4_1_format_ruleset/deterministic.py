"""Deterministic helpers for step 4.1 ruleset formatting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.output_naming import formatted_ruleset_path_for_ruleset
from src.common.output_paths import award_output_dir, write_text_output
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.common.pipeline_io import load_text_file as load_required_text_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_CODE = "MA000018"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "resources" / "Templates" / "Template.md"


class OvertimeEntitlementSummaryError(RuntimeError):
    """Raised when the overtime formatter cannot complete its work."""


@dataclass(frozen=True)
class Step4FormattingInputs:
    """Prepared deterministic inputs for step 4.1 formatting."""

    interpretation_path: Path
    template_path: Path
    output_path: Path
    ruleset_key: str
    interpretation_markdown: str
    template_markdown: str


def load_text_file(path: Path | str, description: str) -> str:
    """Load one required text file for step 4.1."""
    return load_required_text_file(
        path,
        description,
        error_type=OvertimeEntitlementSummaryError,
    )


def strip_wrapping_markdown_fence(text: str) -> str:
    """Remove a surrounding markdown code fence from one response."""
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


def strip_validation_notes_preamble(text: str) -> str:
    """Remove the saved validation-notes block before formatting the interpretation."""
    stripped_text = text.strip()
    if not stripped_text.startswith("# Validation notes"):
        return stripped_text

    lines = stripped_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "\n".join(lines[index:]).strip()

    return stripped_text


def looks_like_path(value: str) -> bool:
    """Return whether one value looks like a filesystem path."""
    path = Path(value)
    return path.suffix != "" or "/" in value or "\\" in value


def default_interpretation_path_for_award(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    """Return the preferred interpretation source for one award code."""
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_interpretation.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        explicit_revised_path = award_dir / "3_2_OT_creation_revised_ruleset.md"
        if explicit_revised_path.exists():
            return explicit_revised_path
        return award_dir / "3_1_OT_creation_ruleset.md"
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        explicit_revised_path = award_dir / "3_2_OT_consequence_revised_ruleset.md"
        if explicit_revised_path.exists():
            return explicit_revised_path
        return award_dir / "3_1_OT_consequence_ruleset.md"
    revised_path = award_dir / "3_2_OT_creation_revised_ruleset.md"
    if revised_path.exists():
        return revised_path

    return award_dir / "3_1_OT_creation_ruleset.md"


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

    if stem == "3_2_OT_creation_revised_ruleset":
        return formatted_ruleset_path_for_ruleset(path, OVERTIME_CREATION_RULESET)

    if stem == "3_2_OT_consequence_revised_ruleset":
        return formatted_ruleset_path_for_ruleset(path, OVERTIME_CONSEQUENCE_RULESET)
    raise OvertimeEntitlementSummaryError(
        "Step 4.1 expects a canonical revised ruleset path such as "
        "`3_2_OT_creation_revised_ruleset.md` or "
        "`3_2_OT_consequence_revised_ruleset.md`."
    )


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
    write_text_output(destination, cleaned_output)
    return cleaned_output
