"""Step 3.1 stage 5: write expert drafts, comparison output, and final artifact."""

from __future__ import annotations

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
from src.common.output_paths import write_text_output

from .step_1_load_inputs import comparison_output_path, expert_markdown_output_path


def write_expert_draft_artifact(
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


def write_combination_artifact(
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
    write_text_output(
        comparison_artifact_path,
        json.dumps(
            make_json_serializable(comparison_artifact),
            indent=2,
            ensure_ascii=False,
        ),
    )


def write_final_ruleset_artifact(
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
