from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from src.common.output_paths import (
    FETCH_AWARD_DIR,
    FETCH_AWARD_SUPPORTING_DIR,
    OVERTIME_INTERPRETATION_FEEDBACK_DIR,
    output_set_name_for_path,
    output_set_name_for_stem,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
SPECIAL_ROOT_DIRS = {"_source_registry", "_streamlit_pipeline_runs"}
TEXT_SUFFIXES = {".csv", ".json", ".log", ".md", ".txt"}
LEGACY_TOP_LEVEL_DIRS = {
    "1_fetch_award",
    "2_payment_clause_identifier",
    "3_overtime_interpretations",
    "4a_overtime_entitlements",
    "5b_generate_overtime_pseudocode",
    "6_final_consistency_review",
}


@dataclass(frozen=True)
class FileMove:
    source_path: Path
    destination_path: Path


def is_supporting_fetch_filename(filename: str) -> bool:
    return (
        filename.endswith("_sections.json")
        or "_sections_" in filename
        or filename.endswith("_diagnostics.json")
        or "_diagnostics_" in filename
        or filename.endswith("_excluded_sections.json")
        or "_excluded_sections_" in filename
        or filename.endswith(".csv")
    )


def iter_legacy_files(processed_root: Path) -> list[Path]:
    legacy_files: list[Path] = []

    for top_level_dir in LEGACY_TOP_LEVEL_DIRS:
        legacy_dir = processed_root / top_level_dir
        if not legacy_dir.exists():
            continue

        for path in legacy_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            legacy_files.append(path)

    return sorted(legacy_files)


def destination_for_legacy_file(path: Path, processed_root: Path) -> Path:
    relative_path = path.relative_to(processed_root)
    top_level_dir = relative_path.parts[0]
    remaining_parts = relative_path.parts[1:]
    output_set_name = output_set_name_for_path(path)
    award_dir = processed_root / output_set_name
    filename = path.name

    if top_level_dir == FETCH_AWARD_DIR:
        if remaining_parts[0] == "raw":
            return award_dir / "raw" / filename

        if remaining_parts[0] == FETCH_AWARD_SUPPORTING_DIR:
            if len(remaining_parts) > 1 and remaining_parts[1] == "archive":
                return award_dir / FETCH_AWARD_SUPPORTING_DIR / "archive" / filename
            return award_dir / FETCH_AWARD_SUPPORTING_DIR / filename

        if remaining_parts[0] == "archive":
            if is_supporting_fetch_filename(filename):
                return award_dir / FETCH_AWARD_SUPPORTING_DIR / "archive" / filename
            return award_dir / "archive" / filename

        if is_supporting_fetch_filename(filename):
            return award_dir / FETCH_AWARD_SUPPORTING_DIR / filename
        return award_dir / filename

    if top_level_dir == "2_payment_clause_identifier":
        if remaining_parts[0] == "archive":
            return award_dir / "archive" / filename
        return award_dir / filename

    if top_level_dir == "3_overtime_interpretations":
        if remaining_parts[0] == OVERTIME_INTERPRETATION_FEEDBACK_DIR:
            if len(remaining_parts) > 1 and remaining_parts[1] == "archive":
                return award_dir / OVERTIME_INTERPRETATION_FEEDBACK_DIR / "archive" / filename
            return award_dir / OVERTIME_INTERPRETATION_FEEDBACK_DIR / filename

        if remaining_parts[0] == "archive":
            if len(remaining_parts) > 1 and remaining_parts[1] == OVERTIME_INTERPRETATION_FEEDBACK_DIR:
                return award_dir / OVERTIME_INTERPRETATION_FEEDBACK_DIR / "archive" / filename
            return award_dir / "archive" / filename

        return award_dir / filename

    if top_level_dir in {
        "4a_overtime_entitlements",
        "5b_generate_overtime_pseudocode",
        "6_final_consistency_review",
    }:
        if remaining_parts[0] == "archive":
            return award_dir / "archive" / filename
        return award_dir / filename

    raise ValueError(f"Unsupported legacy file location: {path}")


def build_move_plan(processed_root: Path) -> list[FileMove]:
    moves: list[FileMove] = []

    for source_path in iter_legacy_files(processed_root):
        destination_path = destination_for_legacy_file(source_path, processed_root)
        moves.append(FileMove(source_path=source_path, destination_path=destination_path))

    return moves


def build_normalization_moves(processed_root: Path) -> list[FileMove]:
    moves: list[FileMove] = []

    for path in sorted(processed_root.iterdir()):
        if not path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if path.name in LEGACY_TOP_LEVEL_DIRS:
            continue
        if path.name in SPECIAL_ROOT_DIRS:
            continue

        normalized_output_set_name = output_set_name_for_stem(path.name)
        if normalized_output_set_name == path.name:
            continue

        normalized_dir = processed_root / normalized_output_set_name

        for child_path in sorted(path.rglob("*")):
            if not child_path.is_file():
                continue
            relative_child_path = child_path.relative_to(path)
            moves.append(
                FileMove(
                    source_path=child_path,
                    destination_path=normalized_dir / relative_child_path,
                )
            )

    return moves


def replace_text_references(text: str, replacements: dict[str, str]) -> str:
    updated_text = text

    for old_value, new_value in replacements.items():
        updated_text = updated_text.replace(old_value, new_value)

    return updated_text


def apply_move(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if destination_path.exists():
        source_bytes = source_path.read_bytes()
        destination_bytes = destination_path.read_bytes()

        if source_bytes != destination_bytes:
            raise RuntimeError(
                "Migration would overwrite a different file: "
                f"{destination_path}"
            )

        source_path.unlink()
        return

    source_path.rename(destination_path)


def rewrite_migrated_text_files(
    moved_destinations: list[Path],
    replacements: dict[str, str],
) -> int:
    rewritten_file_count = 0

    for path in moved_destinations:
        if path.suffix not in TEXT_SUFFIXES:
            continue

        original_text = path.read_text(encoding="utf-8")
        updated_text = replace_text_references(original_text, replacements)

        if updated_text == original_text:
            continue

        path.write_text(updated_text, encoding="utf-8")
        rewritten_file_count += 1

    return rewritten_file_count


def prune_empty_legacy_dirs(processed_root: Path) -> None:
    candidate_directories = [
        path
        for path in processed_root.rglob("*")
        if path.is_dir()
        and path.name not in SPECIAL_ROOT_DIRS
    ]

    for path in sorted(candidate_directories, key=lambda item: len(item.parts), reverse=True):
        if path == processed_root:
            continue
        if any(child for child in path.iterdir()):
            continue
        path.rmdir()


def migration_replacements(
    project_root: Path,
    moves: list[FileMove],
) -> dict[str, str]:
    replacements: dict[str, str] = {}

    for move in moves:
        old_path = move.source_path.resolve()
        new_path = move.destination_path.resolve()

        replacements[str(old_path)] = str(new_path)

        try:
            old_relative_path = move.source_path.relative_to(project_root)
            new_relative_path = move.destination_path.relative_to(project_root)
        except ValueError:
            continue

        replacements[str(old_relative_path)] = str(new_relative_path)

    return replacements


def migrate_processed_outputs(
    processed_root: Path = DEFAULT_PROCESSED_ROOT,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, int]:
    moved_file_count = 0
    rewritten_file_count = 0

    move_groups = [
        build_move_plan(processed_root),
        build_normalization_moves(processed_root),
    ]

    for moves in move_groups:
        if not moves:
            continue

        replacements = migration_replacements(project_root, moves)
        moved_destinations: list[Path] = []

        for move in moves:
            apply_move(move.source_path, move.destination_path)
            moved_destinations.append(move.destination_path)

        moved_file_count += len(moves)
        rewritten_file_count += rewrite_migrated_text_files(
            moved_destinations,
            replacements,
        )

    prune_empty_legacy_dirs(processed_root)

    return {
        "moved_file_count": moved_file_count,
        "rewritten_file_count": rewritten_file_count,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move legacy step-based processed outputs into award-first folders."
    )
    parser.add_argument(
        "--processed-root",
        default=str(DEFAULT_PROCESSED_ROOT),
        help="Processed output root to migrate. Defaults to data/processed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    processed_root = Path(args.processed_root)
    result = migrate_processed_outputs(processed_root=processed_root, project_root=PROJECT_ROOT)

    print(f"Migrated {result['moved_file_count']} files.")
    print(f"Rewrote {result['rewritten_file_count']} migrated text files.")


if __name__ == "__main__":
    main()
