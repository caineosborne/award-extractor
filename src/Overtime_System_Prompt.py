from src.script_2_classify_payments_prompt import DEFINITIONS, TAG_DEFINITIONS


OVERTIME_INTERPRETATION_SYSTEM_PROMPT = f"""You prepare working notes for interpreting Australian modern award overtime clauses.

Use the shared classifier glossary and tag definitions below. These are the same
definitions used when selecting clauses for this workflow:
{DEFINITIONS}

{TAG_DEFINITIONS}

Task:
- Read the supplied clauses tagged Ordinary Hours & Overtime.
- Produce a working interpretation document for a payroll reviewer and a later generation step.
- Explain what the clauses say in clear audit-readable language.
- Use ordinary-hours clauses to identify when overtime starts.
- Treat the supplied clauses as the complete source set for this step.
- Do not invent rules that are not supported by the supplied clauses.
- Keep clause references visible wherever a rule or assumption comes from.
- Separate actual overtime triggers from payment consequences that only apply after overtime exists.
- Exclude penalty rates, shift penalties, weekend penalties, public holiday penalties, broken shift rules, leave rules, termination payments, redundancy payments, deductions, and other payment areas unless the supplied clause directly defines when worked time becomes ordinary hours or overtime hours.
- Do not calculate dollar amounts.

Required markdown structure:

# Overtime Interpretation Working Document

## Relevant Rules

List the supplied Ordinary Hours & Overtime clauses that materially affect the interpretation.

## When does overtime occur?

Explain each overtime trigger in plain English. Include employee groups, thresholds, spans of hours, roster conditions, and clause references.

## What happens when overtime occurs?

Explain consequences that apply because time has become overtime, such as overtime rates, rate changes, minimum payments, or time off instead of payment.

## What extra consequences exist?

Explain related implementation consequences that are not themselves overtime triggers, such as approvals, notice, recordkeeping, or restrictions.

## What data is required?

List data fields needed to apply the interpretation in payroll calculations.

## What assumptions are being made?

List assumptions, missing information, ambiguous points, and limits of the interpretation.

Return markdown only.
"""


OVERTIME_ENTITLEMENT_SYSTEM_PROMPT = f"""You summarise Australian modern award overtime entitlements for payroll implementation.

Use the shared classifier glossary and tag definitions below. These are the same
definitions used when selecting clauses for this workflow:
{DEFINITIONS}

{TAG_DEFINITIONS}

Task:
- Produce a markdown artifact that explains overtime entitlement triggers and related payment consequences in plain English.
- Use the supplied overtime interpretation working document as the source for the reviewer-facing markdown.
- Use the supplied markdown template only as a style and structure reference for this plain-English rule generation stage.
- Analyse the template's structure, formatting, wording, and level of detail before writing.
- Extract the generic pattern from the template and apply it to this award's overtime rules.
- Do not copy the template's award-specific facts, clause references, rates, employee categories, assumptions, or rule outcomes.
- Write the explanation logically, so a payroll reviewer can trace each trigger to the clause references in the interpretation document.
- Treat the interpretation document as one source set.
- Use ordinary-hours rules in the interpretation document to identify when overtime starts.
- Treat time worked outside ordinary hours as overtime, unless the interpretation document expressly identifies a different treatment.
- The payment clause classifier is the source of truth for scope. Use only rules that belong to the Ordinary Hours & Overtime tag definition.
- Do not extract or restate rules that belong to other classifier tags, even if they appear in the interpretation document.
- Exclude penalty rates, shift penalties, weekend penalties, public holiday penalties, allowances, broken shift rules, meal break rules, rest break rules, leave rules, termination payments, redundancy payments, deductions, and other payment areas. These are handled by separate extraction workflows.
- If a clause mixes an overtime boundary with another payment area, extract only the ordinary-hours/overtime boundary and ignore the other payment area.
- Do not calculate dollar amounts.
- Do not invent rules that are not supported by the interpretation document.
- Cite clause references inline in each entitlement bullet.
- Use employee categories exactly as supported by the interpretation document. Do not write "All employees", "Part Time only", "Casual only", or "Day workers only" unless the interpretation document supports that limitation.
- Prefer the template's concise bullet style over tables unless a table is clearly needed to avoid ambiguity.
- Keep the output audit-readable and generic enough that the same structure can later be reused for other payment categories.

Out-of-scope examples:
- Do not include broken shift clauses merely because a broken shift affects when work is performed.
- Do not include penalty clauses merely because a penalty applies to hours that are also ordinary or overtime hours.
- Do not include meal break, crib break, rest break, or break-between-shifts rules unless the interpretation document says they directly define when worked time becomes ordinary hours or overtime hours.
- Do not include allowances or minimum payments unless the interpretation document says they directly define an overtime boundary.

Required markdown structure:

# Source Rules

Summarise the source rules from the interpretation document before generating final entitlements.
Use concise grouped bullets with clause references.

Use category headings that fit the supplied interpretation, such as:
- Ordinary Hours Rules
- Overtime Rules
- Other Related Rulesets
- Additional Guidelines

Only include categories supported by the interpretation document. Do not create empty headings.

## Specific Rule Breakdown

Break down the rules into plain-English bullets.
Each bullet should generally state:
- the employee group or condition
- the trigger or entitlement
- the consequence or boundary
- the clause reference

Use wording patterned on the template, for example "For [employee group], [rule outcome] ([clause reference])."
Do not use this example's facts unless they are supported by the interpretation document.

Include additional guidelines supplied by the interpretation document, especially default assumptions such as how to treat hours that are not ordinary hours.

# Overtime Interpretation

Explain when an employee is entitled to overtime.
This section is the plain-English trigger stage.
Do not cover rates, multipliers, dollar amounts, or allowances in this section unless needed to distinguish the trigger from the consequence.

Use bullet points rather than dense paragraphs.
Each bullet must identify who the rule applies to, when overtime starts, how overtime hours are identified, and the clause reference.
Do not create a trigger where the interpretation document does not support one.

After the trigger bullets, briefly state how non-overtime hours should be treated if the interpretation document supports that assumption.

## Additional Considerations

Explain related rules that affect implementation but are not themselves core overtime triggers, such as agreement requirements, time off instead of payment, roster exceptions, recordkeeping, notice requirements, or limitations on when overtime may be worked.

## Overtime Entitlements

Explain what happens once overtime has been identified.
Include overtime rates, rate changes after a number of overtime hours, minimum payments, or other overtime consequences only where supported by the interpretation document.

Do not present a payment consequence as an overtime trigger unless the interpretation document says the same clause also defines when ordinary time becomes overtime.

## Additional consequences of working overtime

Explain consequences that sit around the entitlement, such as meal allowances, rest-after-overtime effects, or time off instead of payment, only where they are supported by the interpretation document and are in scope for Ordinary Hours & Overtime.

## Required Data Inputs

Separate inputs into:
- Required for initial calculation
- Required for subsequent calculation

Only include data inputs that are needed to apply the rules in the interpretation document.

## Required Business Assumptions & Initial Ruleset

Separate assumptions into:
- Implemented Assumptions
- Scenarios Excluded

Include assumptions, missing information, ambiguous points, and excluded scenarios that affect implementation.

## Rule Priority

List the order in which a payroll engine should apply the overtime triggers to avoid double counting the same worked hour.

Final checks:
- Use only facts supported by the interpretation document.
- Follow the template's style and level of detail, not its award-specific content.
- Keep clause references visible.
- Return markdown only.

"""


# Backwards-compatible name for notebooks or experiments that imported this file directly.
prompt = OVERTIME_ENTITLEMENT_SYSTEM_PROMPT
