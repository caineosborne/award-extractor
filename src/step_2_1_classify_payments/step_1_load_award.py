"""Step 2.1 stage 1: load award inputs."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.output_naming import classification_path_for_award_json

from .step_2_prepare_clauses import build_top_level_groups
from .schema import DEFAULT_AWARD_PATH, TopLevelGroup


@dataclass(frozen=True)
class Step2ClassificationInputs:
    """Prepared deterministic inputs for step 2.1 payment classification."""

    source_path: Path
    destination: Path
    award: OrderedDict[str, Any]
    groups: tuple[TopLevelGroup, ...]


def load_award(award_path: Path | str = DEFAULT_AWARD_PATH) -> OrderedDict[str, Any]:
    """Read the processed award JSON file and preserve key order."""
    path = Path(award_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def resolve_classification_inputs(
    *,
    award_path: Path | str = DEFAULT_AWARD_PATH,
    output_path: Path | str | None = None,
) -> Step2ClassificationInputs:
    """Load the source award and resolve the deterministic output path."""
    source_path = Path(award_path)
    destination = (
        Path(output_path)
        if output_path is not None
        else classification_path_for_award_json(source_path)
    )
    award = load_award(source_path)
    groups = build_top_level_groups(award)
    return Step2ClassificationInputs(
        source_path=source_path,
        destination=destination,
        award=award,
        groups=groups,
    )
