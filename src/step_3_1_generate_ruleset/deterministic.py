"""Deterministic helpers for step 3.1 ruleset generation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from src.common.overtime_rules import (
    OvertimeRule,
    build_step_3_rules_artifact,
    json_output_path_for_markdown,
    make_json_serializable,
    rule_to_dict,
    write_rules_artifact,
)
from src.common.output_paths import write_text_with_archive
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET, overtime_ruleset_config

from .core import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    comparison_output_path,
    expert_markdown_output_path,
    interpretation_output_path_for_source,
    overtime_clause_classification_path_for_source,
    select_overtime_creation_clauses,
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
        else overtime_clause_classification_path_for_source(source_path)
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


def load_prepared_clause_classifications(
    source_path: Path,
    classification_output_path: Path,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[OvertimeClauseClassification]:
    """Load part-1 output and validate it against the current step-2 source."""
    if not classification_output_path.exists():
        raise OvertimeInterpretationError(
            "Overtime clause classification JSON not found: "
            f"{classification_output_path}. Run step 3 part 1 first."
        )

    data = load_classification(source_path)
    overtime_clauses = select_ruleset_related_clauses(
        data,
        OVERTIME_CREATION_RULESET,
    )
    if not overtime_clauses:
        raise OvertimeInterpretationError(
            f"No overtime source clauses found in: {source_path}"
        )

    return load_overtime_clause_classification_artifact(
        classification_output_path,
        overtime_clauses,
        OVERTIME_CREATION_RULESET,
    )


def write_expert_draft(
    *,
    base_markdown_path: Path,
    label: str,
    source_path: Path,
    clause_classification_path: Path,
    rules: list[OvertimeRule],
    validation_warnings: list[str],
) -> dict[str, str]:
    """Write one expert draft artifact and return its paths."""
    expert_markdown_path = expert_markdown_output_path(base_markdown_path, label)
    expert_json_path = json_output_path_for_markdown(expert_markdown_path)
    expert_rules_artifact = build_step_3_rules_artifact(
        source_classification_file=source_path,
        source_clause_classification_file=clause_classification_path,
        rules=rules,
        validation_warnings=validation_warnings,
    )
    write_rules_artifact(
        json_path=expert_json_path,
        markdown_path=expert_markdown_path,
        artifact=expert_rules_artifact,
    )
    return {
        "label": label,
        "json_path": str(expert_json_path),
        "markdown_path": str(expert_markdown_path),
    }


def write_merged_ruleset(
    *,
    json_destination: Path,
    markdown_destination: Path,
    source_path: Path,
    clause_classification_path: Path,
    rules: list[OvertimeRule],
    validation_warnings: list[str],
    expert_output_paths: list[dict[str, str]],
    comparison_metadata: dict[str, Any],
) -> str:
    """Write the final step 3.1 ruleset artifact."""
    rules_artifact = build_step_3_rules_artifact(
        source_classification_file=source_path,
        source_clause_classification_file=clause_classification_path,
        rules=rules,
        validation_warnings=validation_warnings,
    )
    if expert_output_paths:
        rules_artifact["comparison_mode"] = "band_of_experts"
        rules_artifact["expert_outputs"] = expert_output_paths
    if comparison_metadata:
        rules_artifact["comparison_summary_markdown"] = comparison_metadata.get(
            "comparison_summary_markdown",
            "",
        )
        rules_artifact["merge_explanations"] = comparison_metadata.get(
            "merge_explanations",
            [],
        )

    write_rules_artifact(
        json_path=json_destination,
        markdown_path=markdown_destination,
        artifact=rules_artifact,
    )
    return str(rules_artifact["rendered_markdown"])


def write_merged_comparison(
    *,
    markdown_destination: Path,
    source_path: Path,
    clause_classification_path: Path,
    expert_output_paths: list[dict[str, str]],
    comparison_metadata: dict[str, Any],
    validation_warnings: list[str],
    rules: list[OvertimeRule],
) -> None:
    """Write the comparison artifact used to explain the merged ruleset."""
    comparison_artifact_path = comparison_output_path(markdown_destination)
    comparison_artifact = {
        "source_classification_file": str(source_path),
        "source_clause_classification_file": str(clause_classification_path),
        "expert_outputs": expert_output_paths,
        **comparison_metadata,
        "validation_warnings": validation_warnings,
        "merged_rules": [rule_to_dict(rule) for rule in rules],
    }
    write_text_with_archive(
        comparison_artifact_path,
        json.dumps(
            make_json_serializable(comparison_artifact),
            indent=2,
            ensure_ascii=False,
        ),
    )
