from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.output_naming import (
    clause_classification_path_for_ruleset,
    ruleset_markdown_path_for_ruleset,
)


OVERTIME_CREATION_RULESET = "overtime_creation"
OVERTIME_CONSEQUENCE_RULESET = "overtime_consequence"


@dataclass(frozen=True)
class OvertimeRulesetConfig:
    key: str
    display_name: str
    source_tags: tuple[str, ...]
    allowed_classifications: tuple[str, ...]
    generation_classifications: tuple[str, ...]
    clause_classification_filename_stem: str
    ruleset_filename_stem: str
    comparison_schema_name: str
    interpretation_schema_name: str
    clause_classification_schema_name: str
    prompt_variant: str
    review_question: str


OVERTIME_RULESET_CONFIGS = {
    OVERTIME_CREATION_RULESET: OvertimeRulesetConfig(
        key=OVERTIME_CREATION_RULESET,
        display_name="Overtime creation",
        source_tags=("Ordinary Hours & Overtime",),
        allowed_classifications=(
            "Ordinary Hours Boundary",
            "Overtime Trigger",
            "Overtime Consequence",
            "Related Rule",
            "Not Relevant",
        ),
        generation_classifications=(
            "Ordinary Hours Boundary",
            "Overtime Trigger",
        ),
        clause_classification_filename_stem="2_2_OT_creation_clause_classification",
        ruleset_filename_stem="3_1_OT_creation_ruleset",
        comparison_schema_name="overtime_creation_rule_comparison",
        interpretation_schema_name="overtime_creation_rules",
        clause_classification_schema_name="overtime_creation_clause_classification",
        prompt_variant="creation",
        review_question="What circumstances increase total overtime hours?",
    ),
    OVERTIME_CONSEQUENCE_RULESET: OvertimeRulesetConfig(
        key=OVERTIME_CONSEQUENCE_RULESET,
        display_name="Overtime consequence",
        source_tags=("Ordinary Hours & Overtime",),
        allowed_classifications=(
            "Ordinary Hours Boundary",
            "Overtime Trigger",
            "Overtime Consequence",
            "Related Rule",
            "Not Relevant",
        ),
        generation_classifications=("Overtime Consequence",),
        clause_classification_filename_stem="2_2_OT_consequence_clause_classification",
        ruleset_filename_stem="3_1_OT_consequence_ruleset",
        comparison_schema_name="overtime_consequence_rule_comparison",
        interpretation_schema_name="overtime_consequence_rules",
        clause_classification_schema_name="overtime_consequence_clause_classification",
        prompt_variant="consequence",
        review_question="What overtime consequence applies once hours are already overtime?",
    ),
}


def overtime_ruleset_config(ruleset_key: str) -> OvertimeRulesetConfig:
    try:
        return OVERTIME_RULESET_CONFIGS[ruleset_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported overtime ruleset: {ruleset_key}") from exc


def infer_overtime_ruleset_key_from_path(path: Path | str) -> str:
    """Infer the overtime ruleset key from a standard artifact filename."""
    stem = Path(path).stem

    if stem.startswith("2_2_OT_creation_"):
        return OVERTIME_CREATION_RULESET
    if stem.startswith("3_1_OT_creation_"):
        return OVERTIME_CREATION_RULESET
    if stem.startswith("3_2_OT_creation_"):
        return OVERTIME_CREATION_RULESET
    if stem.startswith("4_1_OT_creation_"):
        return OVERTIME_CREATION_RULESET
    if stem.startswith("5_1_OT_creation_"):
        return OVERTIME_CREATION_RULESET

    if stem.startswith("2_2_OT_consequence_"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.startswith("3_1_OT_consequence_"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.startswith("3_2_OT_consequence_"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.startswith("4_1_OT_consequence_"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.startswith("5_1_OT_consequence_"):
        return OVERTIME_CONSEQUENCE_RULESET

    if stem.endswith("_overtime_creation_clause_classification"):
        return OVERTIME_CREATION_RULESET
    if stem.endswith("_overtime_creation_ruleset"):
        return OVERTIME_CREATION_RULESET
    if stem.endswith("_overtime_creation_ruleset_revised"):
        return OVERTIME_CREATION_RULESET

    if stem.endswith("_overtime_consequence_clause_classification"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.endswith("_overtime_consequence_ruleset"):
        return OVERTIME_CONSEQUENCE_RULESET
    if stem.endswith("_overtime_consequence_ruleset_revised"):
        return OVERTIME_CONSEQUENCE_RULESET

    if stem.endswith("_overtime_clause_classification"):
        return OVERTIME_CREATION_RULESET
    if stem.endswith("_overtime_interpretation"):
        return OVERTIME_CREATION_RULESET
    if stem.endswith("_overtime_interpretation_revised"):
        return OVERTIME_CREATION_RULESET

    raise ValueError(f"Could not infer overtime ruleset from path: {path}")


def explicit_clause_classification_output_path(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    return clause_classification_path_for_ruleset(classification_path, ruleset_key)


def explicit_ruleset_output_path(
    classification_path: Path | str,
    ruleset_key: str,
) -> Path:
    return ruleset_markdown_path_for_ruleset(classification_path, ruleset_key)
