import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    evaluator_feedback: Path
    creator_response: Path
    revised_overtime_interpretation: Path


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
        evaluator_feedback=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_evaluator_feedback.md",
        creator_response=OVERTIME_FEEDBACK_DIR
        / f"{award_code}_overtime_interpretation_creator_response.md",
        revised_overtime_interpretation=OVERTIME_INTERPRETATION_DIR
        / f"{award_code}_overtime_interpretation_revised.md",
    )


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def read_text_file(path: Path) -> FileContent:
    if not path.exists():
        return FileContent(path=path, exists=False, text="")

    return FileContent(path=path, exists=True, text=path.read_text(encoding="utf-8"))


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
