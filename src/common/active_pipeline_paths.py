from __future__ import annotations

import re
from pathlib import Path

from src.common.output_naming import (
    DEFAULT_AWARD_URL_TEMPLATE,
    PROJECT_ROOT,
    award_dir_for_output_stem,
    creator_response_path_for_interpretation as naming_creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation as naming_evaluator_feedback_path_for_interpretation,
    feedback_dir_for_interpretation as naming_feedback_dir_for_interpretation,
    interpretation_path_for_classification,
    overtime_clause_classification_path_for_classification,
    revised_interpretation_path_for_interpretation,
)
from src.common.output_paths import (
    award_output_dir,
)
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    explicit_ruleset_output_path,
)


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
    award_dir = award_dir_for_output_stem(award_code)
    return award_dir / "2_1_payment_classification.json"


def interpretation_output_path_for_classification(classification_path: Path | str) -> Path:
    """Derive the default step-3 interpretation path from a step-2 classification path."""
    return interpretation_path_for_classification(
        classification_path,
    )


def ruleset_output_path_for_classification(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Derive the explicit ruleset output path from a step-2 classification path."""
    return explicit_ruleset_output_path(classification_path, ruleset_key)


def overtime_clause_classification_output_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Derive the default step-3 clause classification path from step-2 output."""
    return overtime_clause_classification_path_for_classification(
        classification_path,
    )


def ruleset_clause_classification_output_path_for_classification(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical clause-classification path shared by all rulesets."""
    del ruleset_key
    return overtime_clause_classification_output_path_for_classification(
        classification_path
    )


def award_code_from_interpretation_path(interpretation_path: Path | str) -> str:
    """Extract an award code from a standard step-3 interpretation filename."""
    path = Path(interpretation_path)
    award_dir = award_output_dir(path)
    if award_dir.name:
        return award_dir.name

    raise ValueError(
        "Could not derive award code from interpretation path. "
        "Pass --classification-path explicitly."
    )


def default_interpretation_path_for_award(award_code: str) -> Path:
    """Return the default step-3 interpretation artifact path for an award code."""
    award_dir = award_dir_for_output_stem(award_code)
    return award_dir / "3_1_OT_creation_ruleset.md"


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
    interpretation_path: Path | str | None = None,
) -> Path:
    """Resolve the step-3 clause classification path for review steps."""
    if overtime_clause_classification_path:
        return Path(overtime_clause_classification_path)
    del interpretation_path
    return overtime_clause_classification_output_path_for_classification(
        classification_path
    )


def feedback_dir_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the feedback directory used for interpretation review artifacts."""
    return naming_feedback_dir_for_interpretation(interpretation_path)


def evaluator_feedback_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default evaluator feedback path for an interpretation file."""
    return naming_evaluator_feedback_path_for_interpretation(interpretation_path)


def creator_response_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default creator decision record path for an interpretation file."""
    return naming_creator_response_path_for_interpretation(interpretation_path)


def revised_output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default revised interpretation path for an interpretation file."""
    return revised_interpretation_path_for_interpretation(interpretation_path)


def manual_ruleset_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default manually edited ruleset path for an interpretation file."""
    path = Path(interpretation_path)
    return path.with_name(f"{path.stem}_manual.md")


def preferred_step_5_source_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the preferred step 5.1 source path, using a manual ruleset when present."""
    revised_path = Path(interpretation_path)
    manual_ruleset_path = manual_ruleset_path_for_interpretation(revised_path)
    if manual_ruleset_path.exists():
        return manual_ruleset_path
    return revised_path
