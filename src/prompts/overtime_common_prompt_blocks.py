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
- Prefer structured English or pseudocode (as requested), with explicit data points, clear conditions, and concrete outputs.
- Treat the questions below as expected checks for common award rules in the selected ruleset, not as the complete universe of possible rules.
- If the source supports another material rule for the selected ruleset, include it even if it is not listed below.
- Do not invent a rule where the source does not support it.
"""


COMMON_OVERTIME_RULES_PREAMBLE = """Common rulesets that may apply are:
- The following rules may appear across multiple awards.
- If the source supports a rule, include it in the ruleset.
- If the source does not support a rule, do not invent it.
- Include any other material rules supported by the source, even if they are not listed below.
"""


OVERTIME_CREATION_COMMON_QUESTIONS = """Reusable overtime creation checks:

- Is overtime created by working more than a number of hours in a day?
- What is the maximum amount of hours workable in a day before hours become overtime?
- Is overtime created by working outside a defined span of hours? This often, but not always, varies for day workers and shift workers.
- What is the allowed span of hours within which ordinary hours may be worked before hours become overtime?
- Is overtime created by working more than a number of hours in a week or pay period?
- If the clause states ordinary hours may be worked between times or within a span, treat that as an all-employees ordinary-hours boundary unless the clause expressly narrows the cohort.
- If the clause mentions broken shifts or spread of hours alongside the span, keep that boundary rule with the same all-employees scope unless the clause says otherwise.

For each supported creation rule, answer:
- which employee cohorts it applies to, including full-time, part-time, casual, shift workers, and day workers where relevant;
- the triggering condition;
- any exceptions or limits, including agreement-based variations where supported by the source.
"""


OVERTIME_CONSEQUENCE_COMMON_QUESTIONS = """Reusable overtime consequence checks:
- What multiplier is paid when overtime is worked? eg is it 150% or 200%? Does it vary on the day of the week, the time of day, or the number of hours worked?
- Does the multiplier vary by employee cohort, including full-time, part-time, and casual employees?
- What other consequences apply once overtime exists, such as additional breaks, meal allowances, time off instead of payment, rest or release entitlements, minimum payments, or other post-overtime entitlements?

Every award is expected to have a clause stating the overtime rates for the main employee cohorts. If the supplied source contains those rates, do not leave the cohort multiplier unstated.

For each supported consequence rule, answer:
- which employee cohorts it applies to, including full-time, part-time, casual, shift workers, and day workers where relevant;
- the triggering condition for applying the consequence;
- any exceptions or limits.

Do not include standalone commentary on what creates overtime.
Do not include any clauses related to the creation of overtime hours, or anythign which moves hours to overtime. Only include rulesets related to the consequences of working overtime. 
Only include creation context when it is strictly necessary to identify which consequence applies after overtime is already defined.
"""


PENALTIES_COMMON_QUESTIONS = """Reusable penalties checks:
- Penalties includes anything other than overtime that can increase pay for worked hours.
- Do not include anything related to overtime creation or overtime consequences, unless the clause expressly makes it part of a penalties-domain rule.
- This includes shift allowances, shift penalties, weekend penalties, public holiday penalties, afternoon penalties, evening penalties, night penalties, and similar higher-paid time-based rules.
- This also includes break-between-work-period clauses, even where they do not create a direct financial entitlement, because those clauses may still define operational rules relevant to the penalties domain.
- Break-between-work-period rules are still in scope even when they do not create any separate payment outcome.
- Some rules qualify by shift commencement.
- Some rules apply to the whole shift once qualified.
- Some rules apply only to specific hours worked.
- Some break-gap rules create premium pay outcomes.
- Some break-gap rules create no financial entitlement and should be retained as supporting context, not forced into a premium-pay rule.
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
- An afternoon or night shift allowance may depend on when the shift commences.
- Once a shift qualifies, the allowance may apply to the entire shift.
- A table-based penalty may instead apply only to the specific hours worked during a period such as 7.00 pm to midnight, midnight to 7.00 am, Saturday, Sunday, or public holiday.
- A break-between-work-period rule may require 10 hours off duty, allow reduction by agreement, and then pay 200% until release if the employee resumes without the required break.
- A break-between-work-period rule may create a 200% payment consequence plus paid release until the employee receives the required break.
- A minimum-break rule with no entitlement should still be captured in the subset as a supporting rule.

Mixed-clause handling:
- Some shortlisted clauses may also mention overtime, ordinary hours, allowances, or other payment topics because step 2.1 can assign more than one source tag to the same clause.
- For the penalties ruleset, keep only the penalty or break-between-work-period component that belongs in this subset.
- Do not create a penalties rule from a clause component that only creates overtime, only sets overtime rates, or only explains when overtime applies.
- Mention overtime only where the clause expressly makes it part of a penalties-domain rule, such as a break-gap consequence that applies after insufficient rest, or a cross-reference that is strictly necessary to explain the penalties outcome.

Keep whole-shift qualification rules separate from specific-hours rules. Do not invent a financial consequence where the clause only states a supporting operational condition.
"""


OVERTIME_COMMON_QUESTION_BLOCKS = {
    OVERTIME_CREATION_RULESET: (
        f"{COMMON_OVERTIME_RULES_PREAMBLE}\n{OVERTIME_CREATION_COMMON_QUESTIONS}"
    ),
    OVERTIME_CONSEQUENCE_RULESET: (
        f"{COMMON_OVERTIME_RULES_PREAMBLE}\n{OVERTIME_CONSEQUENCE_COMMON_QUESTIONS}"
    ),
    PENALTIES_RULESET: f"{COMMON_OVERTIME_RULES_PREAMBLE}\n{PENALTIES_COMMON_QUESTIONS}",
}


def common_overtime_question_block(ruleset_key: str) -> str:
    """Return the reusable question block for one supported ruleset."""
    return OVERTIME_COMMON_QUESTION_BLOCKS.get(
        ruleset_key,
        OVERTIME_CREATION_COMMON_QUESTIONS,
    )
