"""Shared prompt blocks organised by ruleset subset.

These are the broad subset instructions that should remain consistent wherever a
given subset is used across the pipeline.
"""

from __future__ import annotations

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
)


RULESET_PROMPT_FAMILY = {
    OVERTIME_CREATION_RULESET: "overtime",
    OVERTIME_CONSEQUENCE_RULESET: "overtime",
    PENALTIES_RULESET: "penalties",
}


SUBSET_SHARED_PROMPT_BLOCKS = {
    OVERTIME_CREATION_RULESET: """Subset-wide instructions for overtime creation:
- Focus on what circumstances increase total overtime hours.
- Preserve ordinary-hours boundaries whenever work outside the boundary may become overtime.
- Keep payment-consequence language only where it is needed to explain why hours become overtime.""",
    OVERTIME_CONSEQUENCE_RULESET: """Subset-wide instructions for overtime consequence:
- Focus on what payment, entitlement, release, or other result applies once hours are already overtime.
- Preserve direct consequence outcomes such as multipliers, minimum payments, meal entitlements, rest outcomes, and ordinary-rate exceptions where supported.
- Keep overtime-creation language only where it is genuinely required to identify when the consequence applies.""",
    PENALTIES_RULESET: """Subset-wide instructions for penalties:
- Focus on penalty rates, shift allowances, and supporting break-between-work-period rules.
- Preserve the distinction between whole-shift outcomes, qualifying-hours outcomes, and supporting operational conditions.
- Do not drift into overtime-only creation logic or overtime-only consequence logic unless the clause expressly states a penalties-domain outcome.""",
}


def ruleset_prompt_family(ruleset_key: str) -> str:
    """Return the prompt family for one supported ruleset key."""
    return RULESET_PROMPT_FAMILY[ruleset_key]


def subset_shared_prompt_block(ruleset_key: str) -> str:
    """Return the subset-wide prompt block for one supported ruleset key."""
    return SUBSET_SHARED_PROMPT_BLOCKS[ruleset_key]
