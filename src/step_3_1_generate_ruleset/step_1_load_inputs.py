"""Step 3.1 stage 1: load validated inputs and resolve output paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.active_pipeline_paths import interpretation_output_path_for_classification
from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    classification_output_path_for_source as overtime_clause_classification_path_for_source,
    load_classification,
    load_overtime_clause_classification_artifact,
    select_overtime_creation_clauses,
    select_ruleset_related_clauses,
)
from src.common.overtime_rules import json_output_path_for_markdown
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
    explicit_ruleset_output_path,
    overtime_ruleset_config,
)


@dataclass(frozen=True)
class Step3GenerationInputs:
    """Prepared step 3.1 inputs after deterministic loading and validation."""

    source_path: Path
    clause_classification_path: Path
    destination: Path
    json_destination: Path
    clause_classifications: list[OvertimeClauseClassification]
    overtime_creation_clauses: list[OvertimeClauseClassification]
    ruleset_key: str


def interpretation_output_path_for_source(
    classification_path: Path | str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> Path:
    """Return the default markdown ruleset path for step 3.1."""
    if ruleset_key == OVERTIME_CREATION_RULESET:
        return interpretation_output_path_for_classification(classification_path)
    if ruleset_key in {OVERTIME_CONSEQUENCE_RULESET, PENALTIES_RULESET}:
        return explicit_ruleset_output_path(classification_path, ruleset_key)
    raise ValueError(f"Unsupported overtime ruleset: {ruleset_key}")


def expert_markdown_output_path(base_markdown_path: Path | str, label: str) -> Path:
    """Return the sibling markdown path used for one expert draft."""
    path = Path(base_markdown_path)
    return path.with_name(f"{path.stem}_{label}{path.suffix}")


def comparison_output_path(base_markdown_path: Path | str) -> Path:
    """Return the JSON path used for the expert-comparison artifact."""
    path = Path(base_markdown_path)
    return path.with_name(f"{path.stem}_comparison.json")


def load_prepared_clause_classifications(
    source_path: Path,
    classification_output_path: Path,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Load step 2.2 output and validate it against the current step 2.1 source."""
    if not classification_output_path.exists():
        raise OvertimeInterpretationError(
            "Overtime clause classification JSON not found: "
            f"{classification_output_path}. Run step 2.2 first."
        )

    data = load_classification(source_path)
    overtime_clauses = select_ruleset_related_clauses(data, ruleset_key)
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No overtime source clauses found in: {source_path}"
        )

    return load_overtime_clause_classification_artifact(
        classification_output_path,
        overtime_clauses,
        ruleset_key,
    )


def resolve_generation_inputs(
    *,
    classification_path: Path | str,
    classification_output_path: Path | str | None = None,
    output_path: Path | str | None = None,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> Step3GenerationInputs:
    """Load and validate the deterministic inputs for step 3.1."""
    source_path = Path(classification_path)
    clause_classification_path = (
        Path(classification_output_path)
        if classification_output_path is not None
        else overtime_clause_classification_path_for_source(source_path, ruleset_key)
    )
    destination = (
        Path(output_path)
        if output_path is not None
        else interpretation_output_path_for_source(source_path, ruleset_key)
    )
    json_destination = json_output_path_for_markdown(destination)
    clause_classifications = load_prepared_clause_classifications(
        source_path,
        clause_classification_path,
        ruleset_key,
    )
    overtime_creation_clauses = select_overtime_creation_clauses(
        clause_classifications,
        ruleset_key,
    )
    if not overtime_creation_clauses:
        ruleset_label = overtime_ruleset_config(ruleset_key).display_name.lower()
        raise OvertimeInterpretationError(
            f"No generation-ready clauses found for the {ruleset_label} ruleset."
        )

    return Step3GenerationInputs(
        source_path=source_path,
        clause_classification_path=clause_classification_path,
        destination=destination,
        json_destination=json_destination,
        clause_classifications=clause_classifications,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
