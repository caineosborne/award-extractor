"""Prompt content for step 5B core overtime pseudocode generation.

Used by:
- `src/script_5b_generate_overtime_pseudocode.py`
"""

from src.common.rule_inventory import RuleInventory, render_inventory_for_prompt


CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied overtime entitlement markdown into bullet-point pseudocode.
- Only classify whether worked hours are Ordinary_Hours or Overtime_Hours.
- Treat Unallocated_Hours as the total hours worked that still need ordinary/overtime classification, assume that no hours are preallocated.
- For this task, any hours that are not ordinary hours are overtime.
- Preserve the business meaning of the overtime triggers in the markdown, even if headings or bullet formatting have been edited by a human.

The output will be passed to system engineers to configure payroll rules - it does not need explanations (beyond the clauses) simply the code is sufficient.

Available fields:
{fields}

Constraints:
- Assume that you are reviewing the hours worked for a fortnight, none of these hours are currently classified as overtime or ordinary. Your task is to allocate the hours as ordinary or overtime.  You are recieving the the total hours worked for the fornight, no other hours worked.
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts. The outputs need to simply contain the amount of hours allocated to overitme, and the amount of hours as ordinary.
- If formulas refer to a specific time (eg penalties for working after 10PM) this may be stated as a derived field only where that calculation is genuinely needed and reused in more than one rule.

Do not say "IF block occurs on a day other than Monday to Friday OR block time is before 6:00 am OR block time is after 6:00 pm. Allocate that block hour to Overtime_Hours"

Say "If the shift ends after 6pm, or starts before 6am, or is worked on the weekend. Allocate any hours between shift end and 6pm as overtime"

Shift_Segments_By_Hour
- Use the plain-English overtime trigger section as the main source for ordinary/overtime classification.
- Do not rely on a rule having an exact markdown heading or bullet label. Read the complete document for meaning.
- Apply rules only to currently Unallocated_Hours.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining Unallocated_Hours to Ordinary_Hours after all overtime triggers have been applied.
- Include source clause references in comments.
- Do not create additional fields unnecessarily - for any clauses are are reliant on times, use the existing Shift Start and Shift End fields.
- If a rule needs an input that is not in the available fields, name it under Required additional inputs. Any fields that can be derived from the supplied data should be included as a calucation, rather than an additional data point.
- Do not list a derived field that is just a renamed component of an existing field. For example, do not derive `Shift_Start_Time` from `Shift_Start`, `Shift_End_Time` from `Shift_End`, or `Shift_Start_Day` from `Shift_Date` unless the source rule truly requires a different representation that is not already supplied.
- Do not list straightforward calculations as separate derived fields unless they are reused across multiple rules and make the pseudocode materially clearer. For example, totals such as hours worked in the day, week, or fortnight, hours over 10 in a day, or hours outside rostered hours should usually appear as calculations inside the pseudocode rather than as standalone derived fields.
- Treat derived fields as optional. Use the `Derived Fields` section only for non-obvious reusable calculations. If no such calculations are needed, write `None`.
- Treat `Required additional inputs` narrowly. Only include facts that are not already provided and cannot be calculated directly from the supplied fields and shift records.
- Use clear payroll variables. Do not invent vague helper variables such as offsets, safe offsets, magic masks, or placeholders that hide the calculation.
- If a rule requires segmenting a shift into hour blocks, state that as a required additional input and describe the segmentation plainly.
- Prefer simple step-by-step pseudocode over dense formulas.
- If the ruleset applies to all employees,then it is not necessary to specify the employee cohort - this is only necessary where clauses only target particular cohorts. Assume all employees are affected by all rules, unless otherwise stated.
- Do not specify clauess within the psuedo code - use rulesets that technical teams can build without being aware of the award.
- When determining the priority, ensure that all rulesets that affect outlier situations are processed first, followed by any rules time of days are processed first, before those reviewing total hours in a day, before those that affect a week, or those that affect a longer time period.  When listing the priority ensure that the rules here match what is shown in the pseudocode section.
- Return markdown only.

Required markdown structure:

# Overtime pseudocode

## Derived Fields

## Required additional inputs

## Rule priority

## Pseudocode

## Implementation notes
"""

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


def build_messages(
    source_file: str,
    overtime_summary_markdown: str,
    source_inventory: RuleInventory | None = None,
) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE.format(fields=fields)
    inventory_text = ""
    if source_inventory is not None:
        inventory_text = (
            "Required rule inventory derived from the reviewed source markdown:\n"
            f"{render_inventory_for_prompt(source_inventory)}\n\n"
            "Every inventory rule must be represented in the pseudocode or implementation notes. "
            "Do not omit a reviewed rule merely because another rule sounds similar.\n\n"
        )
    user_prompt = (
        f"Source overtime interpretation markdown: {source_file}\n\n"
        f"{inventory_text}"
        "Complete overtime interpretation markdown to convert:\n"
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
) -> list[dict[str, str]]:
    fields = "\n".join(
        f"- {field}: {description}" for field, description in PSEUDOCODE_FIELDS.items()
    )
    system_prompt = CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE.format(fields=fields)
    user_prompt = (
        f"Source overtime interpretation markdown: {source_file}\n\n"
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
