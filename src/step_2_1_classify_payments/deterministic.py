"""Deterministic helpers for step 2.1 payment classification."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.script_2_classify_payments import (
    DEFAULT_AWARD_PATH,
    SCHEMA_VERSION,
    build_top_level_groups,
    load_award,
    output_path_for_award,
)


@dataclass(frozen=True)
class Step2ClassificationInputs:
    """Prepared deterministic inputs for step 2.1 payment classification."""

    source_path: Path
    destination: Path
    award: OrderedDict[str, Any]
    groups: tuple[Any, ...]


def resolve_classification_inputs(
    *,
    award_path: Path | str = DEFAULT_AWARD_PATH,
    output_path: Path | str | None = None,
) -> Step2ClassificationInputs:
    """Load the source award and resolve the deterministic output path."""
    source_path = Path(award_path)
    destination = Path(output_path) if output_path is not None else output_path_for_award(source_path)
    award = load_award(source_path)
    groups = build_top_level_groups(award)
    return Step2ClassificationInputs(
        source_path=source_path,
        destination=destination,
        award=award,
        groups=groups,
    )


def build_result_artifact(
    *,
    source_path: Path,
    model: str,
    top_level_clauses: OrderedDict[str, dict[str, Any]],
    classified_clauses: OrderedDict[str, dict[str, Any]],
) -> OrderedDict[str, Any]:
    """Build the final step 2.1 JSON artifact."""
    result: OrderedDict[str, Any] = OrderedDict()
    result["source_file"] = str(source_path)
    result["model"] = model
    result["schema_version"] = SCHEMA_VERSION
    result["top_level_clauses"] = top_level_clauses
    result["classified_clauses"] = classified_clauses
    return result


def write_result(destination: Path, result: OrderedDict[str, Any]) -> None:
    """Write the current step 2.1 classification artifact."""
    from src.common.output_paths import write_text_with_archive

    output_json = json.dumps(result, indent=2, ensure_ascii=False)
    write_text_with_archive(destination, output_json)
