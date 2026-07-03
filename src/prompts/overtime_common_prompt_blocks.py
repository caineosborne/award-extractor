"""Reusable ruleset prompt blocks.

These blocks are intentionally plain text so they can later become user-editable
configuration without changing the prompt builders.
"""

from __future__ import annotations

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
)


GENERIC_PAYROLL_CONFIGURATION_PROMPT = """Shared payroll configuration approach:
- Write for a system that will configure code or payroll logic, not for a payroll expert reading a policy note.
- Prefer structured English and pseudocode, with explicit data points, clear conditions, and concrete outputs.
- Treat the questions below as expected checks for common award rules in the selected ruleset, not as the complete universe of possible rules.
- If the source supports another material rule for the selected ruleset, include it even if it is not listed below.
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


PENALTIES_COMMON_QUESTIONS = """Reusable penalties checks:
- What additional rate, loading, allowance, multiplier, or dollar add-on is paid because of when the employee works?
- Does the rule apply because a shift commences at a particular time, finishes at a particular time, includes specific hours, occurs on a particular day, or occurs on a public holiday?
- Is the additional amount paid for the entire shift, or only for the qualifying hours within the shift?
- Does the rule apply only to a defined cohort or arrangement, such as shift workers, casual employees, or another named group?
- Are there break-between-work-period rules, minimum rest-gap rules, broken-shift rules, or roster-changeover gap rules that support payroll handling for penalties, even where the clause does not itself create an additional payment?
- If a break-gap rule does create a premium outcome, what multiplier, paid-release entitlement, or other direct consequence applies?

For each supported penalties rule, answer:
- which employee cohorts it applies to, including full-time, part-time, casual, shift workers, day workers, or another supported cohort;
- the qualification test, including whether it is based on shift commencement, shift end, actual hours worked, named day, public holiday, roster changeover, or minimum gap between work periods;
- the actual penalty outcome, including the multiplier, fixed add-on, allowance amount, or statement that the rule is a supporting non-financial condition only;
- any limits, exceptions, or agreement-based variations supported by the clause text.

Penalties examples to preserve where supported by the clauses:
- A shift allowance may apply because a shift commences within a qualifying start-time band, and the allowance may then apply to the entire shift.
- A night, evening, Saturday, Sunday, or public holiday penalty may apply only to the specific qualifying hours or day worked.
- Breaks between work periods may require a minimum number of hours off duty, may allow a reduced break by agreement, and may in some awards create a 200% payment consequence plus paid release until the employee has had the required rest period.
- Some break-between-work-period clauses are still in scope even when they do not create any separate payment outcome, because they remain operational supporting conditions for the penalties ruleset.

Keep whole-shift qualification rules separate from specific-hours rules. Do not invent a financial consequence where the clause only states a supporting operational condition.
"""


OVERTIME_COMMON_QUESTION_BLOCKS = {
    OVERTIME_CREATION_RULESET: OVERTIME_CREATION_COMMON_QUESTIONS,
    OVERTIME_CONSEQUENCE_RULESET: OVERTIME_CONSEQUENCE_COMMON_QUESTIONS,
    PENALTIES_RULESET: PENALTIES_COMMON_QUESTIONS,
}


def common_overtime_question_block(ruleset_key: str) -> str:
    """Return the reusable question block for one supported ruleset."""
    return OVERTIME_COMMON_QUESTION_BLOCKS.get(
        ruleset_key,
        OVERTIME_CREATION_COMMON_QUESTIONS,
    )
