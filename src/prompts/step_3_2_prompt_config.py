"""Prompt configuration for step 3.2 review subsets.

Keep step-3.2-specific prompt choices in the prompt layer so new subsets can be
added without spreading review wording across runtime modules.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
    overtime_ruleset_config,
)


@dataclass(frozen=True)
class Step32PromptSubsetConfig:
    """Small prompt-only overlay for one step-3.2 subset."""

    ruleset_key: str
    display_name: str
    review_question: str
    subset_scope_notes: tuple[str, ...] = ()


STEP_3_2_PROMPT_SUBSET_OVERRIDES: dict[str, dict[str, tuple[str, ...]]] = {
    OVERTIME_CREATION_RULESET: {
        "subset_scope_notes": (
            "Focus on circumstances that cause time to become overtime.",
        ),
    },
    OVERTIME_CONSEQUENCE_RULESET: {
        "subset_scope_notes": (
            "Focus on what consequence applies after the time is already overtime.",
        ),
    },
    PENALTIES_RULESET: {
        "subset_scope_notes": (
            "Focus on penalty rates, shift allowances, day or time-based premiums, and break-between-work-period rules that support this subset.",
            "Keep supporting break-gap rules even when they do not create a separate payment outcome, if the clause text makes them operationally relevant.",
            "Exclude overtime-only drafting drift unless the clause expressly states a penalties-specific rule that belongs in this subset.",
            "If a shortlisted clause is mixed, keep the penalties or break-gap component and do not require the final ruleset to restate standalone overtime triggers or overtime rates.",
        ),
    },
}


def step_3_2_prompt_subset_config(ruleset_key: str) -> Step32PromptSubsetConfig:
    """Resolve the small prompt overlay for one supported step-3.2 subset."""
    ruleset_config = overtime_ruleset_config(ruleset_key)
    override_values = STEP_3_2_PROMPT_SUBSET_OVERRIDES.get(ruleset_key, {})

    return Step32PromptSubsetConfig(
        ruleset_key=ruleset_config.key,
        display_name=ruleset_config.display_name,
        review_question=ruleset_config.review_question,
        subset_scope_notes=override_values.get("subset_scope_notes", ()),
    )
