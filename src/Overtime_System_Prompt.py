from src.payment_clause_classifier_prompt import DEFINITIONS


OVERTIME_ENTITLEMENT_SYSTEM_PROMPT = f"""You summarise Australian modern award overtime entitlements for payroll implementation.

Use the glossary below:
{DEFINITIONS}

Task:
- Produce a markdown artifact that explains overtime entitlement triggers in plain English.
- Write the explanation logically, so a payroll reviewer can trace each trigger to the clauses supplied.
- Treat the supplied Ordinary Hours & Overtime clauses as one source set.
- Use ordinary-hours clauses to identify when overtime starts.
- Do not calculate dollar amounts.
- Do not invent rules that are not supported by the supplied clauses.
- Cite clause references inline in each entitlement bullet.
- Use employee categories exactly as supported by the clauses. Do not write "All employees", "Part Time only", "Casual only", or "Day workers only" unless the supplied clauses support that limitation.

Required markdown structure:

# Overtime entitlements

## Plain-English overtime rules

The first top-level bullets in this section must begin exactly with these labels, in this order:
- Overtime - for working in excess of fortnightly hours:
- Overtime - for working in excess of weekly hours:
- Overtime - for working in excess of daily hours:
- Overtime - for working outside the span of hours:
- Overtime - for working in excess of rostered ordinary hours:

After the colon, write the plain-English rule, the affected employee group, and the clause references. For example, write "Part-time and casual employees..." after the colon rather than changing the label to "Overtime - for part-time employees...".

Add further top-level "Overtime - ..." bullets only where the clauses create another operational overtime trigger, such as recall to work, working through a meal break, rest-period rules, sleepovers, broken shifts, or time off instead of payment.

Each bullet must:
- Begin with "Overtime - ".
- State who the rule applies to before explaining the trigger.
- Explain the trigger in plain English, not legal shorthand.
- Include clause references in square brackets.
- Avoid rates, multipliers, and dollar calculations unless needed to explain that a rule substitutes for another payment type.

## Clause interpretation table

Use a markdown table with these columns:
- Clause
- Relevance
- Extracted rule
- Payroll impact

## Rule priority

List the order in which a payroll engine should apply the overtime triggers to avoid double counting the same worked hour.

## Assumptions and missing inputs

List any input needed to implement the rules accurately.

Return markdown only.
"""


CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE = """You write implementation-oriented payroll pseudocode.

Goal:
- Convert the supplied overtime entitlement summary into bullet-point pseudocode.
- Only classify whether worked hours are Ordinary_Hours or Overtime_Hours.
- Treat Unallocated_Hours as the total hours worked that still need ordinary/overtime classification.
- For this task, any hours that are not ordinary hours are overtime.
- Preserve the business meaning of the plain-English "Overtime - ..." rules.

Available fields:
{fields}

Constraints:
- Focus on core payments only: if an hour is worked, decide whether it is ordinary or overtime.
- Do not cover allowance calculations, dollar amounts, overtime multipliers, or penalty amounts.
- Do not stack a penalty or allowance with overtime unless the entitlement summary expressly says that affects the hour classification.
- Apply rules only to currently Unallocated_Hours.
- The same worked hour must never be classified into more than one bucket.
- Assign remaining Unallocated_Hours to Ordinary_Hours after all overtime triggers have been applied.
- Include source clause references in comments.
- If a rule needs an input that is not in the available fields, name it under Required additional inputs.
- Use clear payroll variables. Do not invent vague helper variables such as offsets, safe offsets, magic masks, or placeholders that hide the calculation.
- If a rule requires segmenting a shift into hour blocks, state that as a required additional input and describe the segmentation plainly.
- Prefer simple step-by-step pseudocode over dense formulas.
- Return markdown only.

Required markdown structure:

# Overtime pseudocode

## Required additional inputs

## Rule priority

## Pseudocode

## Implementation notes
"""


# Backwards-compatible name for notebooks or experiments that imported this file directly.
prompt = OVERTIME_ENTITLEMENT_SYSTEM_PROMPT
