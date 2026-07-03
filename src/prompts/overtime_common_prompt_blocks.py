"""Reusable overtime prompt blocks.

These blocks are intentionally plain text so they can later become user-editable
configuration without changing the prompt builders.
"""

from __future__ import annotations

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)


GENERIC_PAYROLL_CONFIGURATION_PROMPT = """Shared payroll configuration approach:
- Write for a system that will configure code or payroll logic, not for a payroll expert reading a policy note.
- Prefer structured English and pseudocode, with explicit data points, clear conditions, and concrete outputs.
- Treat the questions below as expected checks for common award rules, not as the complete universe of possible rules.
- If the source supports another material overtime rule, include it even if it is not listed below.
- Do not invent a rule where the source does not support it.
"""


OVERTIME_CREATION_COMMON_QUESTIONS = """Reusable overtime creation checks:
- Is overtime created by working more than a number of hours in a day?
- Is overtime created by working outside a defined span of hours? This often, but not always, varies for day workers and shift workers.
- Is overtime created by working more than a number of hours in a week or pay period?

For each supported creation rule, answer:
- which employee cohorts it applies to, including full-time, part-time, casual, shift workers, and day workers where relevant;
- the triggering condition;
- any exceptions or limits, including agreement-based variations where supported by the source.
"""


OVERTIME_CONSEQUENCE_COMMON_QUESTIONS = """Reusable overtime consequence checks:
- What multiplier is paid when overtime is worked?
- Does the multiplier vary by employee cohort, including full-time, part-time, and casual employees?
- What other consequences apply once overtime exists, such as additional breaks, meal allowances, time off instead of payment, rest or release entitlements, minimum payments, or other post-overtime entitlements?

Every award is expected to have a clause stating the overtime rates for the main employee cohorts. If the supplied source contains those rates, do not leave the cohort multiplier unstated.

For each supported consequence rule, answer:
- which employee cohorts it applies to, including full-time, part-time, casual, shift workers, and day workers where relevant;
- the triggering condition for applying the consequence;
- any exceptions or limits.

Do not include standalone commentary on what creates overtime. Only include creation context when it is strictly necessary to identify which consequence applies after overtime is already defined.
"""


OVERTIME_COMMON_QUESTION_BLOCKS = {
    OVERTIME_CREATION_RULESET: OVERTIME_CREATION_COMMON_QUESTIONS,
    OVERTIME_CONSEQUENCE_RULESET: OVERTIME_CONSEQUENCE_COMMON_QUESTIONS,
}


def common_overtime_question_block(ruleset_key: str) -> str:
    """Return the reusable question block for one overtime ruleset."""
    return OVERTIME_COMMON_QUESTION_BLOCKS.get(
        ruleset_key,
        OVERTIME_CREATION_COMMON_QUESTIONS,
    )
