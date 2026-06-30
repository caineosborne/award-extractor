from datetime import datetime
from pathlib import Path
import re


FETCH_AWARD_DIR = "1_fetch_award"
FETCH_AWARD_SUPPORTING_DIR = "supporting"
PAYMENT_CLAUSE_IDENTIFIER_DIR = "2_payment_clause_identifier"
OVERTIME_INTERPRETATIONS_DIR = "3_overtime_interpretations"
OVERTIME_INTERPRETATION_FEEDBACK_DIR = "feedback"
OVERTIME_ENTITLEMENTS_DIR = "4a_overtime_entitlements"
OVERTIME_PSEUDOCODE_DIR = "5b_generate_overtime_pseudocode"
OVERTIME_REVIEW_DIR = "6_final_consistency_review"
ARCHIVE_DIR = "archive"
RAW_DIR = "raw"

LEGACY_CATEGORY_DIRS = {
    FETCH_AWARD_DIR,
    PAYMENT_CLAUSE_IDENTIFIER_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_PSEUDOCODE_DIR,
    OVERTIME_REVIEW_DIR,
}

NON_AWARD_SUBDIRECTORIES = {
    ARCHIVE_DIR,
    FETCH_AWARD_SUPPORTING_DIR,
    OVERTIME_INTERPRETATION_FEEDBACK_DIR,
    RAW_DIR,
    "_streamlit_pipeline_runs",
    "_source_registry",
}

ARTIFACT_SUFFIXES = (
    "_overtime_consequence_ruleset_core_overtime_pseudocode_validation",
    "_overtime_consequence_ruleset_core_overtime_pseudocode",
    "_overtime_consequence_ruleset_overtime_entitlements",
    "_overtime_consequence_ruleset_revised",
    "_overtime_consequence_ruleset_expert_a",
    "_overtime_consequence_ruleset_expert_b",
    "_overtime_consequence_ruleset",
    "_overtime_consequence_clause_classification",
    "_overtime_creation_ruleset_core_overtime_pseudocode_validation",
    "_overtime_creation_ruleset_core_overtime_pseudocode",
    "_overtime_creation_ruleset_overtime_entitlements",
    "_overtime_creation_ruleset_revised",
    "_overtime_creation_ruleset_expert_a",
    "_overtime_creation_ruleset_expert_b",
    "_overtime_creation_ruleset",
    "_overtime_creation_clause_classification",
    "_overtime_interpretation_revised_overtime_entitlements",
    "_overtime_entitlements_review_feedback",
    "_overtime_entitlements_updated_answer",
    "_overtime_entitlements_initial_answer",
    "_overtime_entitlements_final",
    "_core_overtime_pseudocode_validation",
    "_core_overtime_pseudocode",
    "_overtime_interpretation_agentic_review_conversation",
    "_overtime_interpretation_evaluator_feedback",
    "_overtime_interpretation_creator_response",
    "_overtime_interpretation_comparison",
    "_overtime_interpretation_expert_a",
    "_overtime_interpretation_expert_b",
    "_overtime_interpretation_revised",
    "_overtime_interpretation_4b",
    "_overtime_interpretation",
    "_overtime_clause_classification",
    "_payment_classificationOriginal",
    "_payment_classification",
    "_overtime_entitlements",
    "_excluded",
    "_excluded_sections",
    "_diagnostics",
    "_sections",
)

ARCHIVE_TIMESTAMP_PATTERN = re.compile(r"_(\d{8}_\d{6})$")


def processed_root_for(path: Path | str) -> Path:
    """Return the data/processed directory that owns an output path.

    Project outputs are grouped under data/processed/<category>. When tests or
    ad hoc callers use a temporary directory without a processed segment, that
    temporary directory is treated as the root so the same layout is still used.
    """
    selected_path = Path(path)
    for index, part in enumerate(selected_path.parts):
        if part == "processed":
            return Path(*selected_path.parts[: index + 1])
    if selected_path.suffix:
        return selected_path.parent
    return selected_path


def output_set_name_for_stem(stem: str) -> str:
    """Return the output-set identifier stored in one artifact filename stem."""
    match = ARCHIVE_TIMESTAMP_PATTERN.search(stem)
    if match is not None:
        stem = stem[: match.start()]

    for suffix in ARTIFACT_SUFFIXES:
        if stem.endswith(suffix):
            return stem.removesuffix(suffix)

    return stem


def output_set_name_for_path(path: Path | str) -> str:
    """Return the output-set identifier for one path under data/processed."""
    selected_path = Path(path)

    for index, part in enumerate(selected_path.parts):
        if part != "processed":
            continue

        remaining_parts = selected_path.parts[index + 1 :]
        if not remaining_parts:
            break

        first_part = remaining_parts[0]
        if len(remaining_parts) == 1 and Path(first_part).suffix:
            break
        if first_part not in LEGACY_CATEGORY_DIRS and first_part not in NON_AWARD_SUBDIRECTORIES:
            return first_part
        break

    return output_set_name_for_stem(selected_path.stem)


def award_output_dir(reference_path: Path | str) -> Path:
    """Return the award-first directory for one processed artifact reference."""
    reference = Path(reference_path)
    processed_root = processed_root_for(reference)
    output_set_name = output_set_name_for_path(reference)
    return processed_root / output_set_name


def category_dir(reference_path: Path | str, category: str) -> Path:
    del category
    return award_output_dir(reference_path)


def path_in_category(reference_path: Path | str, category: str, filename: str) -> Path:
    return category_dir(reference_path, category) / filename


def timestamped_archive_path(output_path: Path | str, timestamp: datetime | None = None) -> Path:
    path = Path(output_path)
    selected_timestamp = timestamp or datetime.now()
    suffix = selected_timestamp.strftime("%Y%m%d_%H%M%S")
    return path.parent / ARCHIVE_DIR / f"{path.stem}_{suffix}{path.suffix}"


def write_text_with_archive(
    output_path: Path | str,
    text: str,
    timestamp: datetime | None = None,
) -> Path:
    """Write the latest output and a timestamped archive copy."""
    path = Path(output_path)
    archive_path = timestamped_archive_path(path, timestamp)

    path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(text, encoding="utf-8")
    archive_path.write_text(text, encoding="utf-8")

    return archive_path
