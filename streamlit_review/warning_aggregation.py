"""Aggregate stored ruleset warnings for the step 4.2 review screen."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def formatted_ruleset_metadata_path(formatted_markdown_path: Path) -> Path:
    """Return the step 4.1 metadata path containing formatter warnings."""
    return formatted_markdown_path.with_name(
        f"{formatted_markdown_path.stem}_metadata.json"
    )


def warning_source_artifacts(ruleset_artifacts: Any) -> list[dict[str, Any]]:
    """List warning-bearing artifacts in pipeline order for one ruleset."""
    return [
        {
            "stage_key": "3.1_expert_a",
            "stage_label": "3.1 Expert A",
            "path": ruleset_artifacts.expert_a_markdown.with_suffix(".json"),
        },
        {
            "stage_key": "3.1_expert_b",
            "stage_label": "3.1 Expert B",
            "path": ruleset_artifacts.expert_b_markdown.with_suffix(".json"),
        },
        {
            "stage_key": "3.1_combined",
            "stage_label": "3.1 Combined",
            "path": ruleset_artifacts.combined_json,
        },
        {
            "stage_key": "3.2_revised",
            "stage_label": "3.2 Revised",
            "path": ruleset_artifacts.revised_json,
        },
        {
            "stage_key": "4.1_formatted",
            "stage_label": "4.1 Formatted",
            "path": formatted_ruleset_metadata_path(
                ruleset_artifacts.formatted_markdown
            ),
        },
    ]


def normalized_warning_key(warning: str) -> str:
    """Normalize insignificant whitespace when identifying duplicate warnings."""
    return re.sub(r"\s+", " ", warning).strip()


def load_stored_validation_warnings(path: Path) -> list[str]:
    """Load the warning strings stored in one JSON artifact."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    raw_warnings = artifact.get("validation_warnings", [])

    if not isinstance(raw_warnings, list):
        raise ValueError(f"validation_warnings must be an array in {path}")

    warnings: list[str] = []
    for raw_warning in raw_warnings:
        warning = str(raw_warning).strip()
        if warning:
            warnings.append(warning)

    return warnings


def build_warning_register(ruleset_artifacts: Any) -> dict[str, Any]:
    """Collect stored warnings without recalculating any stage comparison."""
    unique_warnings: dict[str, dict[str, Any]] = {}
    stage_summaries: list[dict[str, Any]] = []
    missing_artifacts: list[dict[str, str]] = []

    for source in warning_source_artifacts(ruleset_artifacts):
        stage_key = str(source["stage_key"])
        stage_label = str(source["stage_label"])
        artifact_path = Path(source["path"])

        if not artifact_path.exists():
            missing_artifacts.append(
                {
                    "stage_key": stage_key,
                    "stage_label": stage_label,
                    "path": str(artifact_path),
                }
            )
            stage_summaries.append(
                {
                    "stage_key": stage_key,
                    "stage_label": stage_label,
                    "warning_count": 0,
                    "artifact_available": False,
                }
            )
            continue

        stage_warnings = load_stored_validation_warnings(artifact_path)
        stage_summaries.append(
            {
                "stage_key": stage_key,
                "stage_label": stage_label,
                "warning_count": len(stage_warnings),
                "artifact_available": True,
            }
        )

        for warning in stage_warnings:
            warning_key = normalized_warning_key(warning)
            existing_warning = unique_warnings.get(warning_key)

            if existing_warning is None:
                unique_warnings[warning_key] = {
                    "warning": warning,
                    "stage_keys": [stage_key],
                    "stage_labels": [stage_label],
                }
                continue

            if stage_key not in existing_warning["stage_keys"]:
                existing_warning["stage_keys"].append(stage_key)
                existing_warning["stage_labels"].append(stage_label)

    warnings = list(unique_warnings.values())
    total_stage_occurrences = sum(
        summary["warning_count"] for summary in stage_summaries
    )

    return {
        "warnings": warnings,
        "unique_warning_count": len(warnings),
        "total_stage_occurrences": total_stage_occurrences,
        "stage_summaries": stage_summaries,
        "missing_artifacts": missing_artifacts,
    }
