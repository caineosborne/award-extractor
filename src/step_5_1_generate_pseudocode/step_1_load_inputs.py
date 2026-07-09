"""Step 5.1 stage 1: load reviewed ruleset inputs and resolve output paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.active_pipeline_paths import looks_like_path
from src.common.output_naming import pseudocode_path_for_ruleset
from src.common.output_paths import award_output_dir
from src.common.overtime_rules import (
    OVERTIME_RULE_SCHEMA_VERSION,
    build_rule_inventory_from_rules,
    json_output_path_for_markdown,
    load_rules_artifact,
    rules_from_markdown_fallback,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
    infer_overtime_ruleset_key_from_path,
)

from .schema import (
    CoreOvertimePseudocodeError,
    DEFAULT_OVERTIME_SUMMARY_PATH,
    PROJECT_ROOT,
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


def entitlement_path_for_award(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    """Return the preferred step 4.1 formatted ruleset path for one award code."""
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_entitlements.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        return award_dir / "4_1_OT_creation_formatted_ruleset.md"
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        return award_dir / "4_1_OT_consequence_formatted_ruleset.md"
    if ruleset_key == PENALTIES_RULESET:
        return award_dir / "4_1_Penalties_formatted_ruleset.md"
    return award_dir / "4_1_OT_creation_formatted_ruleset.md"


def fallback_source_paths_for_path(path: Path) -> list[Path]:
    """Return the ordered fallback source candidates for one explicit input path."""
    stem = path.stem

    if stem == "3_2_OT_creation_revised_ruleset_manual":
        return [
            path,
            path.parent / "4_1_OT_creation_formatted_ruleset.md",
            path.parent / "3_2_OT_creation_revised_ruleset.md",
            path.parent / "3_1_OT_creation_ruleset.md",
        ]
    if stem == "3_2_OT_consequence_revised_ruleset_manual":
        return [
            path,
            path.parent / "4_1_OT_consequence_formatted_ruleset.md",
            path.parent / "3_2_OT_consequence_revised_ruleset.md",
            path.parent / "3_1_OT_consequence_ruleset.md",
        ]
    if stem == "3_2_Penalties_revised_ruleset_manual":
        return [
            path,
            path.parent / "4_1_Penalties_formatted_ruleset.md",
            path.parent / "3_2_Penalties_revised_ruleset.md",
            path.parent / "3_1_Penalties_ruleset.md",
        ]
    if stem == "3_2_OT_creation_revised_ruleset":
        return [
            path.parent / "4_1_OT_creation_formatted_ruleset.md",
            path,
            path.parent / "3_1_OT_creation_ruleset.md",
        ]
    if stem == "3_2_OT_consequence_revised_ruleset":
        return [
            path.parent / "4_1_OT_consequence_formatted_ruleset.md",
            path,
            path.parent / "3_1_OT_consequence_ruleset.md",
        ]
    if stem == "3_2_Penalties_revised_ruleset":
        return [
            path.parent / "4_1_Penalties_formatted_ruleset.md",
            path,
            path.parent / "3_1_Penalties_ruleset.md",
        ]
    if stem == "4_1_OT_creation_formatted_ruleset":
        return [
            path,
            path.parent / "3_2_OT_creation_revised_ruleset.md",
            path.parent / "3_1_OT_creation_ruleset.md",
        ]
    if stem == "4_1_OT_consequence_formatted_ruleset":
        return [
            path,
            path.parent / "3_2_OT_consequence_revised_ruleset.md",
            path.parent / "3_1_OT_consequence_ruleset.md",
        ]
    if stem == "4_1_Penalties_formatted_ruleset":
        return [
            path,
            path.parent / "3_2_Penalties_revised_ruleset.md",
            path.parent / "3_1_Penalties_ruleset.md",
        ]

    return [path]


def default_overtime_interpretation_path(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    """Return the preferred reviewed ruleset source path for one award code."""
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_interpretation.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        manual_ruleset_path = award_dir / "3_2_OT_creation_revised_ruleset_manual.md"
        if manual_ruleset_path.exists():
            return manual_ruleset_path
        entitlement_path = entitlement_path_for_award(award_code, ruleset_key)
        if entitlement_path.exists():
            return entitlement_path
        revised_path = award_dir / "3_2_OT_creation_revised_ruleset.md"
        if revised_path.exists():
            return revised_path
        return award_dir / "3_1_OT_creation_ruleset.md"
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        manual_ruleset_path = award_dir / "3_2_OT_consequence_revised_ruleset_manual.md"
        if manual_ruleset_path.exists():
            return manual_ruleset_path
        entitlement_path = entitlement_path_for_award(award_code, ruleset_key)
        if entitlement_path.exists():
            return entitlement_path
        revised_path = award_dir / "3_2_OT_consequence_revised_ruleset.md"
        if revised_path.exists():
            return revised_path
        return award_dir / "3_1_OT_consequence_ruleset.md"
    if ruleset_key == PENALTIES_RULESET:
        manual_ruleset_path = award_dir / "3_2_Penalties_revised_ruleset_manual.md"
        if manual_ruleset_path.exists():
            return manual_ruleset_path
        entitlement_path = entitlement_path_for_award(award_code, ruleset_key)
        if entitlement_path.exists():
            return entitlement_path
        revised_path = award_dir / "3_2_Penalties_revised_ruleset.md"
        if revised_path.exists():
            return revised_path
        return award_dir / "3_1_Penalties_ruleset.md"

    manual_ruleset_path = award_dir / "3_2_OT_creation_revised_ruleset_manual.md"
    if manual_ruleset_path.exists():
        return manual_ruleset_path
    entitlement_path = entitlement_path_for_award(award_code)
    if entitlement_path.exists():
        return entitlement_path
    revised_path = award_dir / "3_2_OT_creation_revised_ruleset.md"
    if revised_path.exists():
        return revised_path
    return award_dir / "3_1_OT_creation_ruleset.md"


def select_overtime_interpretation_path(
    source_path: Path | str = DEFAULT_OVERTIME_SUMMARY_PATH,
    ruleset_key: str | None = None,
) -> Path:
    """Resolve the best available reviewed ruleset source path."""
    selected_source = str(source_path)
    if looks_like_path(selected_source):
        candidate_paths = fallback_source_paths_for_path(Path(selected_source))
    else:
        candidate_paths = [default_overtime_interpretation_path(selected_source, ruleset_key)]

    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path

    raise CoreOvertimePseudocodeError(
        "Overtime interpretation markdown not found. Checked: "
        + ", ".join(str(path) for path in candidate_paths)
    )


def source_stage_for_path(path: Path) -> str:
    """Return the pipeline stage label for one selected source path."""
    stem = path.stem

    if stem in {
        "3_2_OT_creation_revised_ruleset_manual",
        "3_2_OT_consequence_revised_ruleset_manual",
        "3_2_Penalties_revised_ruleset_manual",
    }:
        return "manual"
    if stem in {
        "4_1_OT_creation_formatted_ruleset",
        "4_1_OT_consequence_formatted_ruleset",
        "4_1_Penalties_formatted_ruleset",
    }:
        return "4.1"
    if stem in {
        "3_2_OT_creation_revised_ruleset",
        "3_2_OT_consequence_revised_ruleset",
        "3_2_Penalties_revised_ruleset",
    }:
        return "3.2"
    if stem in {
        "3_1_OT_creation_ruleset",
        "3_1_OT_consequence_ruleset",
        "3_1_Penalties_ruleset",
    }:
        return "3.1"
    return "unknown"


def load_overtime_interpretation(source_path: Path | str) -> str:
    """Load one reviewed ruleset markdown source."""
    path = select_overtime_interpretation_path(source_path)
    if not path.exists():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown not found: {path}"
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown is empty: {path}"
        )
    return text


def load_overtime_rules(source_path: Path | str) -> dict[str, Any]:
    """Load the reviewed ruleset artifact, falling back to markdown parsing when needed."""
    path = select_overtime_interpretation_path(source_path)
    json_path = json_output_path_for_markdown(path)
    if not json_path.exists():
        markdown_text = load_overtime_interpretation(path)
        return {
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "rendered_markdown": markdown_text,
            "rules": rules_from_markdown_fallback(markdown_text, source_path=path),
        }
    try:
        return load_rules_artifact(
            json_path,
            expected_schema_version=OVERTIME_RULE_SCHEMA_VERSION,
        )
    except ValueError as exc:
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation rules JSON is invalid: {json_path}"
        ) from exc


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
    destination = (
        Path(output_path)
        if output_path
        else pseudocode_path_for_ruleset(source_path, effective_ruleset_key)
    )

    return Step5GenerationInputs(
        source_path=source_path,
        destination=destination,
        effective_ruleset_key=effective_ruleset_key,
        rules_artifact=rules_artifact,
        summary_text=summary_text,
        source_inventory=source_inventory,
    )
