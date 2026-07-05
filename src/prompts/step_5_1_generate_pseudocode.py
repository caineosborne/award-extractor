"""Prompt content for step 5.1 overtime pseudocode generation.

Used by:
- `src/step_5_1_generate_pseudocode/llm.py`
"""

from __future__ import annotations

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
)
from src.common.rule_inventory import RuleInventory, render_inventory_for_prompt
from src.prompts.overtime_common_prompt_blocks import (
    GENERIC_PAYROLL_CONFIGURATION_PROMPT,
    common_overtime_question_block,
)
from src.step_5_1_generate_pseudocode.core import CoreOvertimePseudocodeError


PSEUDOCODE_FIELDS = {
    "Shift_Date": "The calendar date on which the shift starts.",
    "Shift_Day": "The named day associated with the shift.",
    "Shift_Start": "The shift start time.",
    "Shift_End": "The shift end time.",
    "Roster_Start": "The time the employees is rostered to start work.",
    "Roster_End": "The time the employee is rostered to end work.",
    "Day_of_Week": "The day of the week for the shift date.",
    "Public_Holiday_Indicator": "Whether the shift or relevant hours fall on a public holiday.",
    "Previous_Shift_End": "The end time of the employee's previous shift or work period.",
    "Employee Type - Shift Worker/Day Worker": (
        "Whether the employee is classified as a shift worker or day worker."
    ),
    "Employee Type - Full Time/PartTime/Casual": (
        "Whether the employee is full-time, part-time, or casual."
    ),
    "Shift_Worker_Status": (
        "Whether the employee qualifies as a shift worker for rules that only apply to shift workers. Employees who are not shift workers are day workers."
    ),

}


PSEUDOCODE_GENERIC_CONSTRAINTS = """Common constraints:
- Preserve the business meaning of the reviewed source rules, even if headings or bullet formatting have been edited by a human.
- Read the complete document for meaning. Do not rely on an exact markdown heading or bullet label.
- Every reviewed source rule must be represented in the pseudocode or implementation notes. Do not omit a reviewed rule merely because another rule sounds similar.
- Include exact source clause references in comments on the relevant implementation rule. Use actual clause references such as `10.4(f)` or `23.2(a)`, not only internal rule ids.
- If a rule needs an input that is not in the available fields, name it under `Required additional inputs`. Only add rules into 'Required additional inputs' if they are unable to be derived base don the supplied list of derived fields, instead state how this would be derived, and include in the `Derived Fields` section.
- Do not list a derived field that is just a renamed component of an existing field.
- Do not list straightforward calculations as separate derived fields unless they are reused across multiple rules and make the pseudocode materially clearer.
- Treat `Derived Fields` as optional reusable calculations. If none are needed, write `None`.
- Treat `Required additional inputs` narrowly. Only include facts that are not already provided and cannot be calculated directly from the supplied fields and shift records.
- Use clear field names and rule names. Do not invent vague helper variables or placeholders that hide the calculation.
- Use structured English and pseudocode with explicit data points, conditions, and outputs.
- Prefer simple step-by-step pseudocode over dense formulas.
- Write each rule so the triggering data point, condition, and output are all explicit.
- When determining priority, process outlier and exception rules first, then day-type and time-of-day rules, then shorter-period thresholds, then longer-period thresholds.
- If any fields are unable to be converted into psuedocode, add these to the `Conditions not considered by the pseudocode` section, and explain why they are not included.
- Return markdown only.
"""


PSEUDOCODE_GENERIC_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
{goal}

Available fields:
{fields}

Shared configuration approach:
{generic_prompt}

Reusable ruleset checks:
{ruleset_question_block}

Ruleset-specific constraints:
{ruleset_constraints}

{common_constraints}

Required markdown structure:

{required_markdown_structure}
"""


PSEUDOCODE_VARIANT_PROMPT_CONFIG = {
    OVERTIME_CREATION_RULESET: {
        "goal": """- Convert the supplied reviewed overtime creation guide into bullet-point pseudocode.
- Classify whether worked hours are `Ordinary_Hours` or `Overtime_Hours`.
- Treat `Unallocated_Hours` as the total hours worked that still need ordinary/overtime classification. This will initially be set to all hours, and will reduce based on hours being allocated. 
- For this task, any hours that are not ordinary hours are overtime.
- Focus on what causes hours to become overtime, using explicit data points, conditions, and outputs rather than narrative explanation.""",
        "ruleset_constraints": """- Apply rules only to currently `Unallocated_Hours`.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining `Unallocated_Hours` to `Ordinary_Hours` after all overtime triggers have been applied.
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts.
- If the ruleset applies to all employees, it is not necessary to repeat the employee cohort unless a rule targets a narrower cohort.
- Prefer compact if/then style statements that can be translated into configuration logic without a payroll-expert explanation layer.""",
        "required_markdown_structure": """# Overtime pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Conditions not considered by the pseudocode

## Implementation notes""",
        "user_instructions": (
            "Treat this as overtime creation mode. Determine which worked hours become "
            "overtime and which remain ordinary hours. Use structured English and "
            "pseudocode with explicit data points, conditions, and outputs. Do not "
            "calculate overtime multipliers or pay outcomes."
        ),
        "repair_instructions": (
            "Keep this in overtime creation mode. Repair the pseudocode so it "
            "correctly determines which hours become overtime, without switching into "
            "multiplier or payment-consequence logic. Keep the output structured and "
            "configuration-oriented."
        ),
    },
    OVERTIME_CONSEQUENCE_RULESET: {
        "goal": """- Convert the supplied reviewed overtime consequence guide into bullet-point pseudocode.
- Determine what overtime consequence applies once hours are already overtime.
- The question to answer is 'now these hours are classified as overtime, what consequence applies?'
- Do not classify ordinary hours versus overtime hours in this mode unless a source rule expressly needs that distinction as a condition.
- Focus on consequence outcomes such as multipliers, minimum payments, ordinary-rate exceptions, meal entitlements, paid-release outcomes, and weekend/public-holiday overrides, expressed as explicit configuration logic.""",
        "ruleset_constraints": """- Treat the input as already-overtime hours or already-identified overtime circumstances that now need the correct consequence applied.
- Do not use `Ordinary_Hours` and `Overtime_Hours` as the primary outputs in this mode.
- Use implementation outputs such as `Overtime_Rate_Multiplier`, `Minimum_Payment_Hours`, `Meal_Allowance_Payable`, `Meal_Allowance_Amount`, `Paid_Release_Required`, `Paid_Release_Minimum_Hours`, `Apply_Ordinary_Rate_Instead`, `Weekend_Public_Holiday_Override`, or similarly explicit consequence outputs when supported by the rules.
- Split distinct consequence outcomes into separate implementation rules when payroll would configure them separately.
- Keep trigger wording only where it is needed to identify when the consequence applies.
- If a source rule is informational context only and does not change the outcome, place it in `Implementation notes` rather than forcing it into executable pseudocode.
- Prefer direct condition/output statements over explanatory prose.""",
        "required_markdown_structure": """# Overtime consequence pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Conditions not considered by the pseudocode

## Implementation notes""",
        "user_instructions": (
            "Treat this as overtime consequence mode. The input rules already assume "
            "the relevant hours or circumstances are overtime. Determine the correct "
            "consequence to apply, such as multipliers, minimum payments, paid release, "
            "meal entitlements, ordinary-rate exceptions, or other post-overtime "
            "outcomes. Use structured English and pseudocode with explicit data points, "
            "conditions, and outputs. Prefer direct condition/output statements. Do not "
            "rebuild overtime creation logic unless a source rule expressly needs it as "
            "a condition."
        ),
        "repair_instructions": (
            "Keep this in overtime consequence mode. Repair the pseudocode so it "
            "applies the correct consequence after overtime already exists. Do not "
            "drift into classifying ordinary versus overtime hours unless a source rule "
            "expressly requires that condition. Keep the output structured and "
            "configuration-oriented."
        ),
    },
    PENALTIES_RULESET: {
        "goal": """- Convert the supplied reviewed penalties guide into bullet-point pseudocode.
- Determine what penalty, shift allowance, or supporting break-between-work-period rule applies based on when the employee works.
- Do not classify ordinary hours versus overtime hours as the primary task in this mode.
- Focus on explicit penalty outputs such as multipliers, fixed hourly add-ons, whole-shift application flags, supporting break-gap requirements, and paid-release consequences where supported by the reviewed rules.""",
        "ruleset_constraints": """- Use explicit outputs such as `Penalty_Applies`, `Penalty_Category`, `Penalty_Rate_Multiplier`, `Penalty_Fixed_Add_On_Per_Hour`, `Penalty_Applies_To_Entire_Shift`, `Minimum_Break_Between_Shifts_Required`, `Paid_Release_Required`, or similarly direct fields when supported by the rules.
- Distinguish whole-shift qualification rules from rules that apply only to qualifying hours.
- Distinguish shift commencement tests from shift end tests and from actual-hours tests.
- Keep employee cohort and arrangement checks only where the reviewed rules genuinely require them.
- Supporting non-financial break-gap rules may appear as operational checks or implementation notes. Do not invent a premium payment where the reviewed rule does not state one.
- Prefer direct condition/output statements over explanatory prose.""",
        "required_markdown_structure": """# Penalties pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Conditions not considered by the pseudocode

## Implementation notes""",
        "user_instructions": (
            "Treat this as penalties mode. Determine the correct penalty, shift allowance, "
            "or supporting break-between-work-period rule based on when the employee works. "
            "Use structured English and pseudocode with explicit data points, conditions, "
            "and outputs. Produce explicit penalties outputs rather than ordinary/overtime "
            "hour classification, and keep non-financial supporting break-gap rules where supported."
        ),
        "repair_instructions": (
            "Keep this in penalties mode. Repair the pseudocode so it applies the correct "
            "penalty, shift allowance, or supporting break-between-work-period rule without "
            "falling back to overtime creation logic. Preserve explicit penalties outputs and "
            "keep non-financial supporting rules where the reviewed rules support them."
        ),
    },
}


def _system_prompt_for_ruleset(ruleset_key: str, fields: str) -> str:
    ruleset_variant = PSEUDOCODE_VARIANT_PROMPT_CONFIG.get(
        ruleset_key,
        PSEUDOCODE_VARIANT_PROMPT_CONFIG[OVERTIME_CREATION_RULESET],
    )
    return PSEUDOCODE_GENERIC_SYSTEM_PROMPT_TEMPLATE.format(
        goal=ruleset_variant["goal"],
        fields=fields,
        ruleset_constraints=ruleset_variant["ruleset_constraints"],
        generic_prompt=GENERIC_PAYROLL_CONFIGURATION_PROMPT,
        ruleset_question_block=common_overtime_question_block(ruleset_key),
        common_constraints=PSEUDOCODE_GENERIC_CONSTRAINTS,
        required_markdown_structure=ruleset_variant["required_markdown_structure"],
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
    ruleset_variant = PSEUDOCODE_VARIANT_PROMPT_CONFIG.get(
        ruleset_key,
        PSEUDOCODE_VARIANT_PROMPT_CONFIG[OVERTIME_CREATION_RULESET],
    )
    user_prompt = (
        f"Reviewed source markdown: {source_file}\n\n"
        f"Ruleset mode instruction: {ruleset_variant['user_instructions']}\n\n"
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
    ruleset_variant = PSEUDOCODE_VARIANT_PROMPT_CONFIG.get(
        ruleset_key,
        PSEUDOCODE_VARIANT_PROMPT_CONFIG[OVERTIME_CREATION_RULESET],
    )
    user_prompt = (
        f"Reviewed source markdown: {source_file}\n\n"
        f"Ruleset mode instruction: {ruleset_variant['repair_instructions']}\n\n"
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


def first_top_level_bullets(markdown: str, count: int = 5) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- "):
            if current:
                selected.append("\n".join(current))
                if len(selected) == count:
                    break
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)

    if len(selected) < count and current:
        selected.append("\n".join(current))

    if len(selected) < count:
        raise CoreOvertimePseudocodeError(
            f"Expected at least {count} top-level bullets, found {len(selected)}."
        )

    return "\n".join(selected[:count])


def overtime_rule_bullets(markdown: str) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- Overtime - "):
            if current:
                selected.append("\n".join(current))
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)
            continue

        if current and line.startswith("- "):
            selected.append("\n".join(current))
            current = []

    if current:
        selected.append("\n".join(current))

    if not selected:
        raise CoreOvertimePseudocodeError(
            "Expected at least one top-level 'Overtime - ' entitlement bullet."
        )

    return "\n".join(selected)
