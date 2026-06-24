import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.output_paths import ARCHIVE_DIR, write_text_with_archive
from src.script_4a_summarize_overtime import output_path_for_interpretation
from src.script_5b_validate_overtime_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
PAYMENT_CLASSIFICATION_DIR = PROCESSED_ROOT / "2_payment_clause_identifier"
OVERTIME_INTERPRETATION_DIR = PROCESSED_ROOT / "3_overtime_interpretations"
OVERTIME_FEEDBACK_DIR = OVERTIME_INTERPRETATION_DIR / "feedback"


@dataclass(frozen=True)
class ArtifactPaths:
    payment_classification: Path
    overtime_clause_classification: Path
    original_overtime_interpretation: Path
    original_overtime_interpretation_expert_a: Path
    original_overtime_interpretation_expert_b: Path
    original_overtime_interpretation_comparison: Path
    agentic_review_conversation: Path
    evaluator_feedback: Path
    creator_response: Path
    revised_overtime_interpretation: Path
    overtime_entitlements: Path
    manual_4b_overtime_interpretation: Path
    core_overtime_pseudocode: Path
    core_overtime_validation_json: Path
    core_overtime_validation_markdown: Path
    original_overtime_rules_json: Path = field(default_factory=lambda: Path("__missing__"))
    evaluator_feedback_json: Path = field(default_factory=lambda: Path("__missing__"))
    creator_response_json: Path = field(default_factory=lambda: Path("__missing__"))
    revised_overtime_rules_json: Path = field(default_factory=lambda: Path("__missing__"))


@dataclass(frozen=True)
class FileContent:
    path: Path
    exists: bool
    text: str


def discover_award_codes(payment_classification_dir: Path = PAYMENT_CLASSIFICATION_DIR) -> list[str]:
    if not payment_classification_dir.exists():
        return []

    award_codes = []

    for path in payment_classification_dir.glob("*_payment_classification.json"):
        award_code = path.name.removesuffix("_payment_classification.json")
        award_codes.append(award_code)

    return sorted(award_codes)


def artifact_paths_for_award(award_code: str) -> ArtifactPaths:
    return ArtifactPaths(
        payment_classification=PAYMENT_CLASSIFICATION_DIR
        / f"{award_code}_payment_classification.json",
        overtime_clause_classification=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_clause_classification.json",
        original_overtime_interpretation=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation.md",
        original_overtime_interpretation_expert_a=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_expert_a.md",
        original_overtime_interpretation_expert_b=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_expert_b.md",
        original_overtime_interpretation_comparison=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_comparison.json",
        original_overtime_rules_json=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation.json",
        agentic_review_conversation=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_agentic_review_conversation.md",
        evaluator_feedback=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_evaluator_feedback.md",
        evaluator_feedback_json=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_evaluator_feedback.json",
        creator_response=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_creator_response.md",
        creator_response_json=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_creator_response.json",
        revised_overtime_interpretation=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_revised.md",
        revised_overtime_rules_json=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_revised.json",
        overtime_entitlements=output_path_for_interpretation(
            OVERTIME_INTERPRETATION_DIR / f"{award_code}_overtime_interpretation_revised.md"
        ),
        manual_4b_overtime_interpretation=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_4b.md",
        core_overtime_pseudocode=PROCESSED_ROOT
        / "5b_generate_overtime_pseudocode"
        / f"{award_code}_core_overtime_pseudocode.md",
        core_overtime_validation_json=validation_json_path_for_pseudocode(
            PROCESSED_ROOT
            / "5b_generate_overtime_pseudocode"
            / f"{award_code}_core_overtime_pseudocode.md"
        ),
        core_overtime_validation_markdown=validation_markdown_path_for_pseudocode(
            PROCESSED_ROOT
            / "5b_generate_overtime_pseudocode"
            / f"{award_code}_core_overtime_pseudocode.md"
        ),
    )


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def read_text_file(path: Path) -> FileContent:
    if not path.exists():
        return FileContent(path=path, exists=False, text="")

    return FileContent(path=path, exists=True, text=path.read_text(encoding="utf-8"))


def write_text_file_with_archive(path: Path, text: str) -> Path:
    return write_text_with_archive(path, text)


def source_path_for_manual_4b_editor(artifact_paths: ArtifactPaths) -> Path:
    if artifact_paths.manual_4b_overtime_interpretation.exists():
        return artifact_paths.manual_4b_overtime_interpretation

    if artifact_paths.overtime_entitlements.exists():
        return artifact_paths.overtime_entitlements

    if artifact_paths.revised_overtime_interpretation.exists():
        return artifact_paths.revised_overtime_interpretation

    return artifact_paths.original_overtime_interpretation


def source_path_for_core_overtime_pseudocode(artifact_paths: ArtifactPaths) -> Path:
    if artifact_paths.manual_4b_overtime_interpretation.exists():
        return artifact_paths.manual_4b_overtime_interpretation

    if artifact_paths.overtime_entitlements.exists():
        return artifact_paths.overtime_entitlements

    revised_rules_json = getattr(
        artifact_paths,
        "revised_overtime_rules_json",
        artifact_paths.revised_overtime_interpretation.with_suffix(".json"),
    )
    if revised_rules_json.exists():
        return revised_rules_json
    if artifact_paths.revised_overtime_interpretation.exists():
        return artifact_paths.revised_overtime_interpretation

    original_rules_json = getattr(
        artifact_paths,
        "original_overtime_rules_json",
        artifact_paths.original_overtime_interpretation.with_suffix(".json"),
    )
    if original_rules_json.exists():
        return original_rules_json
    return artifact_paths.original_overtime_interpretation


def last_modified_at(path: Path) -> datetime | None:
    if not path.exists():
        return None

    return datetime.fromtimestamp(path.stat().st_mtime)


def format_last_modified_for_display(path: Path) -> str:
    modified_at = last_modified_at(path)
    if modified_at is None:
        return "File not found"

    return modified_at.strftime("%Y-%m-%d %H:%M:%S")


def processed_files_matching_prefix(
    prefix: str,
    processed_root: Path = PROCESSED_ROOT,
) -> list[Path]:
    selected_prefix = prefix.strip()
    if not selected_prefix:
        return []

    matching_paths: list[Path] = []

    for path in processed_root.rglob("*"):
        if not path.is_file():
            continue

        if ARCHIVE_DIR in path.parts:
            continue

        if path.name.startswith(selected_prefix):
            matching_paths.append(path)

    return sorted(matching_paths)


def delete_processed_files_matching_prefix(
    prefix: str,
    processed_root: Path = PROCESSED_ROOT,
) -> list[Path]:
    selected_prefix = prefix.strip()
    if not selected_prefix:
        raise ValueError("A non-empty prefix is required.")

    matching_paths = processed_files_matching_prefix(
        selected_prefix,
        processed_root=processed_root,
    )

    for path in matching_paths:
        path.unlink()

    return matching_paths


def l1_clause_keys(payment_classification: dict[str, Any]) -> list[str]:
    top_level_clauses = payment_classification.get("top_level_clauses", {})
    return list(top_level_clauses.keys())


def l2_clause_keys(payment_classification: dict[str, Any]) -> list[str]:
    classified_clauses = payment_classification.get("classified_clauses", {})
    return list(classified_clauses.keys())


def overtime_classification_keys(overtime_classification: dict[str, Any]) -> list[str]:
    clauses = overtime_classification.get("clauses", [])
    return [str(clause.get("clause_number", "")) for clause in clauses]


def l1_record(payment_classification: dict[str, Any], clause_key: str) -> dict[str, Any]:
    top_level_clauses = payment_classification.get("top_level_clauses", {})
    return top_level_clauses[clause_key]


def l2_record(payment_classification: dict[str, Any], clause_key: str) -> dict[str, Any]:
    classified_clauses = payment_classification.get("classified_clauses", {})
    return classified_clauses[clause_key]


def overtime_classification_record(
    overtime_classification: dict[str, Any],
    clause_key: str,
) -> dict[str, Any]:
    clauses = overtime_classification.get("clauses", [])

    for clause in clauses:
        if str(clause.get("clause_number", "")) == clause_key:
            return clause

    raise KeyError(clause_key)


def clamp_index(index: int, item_count: int) -> int:
    if item_count == 0:
        return 0

    return min(max(index, 0), item_count - 1)


def next_index(index: int, item_count: int) -> int:
    if item_count == 0:
        return 0

    return (index + 1) % item_count


def previous_index(index: int, item_count: int) -> int:
    if item_count == 0:
        return 0

    return (index - 1) % item_count


def format_path_for_display(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def natural_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value)
    key_parts: list[int | str] = []

    for part in parts:
        if part.isdigit():
            key_parts.append(int(part))
        elif part:
            key_parts.append(part)

    return key_parts
