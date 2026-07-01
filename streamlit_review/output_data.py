import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.output_paths import (
    ARCHIVE_DIR,
    award_output_dir,
    output_set_name_for_path,
    write_text_with_archive,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)
from src.step_4_1_format_ruleset.run import output_path_for_interpretation
from src.script_5b_generate_overtime_pseudocode import output_path_for_summary
from src.script_5b_validate_overtime_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"


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
class RulesetArtifactPaths:
    ruleset_key: str
    clause_classification: Path
    expert_a_markdown: Path
    expert_b_markdown: Path
    comparison_json: Path
    combined_markdown: Path
    combined_json: Path
    evaluator_feedback: Path
    evaluator_feedback_json: Path
    creator_response: Path
    creator_response_json: Path
    revised_markdown: Path
    revised_json: Path
    formatted_markdown: Path
    manual_4b_markdown: Path
    pseudocode_markdown: Path
    pseudocode_validation_json: Path
    pseudocode_validation_markdown: Path


@dataclass(frozen=True)
class FileContent:
    path: Path
    exists: bool
    text: str


def discover_award_codes(processed_root: Path = PROCESSED_ROOT) -> list[str]:
    if not processed_root.exists():
        return []

    award_codes: list[str] = []

    for path in processed_root.rglob("*_payment_classification.json"):
        if ARCHIVE_DIR in path.parts:
            continue
        award_codes.append(output_set_name_for_path(path))

    return sorted(set(award_codes))


def artifact_paths_for_award(award_code: str) -> ArtifactPaths:
    award_dir = award_output_dir(PROCESSED_ROOT / f"{award_code}_payment_classification.json")
    feedback_dir = award_dir / "feedback"

    return ArtifactPaths(
        payment_classification=award_dir / f"{award_code}_payment_classification.json",
        overtime_clause_classification=award_dir / f"{award_code}_overtime_clause_classification.json",
        original_overtime_interpretation=award_dir / f"{award_code}_overtime_interpretation.md",
        original_overtime_interpretation_expert_a=award_dir
        / f"{award_code}_overtime_interpretation_expert_a.md",
        original_overtime_interpretation_expert_b=award_dir
        / f"{award_code}_overtime_interpretation_expert_b.md",
        original_overtime_interpretation_comparison=award_dir
        / f"{award_code}_overtime_interpretation_comparison.json",
        original_overtime_rules_json=award_dir / f"{award_code}_overtime_interpretation.json",
        agentic_review_conversation=feedback_dir
        / f"{award_code}_overtime_interpretation_agentic_review_conversation.md",
        evaluator_feedback=feedback_dir / f"{award_code}_overtime_interpretation_evaluator_feedback.md",
        evaluator_feedback_json=feedback_dir
        / f"{award_code}_overtime_interpretation_evaluator_feedback.json",
        creator_response=feedback_dir / f"{award_code}_overtime_interpretation_creator_response.md",
        creator_response_json=feedback_dir
        / f"{award_code}_overtime_interpretation_creator_response.json",
        revised_overtime_interpretation=award_dir / f"{award_code}_overtime_interpretation_revised.md",
        revised_overtime_rules_json=award_dir / f"{award_code}_overtime_interpretation_revised.json",
        overtime_entitlements=output_path_for_interpretation(
            award_dir / f"{award_code}_overtime_interpretation_revised.md"
        ),
        manual_4b_overtime_interpretation=award_dir / f"{award_code}_overtime_interpretation_4b.md",
        core_overtime_pseudocode=award_dir / f"{award_code}_core_overtime_pseudocode.md",
        core_overtime_validation_json=validation_json_path_for_pseudocode(
            award_dir / f"{award_code}_core_overtime_pseudocode.md"
        ),
        core_overtime_validation_markdown=validation_markdown_path_for_pseudocode(
            award_dir / f"{award_code}_core_overtime_pseudocode.md"
        ),
    )


def ruleset_artifact_paths_for_award(
    award_code: str,
    ruleset_key: str,
) -> RulesetArtifactPaths:
    award_dir = award_output_dir(PROCESSED_ROOT / f"{award_code}_payment_classification.json")
    feedback_dir = award_dir / "feedback"

    if ruleset_key == OVERTIME_CREATION_RULESET:
        explicit_base_stem = f"{award_code}_overtime_creation_ruleset"
        explicit_clause_stem = f"{award_code}_overtime_clause_classification"
        explicit_combined_markdown = award_dir / f"{explicit_base_stem}.md"

        if explicit_combined_markdown.exists():
            return RulesetArtifactPaths(
                ruleset_key=ruleset_key,
                clause_classification=award_dir / f"{explicit_clause_stem}.json",
                expert_a_markdown=award_dir / f"{explicit_base_stem}_expert_a.md",
                expert_b_markdown=award_dir / f"{explicit_base_stem}_expert_b.md",
                comparison_json=award_dir / f"{explicit_base_stem}_comparison.json",
                combined_markdown=explicit_combined_markdown,
                combined_json=explicit_combined_markdown.with_suffix(".json"),
                evaluator_feedback=feedback_dir
                / f"{explicit_base_stem}_evaluator_feedback.md",
                evaluator_feedback_json=feedback_dir
                / f"{explicit_base_stem}_evaluator_feedback.json",
                creator_response=feedback_dir
                / f"{explicit_base_stem}_creator_response.md",
                creator_response_json=feedback_dir
                / f"{explicit_base_stem}_creator_response.json",
                revised_markdown=award_dir / f"{explicit_base_stem}_revised.md",
                revised_json=award_dir / f"{explicit_base_stem}_revised.json",
                formatted_markdown=award_dir
                / f"{explicit_base_stem}_overtime_entitlements.md",
                manual_4b_markdown=award_dir / f"{explicit_base_stem}_4b.md",
                pseudocode_markdown=award_dir
                / f"{explicit_base_stem}_core_overtime_pseudocode.md",
                pseudocode_validation_json=award_dir
                / f"{explicit_base_stem}_core_overtime_pseudocode_validation.json",
                pseudocode_validation_markdown=award_dir
                / f"{explicit_base_stem}_core_overtime_pseudocode_validation.md",
            )

        legacy_combined_markdown = award_dir / f"{award_code}_overtime_interpretation.md"
        return RulesetArtifactPaths(
            ruleset_key=ruleset_key,
            clause_classification=award_dir / f"{award_code}_overtime_clause_classification.json",
            expert_a_markdown=award_dir / f"{award_code}_overtime_interpretation_expert_a.md",
            expert_b_markdown=award_dir / f"{award_code}_overtime_interpretation_expert_b.md",
            comparison_json=award_dir / f"{award_code}_overtime_interpretation_comparison.json",
            combined_markdown=legacy_combined_markdown,
            combined_json=legacy_combined_markdown.with_suffix(".json"),
            evaluator_feedback=feedback_dir
            / f"{award_code}_overtime_interpretation_evaluator_feedback.md",
            evaluator_feedback_json=feedback_dir
            / f"{award_code}_overtime_interpretation_evaluator_feedback.json",
            creator_response=feedback_dir
            / f"{award_code}_overtime_interpretation_creator_response.md",
            creator_response_json=feedback_dir
            / f"{award_code}_overtime_interpretation_creator_response.json",
            revised_markdown=award_dir / f"{award_code}_overtime_interpretation_revised.md",
            revised_json=award_dir / f"{award_code}_overtime_interpretation_revised.json",
            formatted_markdown=award_dir / f"{award_code}_overtime_entitlements.md",
            manual_4b_markdown=award_dir / f"{award_code}_overtime_interpretation_4b.md",
            pseudocode_markdown=award_dir / f"{award_code}_core_overtime_pseudocode.md",
            pseudocode_validation_json=award_dir
            / f"{award_code}_core_overtime_pseudocode_validation.json",
            pseudocode_validation_markdown=award_dir
            / f"{award_code}_core_overtime_pseudocode_validation.md",
        )
    elif ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        base_stem = f"{award_code}_overtime_consequence_ruleset"
        clause_stem = f"{award_code}_overtime_clause_classification"
    else:
        raise ValueError(f"Unsupported ruleset key: {ruleset_key}")

    combined_markdown = award_dir / f"{base_stem}.md"
    return RulesetArtifactPaths(
        ruleset_key=ruleset_key,
        clause_classification=award_dir / f"{clause_stem}.json",
        expert_a_markdown=award_dir / f"{base_stem}_expert_a.md",
        expert_b_markdown=award_dir / f"{base_stem}_expert_b.md",
        comparison_json=award_dir / f"{base_stem}_comparison.json",
        combined_markdown=combined_markdown,
        combined_json=combined_markdown.with_suffix(".json"),
        evaluator_feedback=feedback_dir / f"{base_stem}_evaluator_feedback.md",
        evaluator_feedback_json=feedback_dir / f"{base_stem}_evaluator_feedback.json",
        creator_response=feedback_dir / f"{base_stem}_creator_response.md",
        creator_response_json=feedback_dir / f"{base_stem}_creator_response.json",
        revised_markdown=award_dir / f"{base_stem}_revised.md",
        revised_json=award_dir / f"{base_stem}_revised.json",
        formatted_markdown=award_dir / f"{base_stem}_overtime_entitlements.md",
        manual_4b_markdown=award_dir / f"{base_stem}_4b.md",
        pseudocode_markdown=award_dir / f"{base_stem}_core_overtime_pseudocode.md",
        pseudocode_validation_json=award_dir
        / f"{base_stem}_core_overtime_pseudocode_validation.json",
        pseudocode_validation_markdown=award_dir
        / f"{base_stem}_core_overtime_pseudocode_validation.md",
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


def source_path_for_ruleset_manual_4b_editor(
    ruleset_artifact_paths: RulesetArtifactPaths,
) -> Path:
    if ruleset_artifact_paths.manual_4b_markdown.exists():
        return ruleset_artifact_paths.manual_4b_markdown

    if ruleset_artifact_paths.formatted_markdown.exists():
        return ruleset_artifact_paths.formatted_markdown

    if ruleset_artifact_paths.revised_markdown.exists():
        return ruleset_artifact_paths.revised_markdown

    return ruleset_artifact_paths.combined_markdown


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


def source_path_for_ruleset_core_overtime_pseudocode(
    ruleset_artifact_paths: RulesetArtifactPaths,
) -> Path:
    if ruleset_artifact_paths.manual_4b_markdown.exists():
        return ruleset_artifact_paths.manual_4b_markdown

    if ruleset_artifact_paths.formatted_markdown.exists():
        return ruleset_artifact_paths.formatted_markdown

    if ruleset_artifact_paths.revised_json.exists():
        return ruleset_artifact_paths.revised_json

    if ruleset_artifact_paths.revised_markdown.exists():
        return ruleset_artifact_paths.revised_markdown

    if ruleset_artifact_paths.combined_json.exists():
        return ruleset_artifact_paths.combined_json

    return ruleset_artifact_paths.combined_markdown


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
    award_directory = processed_root / selected_prefix

    if award_directory.exists() and award_directory.is_dir():
        for path in award_directory.rglob("*"):
            if not path.is_file():
                continue

            if ARCHIVE_DIR in path.parts:
                continue

            matching_paths.append(path)

    for path in processed_root.rglob("*"):
        if not path.is_file():
            continue

        if ARCHIVE_DIR in path.parts:
            continue

        if path.name.startswith(selected_prefix):
            matching_paths.append(path)

    return sorted(set(matching_paths))


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

    award_directory = processed_root / selected_prefix
    if award_directory.exists() and award_directory.is_dir():
        directories_to_consider = sorted(
            [path for path in award_directory.rglob("*") if path.is_dir()],
            reverse=True,
        )
        for directory in directories_to_consider:
            if any(directory.iterdir()):
                continue
            directory.rmdir()

        if not any(award_directory.iterdir()):
            award_directory.rmdir()

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
