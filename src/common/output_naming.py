from __future__ import annotations

import re
from pathlib import Path

from src.common.output_paths import (
    OVERTIME_INTERPRETATION_FEEDBACK_DIR,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_URL_TEMPLATE = "https://awards.fairwork.gov.au/{award_code}.html"

ACTIVE_PIPELINE_STEP_CHOICES = ("1", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1")
DEFAULT_ACTIVE_PIPELINE_STEPS = ("1", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1")


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
    return award_dir_for_output_stem(output_stem) / "raw" / "1_1_raw.html"


def award_json_path_for_output_stem(output_stem: str) -> Path:
    """Return the default parsed award JSON path for one processed output set."""
    return award_dir_for_output_stem(output_stem) / "1_2_award.json"


def classification_path_for_award_json(award_json_path: Path | str) -> Path:
    """Return the default payment-classification path for one parsed award JSON file."""
    path = Path(award_json_path)
    return path.parent / "2_1_payment_classification.json"


def ruleset_short_label(ruleset_key: str) -> str:
    """Return the short ruleset label used in canonical filenames."""
    if ruleset_key == "overtime_creation":
        return "OT_creation"
    if ruleset_key == "overtime_consequence":
        return "OT_consequence"
    raise ValueError(f"Unsupported overtime ruleset: {ruleset_key}")


def clause_classification_path_for_ruleset(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 2.2 output path for one ruleset."""
    path = Path(classification_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / f"2_2_{short_label}_clause_classification.json"


def ruleset_markdown_path_for_ruleset(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 3.1 markdown output path for one ruleset."""
    path = Path(classification_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / f"3_1_{short_label}_ruleset.md"


def review_markdown_path_for_ruleset(
    interpretation_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 3.2 evaluator-review markdown path for one ruleset."""
    path = Path(interpretation_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / OVERTIME_INTERPRETATION_FEEDBACK_DIR / f"3_2_{short_label}_review.md"


def creator_response_markdown_path_for_ruleset(
    interpretation_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 3.2 creator-response markdown path for one ruleset."""
    path = Path(interpretation_path)
    short_label = ruleset_short_label(ruleset_key)
    return (
        path.parent
        / OVERTIME_INTERPRETATION_FEEDBACK_DIR
        / f"3_2_{short_label}_creator_response.md"
    )


def revised_ruleset_path_for_ruleset(
    interpretation_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 3.2 revised ruleset path for one ruleset."""
    path = Path(interpretation_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / f"3_2_{short_label}_revised_ruleset.md"


def formatted_ruleset_path_for_ruleset(
    interpretation_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 4.1 formatted ruleset path for one ruleset."""
    path = Path(interpretation_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / f"4_1_{short_label}_formatted_ruleset.md"


def pseudocode_path_for_ruleset(
    interpretation_path: Path | str,
    ruleset_key: str,
) -> Path:
    """Return the canonical step 5.1 pseudocode path for one ruleset."""
    path = Path(interpretation_path)
    short_label = ruleset_short_label(ruleset_key)
    return path.parent / f"5_1_{short_label}_pseudocode.md"


def interpretation_path_for_classification(classification_path: Path | str) -> Path:
    """Return the default interpretation path for one payment classification file."""
    return ruleset_markdown_path_for_ruleset(
        classification_path,
        "overtime_creation",
    )


def overtime_clause_classification_path_for_classification(
    classification_path: Path | str,
) -> Path:
    """Return the default overtime clause-classification path for one step-2 file."""
    return clause_classification_path_for_ruleset(
        classification_path,
        "overtime_creation",
    )


def feedback_dir_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the review-feedback directory for one interpretation file."""
    return Path(interpretation_path).parent / OVERTIME_INTERPRETATION_FEEDBACK_DIR


def evaluator_feedback_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default evaluator feedback path for one interpretation file."""
    path = Path(interpretation_path)
    stem = path.stem
    if stem == "3_1_OT_creation_ruleset":
        return review_markdown_path_for_ruleset(path, "overtime_creation")
    if stem == "3_1_OT_consequence_ruleset":
        return review_markdown_path_for_ruleset(path, "overtime_consequence")
    return feedback_dir_for_interpretation(path) / f"{path.stem}_evaluator_feedback.md"


def creator_response_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default creator response path for one interpretation file."""
    path = Path(interpretation_path)
    stem = path.stem
    if stem == "3_1_OT_creation_ruleset":
        return creator_response_markdown_path_for_ruleset(path, "overtime_creation")
    if stem == "3_1_OT_consequence_ruleset":
        return creator_response_markdown_path_for_ruleset(path, "overtime_consequence")
    return feedback_dir_for_interpretation(path) / f"{path.stem}_creator_response.md"


def revised_interpretation_path_for_interpretation(interpretation_path: Path | str) -> Path:
    """Return the default revised interpretation path for one interpretation file."""
    path = Path(interpretation_path)
    if path.stem == "3_1_OT_creation_ruleset":
        return revised_ruleset_path_for_ruleset(path, "overtime_creation")
    if path.stem == "3_1_OT_consequence_ruleset":
        return revised_ruleset_path_for_ruleset(path, "overtime_consequence")
    return path.with_name(f"{path.stem}_revised{path.suffix}")


def core_overtime_pseudocode_path_for_interpretation(
    interpretation_path: Path | str,
) -> Path:
    """Return the default step-5B pseudocode path for one reviewed interpretation."""
    path = Path(interpretation_path)
    stem = path.stem

    if stem in ("3_2_OT_creation_revised_ruleset", "4_1_OT_creation_formatted_ruleset"):
        return pseudocode_path_for_ruleset(path, "overtime_creation")

    if stem in (
        "3_2_OT_consequence_revised_ruleset",
        "4_1_OT_consequence_formatted_ruleset",
    ):
        return pseudocode_path_for_ruleset(path, "overtime_consequence")

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
