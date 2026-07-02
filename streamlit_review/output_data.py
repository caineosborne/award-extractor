import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.output_paths import (
    ARCHIVE_DIR,
    write_text_output,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)
from src.common.output_naming import ruleset_short_label
from src.common.active_pipeline_paths import (
    ruleset_clause_classification_output_path_for_classification,
)
from src.step_5_1_generate_pseudocode.verification import (
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
    evaluator_feedback: Path
    creator_response: Path
    revised_overtime_interpretation: Path
    overtime_entitlements: Path
    manual_ruleset_path: Path
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
    manual_ruleset_markdown: Path
    pseudocode_markdown: Path
    pseudocode_validation_json: Path
    pseudocode_validation_markdown: Path


@dataclass(frozen=True)
class FileContent:
    path: Path
    exists: bool
    text: str


def award_dir_for_output_set(output_set_name: str) -> Path:
    return PROCESSED_ROOT / output_set_name


def canonical_ruleset_paths(
    output_set_name: str,
    ruleset_key: str,
) -> RulesetArtifactPaths:
    award_dir = award_dir_for_output_set(output_set_name)
    feedback_dir = award_dir / "feedback"
    short_label = ruleset_short_label(ruleset_key)
    payment_classification_path = award_dir / "2_1_payment_classification.json"
    combined_markdown = award_dir / f"3_1_{short_label}_ruleset.md"
    revised_markdown = award_dir / f"3_2_{short_label}_revised_ruleset.md"
    formatted_markdown = award_dir / f"4_1_{short_label}_formatted_ruleset.md"
    manual_ruleset_markdown = revised_markdown.with_name(
        f"{revised_markdown.stem}_manual.md"
    )
    pseudocode_markdown = award_dir / f"5_1_{short_label}_pseudocode.md"

    return RulesetArtifactPaths(
        ruleset_key=ruleset_key,
        clause_classification=ruleset_clause_classification_output_path_for_classification(
            payment_classification_path,
            ruleset_key,
        ),
        expert_a_markdown=award_dir / f"3_1_{short_label}_ruleset_expert_a.md",
        expert_b_markdown=award_dir / f"3_1_{short_label}_ruleset_expert_b.md",
        comparison_json=award_dir / f"3_1_{short_label}_ruleset_comparison.json",
        combined_markdown=combined_markdown,
        combined_json=combined_markdown.with_suffix(".json"),
        evaluator_feedback=feedback_dir / f"3_2_{short_label}_review.md",
        evaluator_feedback_json=feedback_dir / f"3_2_{short_label}_review.json",
        creator_response=feedback_dir / f"3_2_{short_label}_creator_response.md",
        creator_response_json=feedback_dir / f"3_2_{short_label}_creator_response.json",
        revised_markdown=revised_markdown,
        revised_json=revised_markdown.with_suffix(".json"),
        formatted_markdown=formatted_markdown,
        manual_ruleset_markdown=manual_ruleset_markdown,
        pseudocode_markdown=pseudocode_markdown,
        pseudocode_validation_json=validation_json_path_for_pseudocode(pseudocode_markdown),
        pseudocode_validation_markdown=validation_markdown_path_for_pseudocode(
            pseudocode_markdown
        ),
    )


def discover_award_codes(processed_root: Path = PROCESSED_ROOT) -> list[str]:
    if not processed_root.exists():
        return []

    award_codes: list[str] = []

    for path in processed_root.rglob("2_1_payment_classification.json"):
        if ARCHIVE_DIR in path.parts:
            continue
        award_codes.append(path.parent.name)

    return sorted(set(award_codes))


def artifact_paths_for_award(award_code: str) -> ArtifactPaths:
    award_dir = award_dir_for_output_set(award_code)
    feedback_dir = award_dir / "feedback"
    creation_ruleset_paths = canonical_ruleset_paths(award_code, OVERTIME_CREATION_RULESET)

    return ArtifactPaths(
        payment_classification=award_dir / "2_1_payment_classification.json",
        overtime_clause_classification=creation_ruleset_paths.clause_classification,
        original_overtime_interpretation=creation_ruleset_paths.combined_markdown,
        original_overtime_interpretation_expert_a=creation_ruleset_paths.expert_a_markdown,
        original_overtime_interpretation_expert_b=creation_ruleset_paths.expert_b_markdown,
        original_overtime_interpretation_comparison=creation_ruleset_paths.comparison_json,
        original_overtime_rules_json=creation_ruleset_paths.combined_json,
        evaluator_feedback=creation_ruleset_paths.evaluator_feedback,
        evaluator_feedback_json=creation_ruleset_paths.evaluator_feedback_json,
        creator_response=creation_ruleset_paths.creator_response,
        creator_response_json=creation_ruleset_paths.creator_response_json,
        revised_overtime_interpretation=creation_ruleset_paths.revised_markdown,
        revised_overtime_rules_json=creation_ruleset_paths.revised_json,
        overtime_entitlements=creation_ruleset_paths.formatted_markdown,
        manual_ruleset_path=creation_ruleset_paths.manual_ruleset_markdown,
        core_overtime_pseudocode=creation_ruleset_paths.pseudocode_markdown,
        core_overtime_validation_json=creation_ruleset_paths.pseudocode_validation_json,
        core_overtime_validation_markdown=creation_ruleset_paths.pseudocode_validation_markdown,
    )


def ruleset_artifact_paths_for_award(
    award_code: str,
    ruleset_key: str,
) -> RulesetArtifactPaths:
    if ruleset_key not in {OVERTIME_CREATION_RULESET, OVERTIME_CONSEQUENCE_RULESET}:
        raise ValueError(f"Unsupported ruleset key: {ruleset_key}")

    return canonical_ruleset_paths(award_code, ruleset_key)


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def read_text_file(path: Path) -> FileContent:
    if not path.exists():
        return FileContent(path=path, exists=False, text="")

    return FileContent(path=path, exists=True, text=path.read_text(encoding="utf-8"))


def write_text_file(path: Path, text: str) -> None:
    write_text_output(path, text)


def source_path_for_manual_ruleset_editor(artifact_paths: ArtifactPaths) -> Path:
    if artifact_paths.manual_ruleset_path.exists():
        return artifact_paths.manual_ruleset_path

    if artifact_paths.overtime_entitlements.exists():
        return artifact_paths.overtime_entitlements

    if artifact_paths.revised_overtime_interpretation.exists():
        return artifact_paths.revised_overtime_interpretation

    return artifact_paths.original_overtime_interpretation


def source_path_for_ruleset_manual_ruleset_editor(
    ruleset_artifact_paths: RulesetArtifactPaths,
) -> Path:
    if ruleset_artifact_paths.manual_ruleset_markdown.exists():
        return ruleset_artifact_paths.manual_ruleset_markdown

    if ruleset_artifact_paths.formatted_markdown.exists():
        return ruleset_artifact_paths.formatted_markdown

    if ruleset_artifact_paths.revised_markdown.exists():
        return ruleset_artifact_paths.revised_markdown

    return ruleset_artifact_paths.combined_markdown


def source_path_for_core_overtime_pseudocode(artifact_paths: ArtifactPaths) -> Path:
    if artifact_paths.manual_ruleset_path.exists():
        return artifact_paths.manual_ruleset_path

    if artifact_paths.overtime_entitlements.exists():
        return artifact_paths.overtime_entitlements

    if artifact_paths.revised_overtime_interpretation.exists():
        return artifact_paths.revised_overtime_interpretation

    return artifact_paths.original_overtime_interpretation


def source_path_for_ruleset_core_overtime_pseudocode(
    ruleset_artifact_paths: RulesetArtifactPaths,
) -> Path:
    if ruleset_artifact_paths.manual_ruleset_markdown.exists():
        return ruleset_artifact_paths.manual_ruleset_markdown

    if ruleset_artifact_paths.formatted_markdown.exists():
        return ruleset_artifact_paths.formatted_markdown

    if ruleset_artifact_paths.revised_markdown.exists():
        return ruleset_artifact_paths.revised_markdown

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

