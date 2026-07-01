"""Deterministic helpers for step 5.1 pseudocode generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.overtime_rules import build_rule_inventory_from_rules
from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.script_5b_generate_overtime_pseudocode import (
    CoreOvertimePseudocodeError,
    load_overtime_rules,
    output_path_for_summary,
    select_overtime_interpretation_path,
    source_stage_for_path,
)
from src.script_5b_validate_overtime_pseudocode import (
    validate_overtime_pseudocode_against_inventory,
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
    write_validation_artifacts,
)


@dataclass(frozen=True)
class Step5GenerationInputs:
    """Prepared deterministic inputs for step 5.1 pseudocode generation."""

    source_path: Path
    destination: Path
    effective_ruleset_key: str
    rules_artifact: dict[str, Any]
    summary_text: str
    source_inventory: Any


def resolve_generation_inputs(
    *,
    summary_path,
    output_path=None,
    ruleset_key: str | None = None,
) -> Step5GenerationInputs:
    """Load and validate the deterministic inputs for step 5.1."""
    source_path = select_overtime_interpretation_path(summary_path, ruleset_key)
    try:
        effective_ruleset_key = ruleset_key or infer_overtime_ruleset_key_from_path(
            source_path
        )
    except ValueError:
        effective_ruleset_key = OVERTIME_CREATION_RULESET

    rules_artifact = load_overtime_rules(source_path)
    summary_text = str(rules_artifact["rendered_markdown"])
    source_inventory = build_rule_inventory_from_rules(
        rules_artifact["rules"],
        source_path=source_path,
        inventory_name="reviewed_overtime_rules",
        source_stage=source_stage_for_path(source_path),
        domain="overtime",
    )
    destination = Path(output_path) if output_path else output_path_for_summary(source_path)

    return Step5GenerationInputs(
        source_path=source_path,
        destination=destination,
        effective_ruleset_key=effective_ruleset_key,
        rules_artifact=rules_artifact,
        summary_text=summary_text,
        source_inventory=source_inventory,
    )


def validate_and_write_outputs(
    *,
    destination: Path,
    output_text: str,
    source_inventory,
) -> tuple[Any, str]:
    """Write pseudocode and validation artifacts, then return the validation state."""
    from src.common.output_paths import write_text_with_archive

    write_text_with_archive(destination, output_text)
    validation_report = validate_overtime_pseudocode_against_inventory(
        source_inventory,
        output_text,
        target_path=destination,
    )
    validation_markdown_path = write_validation_artifacts(
        validation_report,
        json_path=validation_json_path_for_pseudocode(destination),
        markdown_path=validation_markdown_path_for_pseudocode(destination),
    )[1]
    validation_markdown = validation_markdown_path.read_text(encoding="utf-8")
    return validation_report, validation_markdown
