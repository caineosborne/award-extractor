"""Prompt content for step 5B overtime pseudocode generation.

Used by:
- `src/script_5b_generate_overtime_pseudocode.py`
"""

from __future__ import annotations

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)
from src.common.rule_inventory import RuleInventory, render_inventory_for_prompt


PSEUDOCODE_FIELDS = {
    "Shift_Date": "The calendar date on which the shift starts.",
    "Shift_Day": "The named day associated with the shift.",
    "Shift_Start": "The shift start time.",
    "Shift_End": "The shift end time.",
    "Roster_Start": "The time the employees is rostered to start work.",
    "Roster_End": "The time the employee is rostered to end work.",
    "Day_of_Week": "The day of the week for the shift date.",
    "Employee Type - Shift Worker/Day Worker": (
        "Whether the employee is classified as a shift worker or day worker."
    ),
    "Employee Type - Full Time/PartTime/Casual": (
        "Whether the employee is full-time, part-time, or casual."
    ),
    "Unallocated_Hours": (
        "The hours in the shift that have not yet been allocated by another clause."
    ),
}


COMMON_CONSTRAINTS = """Common constraints:
- Preserve the business meaning of the reviewed source rules, even if headings or bullet formatting have been edited by a human.
- Read the complete document for meaning. Do not rely on an exact markdown heading or bullet label.
- Every reviewed source rule must be represented in the pseudocode or implementation notes. Do not omit a reviewed rule merely because another rule sounds similar.
- Include exact source clause references in comments on the relevant implementation rule. Use actual clause references such as `10.4(f)` or `23.2(a)`, not only internal rule ids.
- If a rule needs an input that is not in the available fields, name it under `Required additional inputs`.
- Do not list a derived field that is just a renamed component of an existing field.
- Do not list straightforward calculations as separate derived fields unless they are reused across multiple rules and make the pseudocode materially clearer.
- Treat `Derived Fields` as optional reusable calculations. If none are needed, write `None`.
- Treat `Required additional inputs` narrowly. Only include facts that are not already provided and cannot be calculated directly from the supplied fields and shift records.
- Use clear payroll variables. Do not invent vague helper variables or placeholders that hide the calculation.
- Prefer simple step-by-step pseudocode over dense formulas.
- When determining priority, process outlier and exception rules first, then day-type and time-of-day rules, then shorter-period thresholds, then longer-period thresholds.
- Return markdown only.
"""


CREATION_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied reviewed overtime creation guide into bullet-point pseudocode.
- Classify whether worked hours are `Ordinary_Hours` or `Overtime_Hours`.
- Treat `Unallocated_Hours` as the total hours worked that still need ordinary/overtime classification.
- For this task, any hours that are not ordinary hours are overtime.
- Focus on what causes hours to become overtime, not on multiplier or dollar calculation.

Available fields:
{fields}

Creation-specific constraints:
- Apply rules only to currently `Unallocated_Hours`.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining `Unallocated_Hours` to `Ordinary_Hours` after all overtime triggers have been applied.
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts.
- If the ruleset applies to all employees, it is not necessary to repeat the employee cohort unless a rule targets a narrower cohort.

{common_constraints}

Required markdown structure:

# Overtime pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Implementation notes
"""


CONSEQUENCE_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied reviewed overtime consequence guide into bullet-point pseudocode.
- Determine what overtime consequence applies once hours are already overtime.
- Do not classify ordinary hours versus overtime hours in this mode unless a source rule expressly needs that distinction as a condition.
- Focus on consequence outcomes such as multipliers, minimum payments, ordinary-rate exceptions, meal entitlements, paid-release outcomes, and weekend/public-holiday overrides.

Available fields:
{fields}

Consequence-specific constraints:
- Treat the input as already-overtime hours or already-identified overtime circumstances that now need the correct consequence applied.
- Do not use `Ordinary_Hours` and `Overtime_Hours` as the primary outputs in this mode.
- Use implementation outputs such as `Overtime_Rate_Multiplier`, `Minimum_Payment_Hours`, `Meal_Allowance_Payable`, `Meal_Allowance_Amount`, `Paid_Release_Required`, `Paid_Release_Minimum_Hours`, `Apply_Ordinary_Rate_Instead`, `Weekend_Public_Holiday_Override`, or similarly explicit consequence outputs when supported by the rules.
- Split distinct consequence outcomes into separate implementation rules when payroll would configure them separately.
- Keep trigger wording only where it is needed to identify when the consequence applies.
- If a source rule is informational context only and does not change the outcome, place it in `Implementation notes` rather than forcing it into executable pseudocode.

{common_constraints}

Required markdown structure:

# Overtime consequence pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Implementation notes
"""


def _system_prompt_for_ruleset(ruleset_key: str, fields: str) -> str:
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        return CONSEQUENCE_SYSTEM_PROMPT_TEMPLATE.format(
            fields=fields,
            common_constraints=COMMON_CONSTRAINTS,
        )

    return CREATION_SYSTEM_PROMPT_TEMPLATE.format(
        fields=fields,
        common_constraints=COMMON_CONSTRAINTS,
    )


def build_messages(
    source_file: str,
    overtime_summary_markdown: str,
    source_inventory: RuleInventory | None = None,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = _system_prompt_for_ruleset(ruleset_key, fields)
    inventory_text = ""
    if source_inventory is not None:
        inventory_text = (
            "Required rule inventory derived from the reviewed source markdown:\n"
            f"{render_inventory_for_prompt(source_inventory)}\n\n"
        )
    user_prompt = (
        f"Reviewed source markdown: {source_file}\n\n"
        f"{inventory_text}"
        "Complete reviewed source markdown to convert:\n"
        f"{overtime_summary_markdown}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_repair_messages(
    *,
    source_file: str,
    overtime_summary_markdown: str,
    source_inventory: RuleInventory,
    initial_pseudocode_markdown: str,
    validation_report_markdown: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = _system_prompt_for_ruleset(ruleset_key, fields)
    user_prompt = (
        f"Reviewed source markdown: {source_file}\n\n"
        "The first pseudocode draft failed deterministic validation.\n\n"
        "Required rule inventory derived from the reviewed source markdown:\n"
        f"{render_inventory_for_prompt(source_inventory)}\n\n"
        "Reviewed source markdown:\n"
        f"{overtime_summary_markdown}\n\n"
        "Initial pseudocode draft to repair:\n"
        f"{initial_pseudocode_markdown}\n\n"
        "Validation report describing the missing or inconsistent rules:\n"
        f"{validation_report_markdown}\n\n"
        "Revise the pseudocode so every reviewed source rule is represented. "
        "Preserve correct rules already present. Carry the relevant source clause references into comments. "
        "If a rule needs operational inputs that are not already in the available fields, state them in `Required additional inputs`."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
