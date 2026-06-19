from datetime import datetime
from pathlib import Path


FETCH_AWARD_DIR = "1_fetch_award"
PAYMENT_CLAUSE_IDENTIFIER_DIR = "2_payment_clause_identifier"
OVERTIME_INTERPRETATIONS_DIR = "3_overtime_interpretations"
OVERTIME_ENTITLEMENTS_DIR = "4a_overtime_entitlements"
OVERTIME_PSEUDOCODE_DIR = "5b_generate_overtime_pseudocode"
OVERTIME_REVIEW_DIR = "6_final_consistency_review"
ARCHIVE_DIR = "archive"


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
    return selected_path.parent


def category_dir(reference_path: Path | str, category: str) -> Path:
    return processed_root_for(reference_path) / category


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
