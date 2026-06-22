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


def looks_like_path(value: str) -> bool:
    """Return whether the value should be treated as a filesystem path."""
    path = Path(value)
    return path.suffix != "" or "/" in value or "\\" in value


def normalize_award_code(value: str) -> str:
    """Validate and normalize a Fair Work award code."""
    award_code = value.strip().upper()
    if not re.fullmatch(r"MA\d{6}", award_code):
        raise ValueError("award code must look like MA000120")
    return award_code


def default_award_url_for_code(award_code: str) -> str:
    """Build the default Fair Work award URL for an award code."""
    return DEFAULT_AWARD_URL_TEMPLATE.format(award_code=award_code)


def default_classification_path_for_award(award_code: str) -> Path:
    """Return the default step-2 classification artifact path for an award code."""
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / PAYMENT_CLAUSE_IDENTIFIER_DIR
        / f"{award_code}_payment_classification.json"
    )


def interpretation_output_path_for_classification(classification_path: Path | str) -> Path:
    """Derive the default step-3 interpretation path from a step-2 classification path."""
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")

    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_interpretation.md",
    )


def overtime_clause_classification_output_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Derive the default step-3 clause classification path from step-2 output."""
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")

    return path_in_category(
        path,
        OVERTIME_INTERPRETATIONS_DIR,
        f"{stem}_overtime_clause_classification.json",
    )


def award_code_from_interpretation_path(interpretation_path: Path | str) -> str:
    """Extract an award code from a standard step-3 interpretation filename."""
    stem = Path(interpretation_path).stem
    if stem.endswith("_overtime_interpretation"):
        return stem.removesuffix("_overtime_interpretation")
    if stem.endswith("_overtime_interpretation_revised"):
        return stem.removesuffix("_overtime_interpretation_revised")

    raise ValueError(
        "Could not derive award code from interpretation path. "
        "Pass --classification-path explicitly."
    )


def default_interpretation_path_for_award(award_code: str) -> Path:
    """Return the default step-3 interpretation artifact path for an award code."""
    return (
        PROJECT_ROOT
        / "data"
        / "processed"
        / OVERTIME_INTERPRETATIONS_DIR
        / f"{award_code}_overtime_interpretation.md"
    )


def resolve_interpretation_path(award_or_interpretation_path: Path | str) -> Path:
    """Resolve either an award code or an explicit interpretation path."""
    value = str(award_or_interpretation_path)
    if looks_like_path(value):
        return Path(value)

    return default_interpretation_path_for_award(value)


def resolve_classification_path(
    award_or_interpretation_path: Path | str,
    classification_path: Path | str | None,
) -> Path:
    """Resolve the step-2 classification path for review and generation steps."""
    if classification_path:
        return Path(classification_path)

    value = str(award_or_interpretation_path)
    award_code = value
    if looks_like_path(value):
        award_code = award_code_from_interpretation_path(value)

    return default_classification_path_for_award(award_code)


def resolve_overtime_clause_classification_path(
    classification_path: Path | str,
    overtime_clause_classification_path: Path | str | None,
) -> Path:
    """Resolve the step-3 clause classification path for review steps."""
    if overtime_clause_classification_path:
        return Path(overtime_clause_classification_path)

    return overtime_clause_classification_output_path_for_classification(
        classification_path
    )


def feedback_dir_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the feedback directory used for interpretation review artifacts."""
    return Path(interpretation_path).parent / OVERTIME_INTERPRETATION_FEEDBACK_DIR


def evaluator_feedback_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default evaluator feedback path for an interpretation file."""
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_evaluator_feedback.md"


def creator_response_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default creator decision record path for an interpretation file."""
    path = Path(interpretation_path)
    return feedback_dir_for_interpretation(path) / f"{path.stem}_creator_response.md"


def revised_output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default revised interpretation path for an interpretation file."""
    path = Path(interpretation_path)
    return path.with_name(f"{path.stem}_revised{path.suffix}")
