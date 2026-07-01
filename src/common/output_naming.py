from __future__ import annotations

import re
from pathlib import Path

from src.common.output_paths import (
    OVERTIME_INTERPRETATION_FEEDBACK_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    path_in_category,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_URL_TEMPLATE = "https://awards.fairwork.gov.au/{award_code}.html"

ACTIVE_PIPELINE_STEP_CHOICES = ("1", "2.1", "2.2", "3", "3b", "4", "5b")
DEFAULT_ACTIVE_PIPELINE_STEPS = ("1", "2.1", "2.2", "3", "3b")

FUTURE_PIPELINE_STEP_IDS = (
    "1.1",
    "1.2",
    "2.1",
    "2.2",
    "3.1",
    "3.2",
    "4.1",
    "5.1",
)


def default_award_url_for_code(award_code: str) -> str:
    """Build the default Fair Work award URL for an award code."""
    return DEFAULT_AWARD_URL_TEMPLATE.format(award_code=award_code)


def normalize_output_suffix(value: str | None) -> str | None:
    """Normalize an optional filename suffix used for processed outputs."""
    if value is None:
        return None

    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    suffix = suffix.strip("._-")
    if not suffix:
        raise ValueError("suffix must contain at least one letter or digit")

    return suffix


def output_stem_for_award(award_code: str, suffix: str | None) -> str:
    """Build the shared filename stem for one processed output set."""
    if suffix:
        return f"{award_code}_{suffix}"
    return award_code


def processed_root() -> Path:
    """Return the root directory that owns processed pipeline outputs."""
    return PROJECT_ROOT / "data" / "processed"


def award_dir_for_output_stem(output_stem: str) -> Path:
    """Return the award-first directory for one processed output set."""
    return processed_root() / output_stem


def raw_html_path_for_output_stem(output_stem: str) -> Path:
    """Return the default raw HTML path for one processed output set."""
    return award_dir_for_output_stem(output_stem) / "raw" / f"{output_stem}.html"


def award_json_path_for_output_stem(output_stem: str) -> Path:
    """Return the default parsed award JSON path for one processed output set."""
    return award_dir_for_output_stem(output_stem) / f"{output_stem}.json"


def classification_path_for_award_json(award_json_path: Path | str) -> Path:
    """Return the default payment-classification path for one parsed award JSON file."""
    path = Path(award_json_path)
    return path_in_category(
        path,
        PAYMENT_CLAUSE_IDENTIFIER_DIR,
        f"{path.stem}_payment_classification.json",
    )


def interpretation_path_for_classification(classification_path: Path | str) -> Path:
    """Return the default interpretation path for one payment classification file."""
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")

    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_interpretation.md",
    )


def overtime_clause_classification_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Return the default overtime clause-classification path for one step-2 file."""
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")

    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_clause_classification.json",
    )


def feedback_dir_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the review-feedback directory for one interpretation file."""
    return Path(interpretation_path).parent / OVERTIME_INTERPRETATION_FEEDBACK_DIR


def evaluator_feedback_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default evaluator feedback path for one interpretation file."""
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_evaluator_feedback.md"


def creator_response_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default creator response path for one interpretation file."""
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_creator_response.md"


def revised_interpretation_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default revised interpretation path for one interpretation file."""
    path = Path(interpretation_path)
    return path.with_name(f"{path.stem}_revised{path.suffix}")


def core_overtime_pseudocode_path_for_interpretation(
    interpretation_path: Path | str,
) -> Path:
    """Return the default step-5B pseudocode path for one reviewed interpretation."""
    path = Path(interpretation_path)
    stem = path.stem

    if stem.endswith("_overtime_creation_ruleset_revised"):
        base_stem = stem.removesuffix("_overtime_creation_ruleset_revised")
        return path.with_name(
            f"{base_stem}_overtime_creation_ruleset_core_overtime_pseudocode.md"
        )

    if stem.endswith("_overtime_consequence_ruleset_revised"):
        base_stem = stem.removesuffix("_overtime_consequence_ruleset_revised")
        return path.with_name(
            f"{base_stem}_overtime_consequence_ruleset_core_overtime_pseudocode.md"
        )

    if stem.endswith("_overtime_interpretation_revised"):
        base_stem = stem.removesuffix("_overtime_interpretation_revised")
        return path.with_name(f"{base_stem}_core_overtime_pseudocode.md")

    return path.with_name(f"{stem}_core_overtime_pseudocode.md")


def validation_json_path_for_pseudocode(pseudocode_path: Path | str) -> Path:
    """Return the JSON validation path for one pseudocode file."""
    path = Path(pseudocode_path)
    return path.with_name(f"{path.stem}_validation.json")


def validation_markdown_path_for_pseudocode(pseudocode_path: Path | str) -> Path:
    """Return the markdown validation path for one pseudocode file."""
    path = Path(pseudocode_path)
    return path.with_name(f"{path.stem}_validation.md")
