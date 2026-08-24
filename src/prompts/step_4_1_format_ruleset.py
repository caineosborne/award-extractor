"""Prompt content for step 4.1 ruleset guide formatting.

Used by:
- `src/step_4_1_format_ruleset/`
"""

from __future__ import annotations

from pathlib import Path

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
    overtime_ruleset_config,
)
from src.prompts.overtime_common_prompt_blocks import (
    GENERIC_PAYROLL_CONFIGURATION_PROMPT,
    common_overtime_question_block,
)
from src.prompts.ruleset_subset_prompt_blocks import (
    ruleset_prompt_family,
    subset_shared_prompt_block,
)


FORMAT_RULESET_GENERIC_SYSTEM_PROMPT = f"""You convert a reviewed payroll ruleset into a polished
human-readable payroll guide, focusing on improving the layout and readability. 

Requirements:
{GENERIC_PAYROLL_CONFIGURATION_PROMPT}

- Use only the supplied reviewed ruleset for award-specific facts.
- This is a presentation rewrite, not a new interpretation. Rewrite the wording
  into plain English without changing the reviewed rule's meaning.
- The output must be lossless in substance: every reviewed rule must remain represented in the formatted guide.
- Ensure clause numbers are present in the output, preferably at the end of each rule in square brackets.
- Be careful when aggregating so that no operational threshold is lost. For
  example, if a rule appears for all employees and for full-time employees, it
  may be combined only when its scope and effect are identical.
- Do not delete, omit, merge, generalise, or invent substantive rules. Keep one
  top-level output bullet for each reviewed source rule. A long list of numeric
  alternatives may use short indented bullets.
- Do not move a rule into a different meaning just to make the guide shorter or fit the template better.
- Treat the supplied template as a structural guide, not a hard contract.
- Only keep headings and sections that are supported by the reviewed ruleset.
- Do not force rare cohort splits or empty sections just because they appear in the template.
- Keep the output concise and easy to scan, but never at the expense of losing a reviewed rule.
- Use short markdown bullet points under each heading.
- Start every top-level bullet with the direct payroll rule or outcome. Prefer
  forms such as `Overtime is created when ...`, `The overtime rate is ...`, or
  `A penalty applies when ...`.
- Keep the lead rule to one short sentence where practical. Use indented bullets
  only when they make a list of thresholds or genuine exceptions easier to read.
- If the reviewed 3.2 rule is already understandable, retain its sentence and
  make only the smallest edits needed for plain English.
- Do not expand a reviewed rule into an explanation of how boundaries, triggers,
  cohorts, or configurations interact. Step 3.2 has already completed that
  interpretation.
- Write for a payroll reviewer who should understand the operative rule without
  reading the award-style drafting behind it.
- Prefer active, everyday language. Replace abstract wording with the employee,
  hours, threshold, and result wherever the reviewed rule supports them.
- Do not add explanatory labels such as `Ordinary-hours boundary`, `not a
  standalone overtime trigger`, `Thresholds`, or `Limit`. State the rule itself.
- Do not begin a rule with `Select` unless the payroll reviewer genuinely must
  choose between alternative configurations. State the rule that creates the
  payroll result first.
- Preserve the substantive rule content from the reviewed ruleset. Do not omit a reviewed rule merely to make the guide shorter.
- Do not collapse distinct thresholds, limits, spans, spreads, multipliers, minimum payments, cohort-specific rules, or clause-specific exceptions into vague summaries.
- If the source contains overlapping but plausible reviewed rules, preserve them rather than deduplicating aggressively at the formatting stage.
- Preserve employee groups, thresholds, assumptions, consequences, and clause references from the source.
- Keep clause references at the end of the lead bullet in square brackets.
- Do not invent rules, clause references, headings, or categories that are not supported by the source.
- Do not add a rule that is not already present in the reviewed ruleset.
- Ignore any validation-notes preamble in the source and format only the actual rules.
- Every rule must stay traceable to the source clauses.
- If a reviewed rule does not fit the template cleanly, keep it intact under the closest supported heading rather than rewriting its substance.
- Return markdown only.
- Do not wrap the answer in a markdown code fence.
"""


FORMAT_RULESET_GENERIC_TEMPLATE_GUIDANCE = """Core template structure:

Use the supplied template as the starting shape for the output, but only retain headings that are supported by the source.
If a section is not supported by the reviewed ruleset, leave it out rather than forcing a placeholder.
"""


FORMAT_RULESET_VARIANT_INSTRUCTIONS = {
    OVERTIME_CREATION_RULESET: """Format the supplied reviewed overtime creation ruleset into a polished guide.

Use this heading structure and order exactly:

# Overtime Triggers

One short introductory sentence explaining that the following circumstances increase total overtime hours.

## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)
## Full-Time Employees Only
## Part-Time Employees Only
## Casual Employees Only
## Shift Workers 
## Day Workers 
### Meal Breaks
### Rest Periods Between Shifts
### Other

Additional rules:
- Only include a heading when the source supports at least one real rule for that heading.
- Do not add headings outside this structure.
- Add additional headings as necessary, if it is appropriate for grouping. 
- Keep the guide focused on what causes hours to become overtime.
- Place each rule under the most specific supported heading, not under `Other` by default.
- Use `## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)` for general rules that apply across employee cohorts or are expressed generally as `employee` or `ordinary hours`, including ordinary-hours boundaries, spans, spreads, daily limits, agreed daily extensions, and Monday-to-Friday ordinary-hours rules, unless the reviewed source clearly narrows them to a smaller cohort.
- Use `### Other` only when a reviewed rule does not fit a more specific heading in the required structure.
- Do not place a general rule in `### Other` merely because it was added during review or evaluator feedback.
- Preserve ordinary-hours boundary rules clearly where work outside that
  boundary may become overtime, using the same degree of certainty as step 3.2.
- When the reviewed rule states that work outside an applicable ordinary-hours
  boundary is overtime, use one direct sentence. Do not append a warning that the
  rule must be tested under a full-time, part-time, or casual trigger.
- Keep an express alternative work-arrangement rule, such as a shiftworker
  override, in its own bullet or section instead of adding it as a legal caveat
  to the day-worker boundary rule.
- Keep the actual operative numbers and conditions in the bullet text, such as daily limits, agreed extensions, spans, spreads, roster conditions, and break conditions.
- Example style:
  - `Overtime is created when an employee works more than the daily limit for their shift: 8 hours for a day shift or 10 hours for a night shift. [22.1(c), 25.1]`
  - `For a day worker, work outside 6.00 am to 6.00 pm Monday to Friday is overtime. [22.2(a)]`
- Do not replace a specific reviewed rule with a shorter high-level paraphrase if that would remove an operational threshold or condition.
- Do not add new operational claims, even if they seem implied by the source.
- Do not include overtime multipliers, penalty amounts, allowance amounts, or payment consequences except where needed to explain that a rule is out of scope.
""",
    OVERTIME_CONSEQUENCE_RULESET: """Format the supplied reviewed overtime consequence ruleset into a polished guide.

Use this heading structure and order exactly:

# Overtime Consequences

One short introductory sentence explaining that the following rules describe what is paid, owed, or applied once overtime already exists.

## All Employees
## Full-Time And Part-Time Employees
## Casual Employees
## Part-Time Employees Only
## Shift Workers
## Day Workers
### Minimum Payments And Blocks
### Allowances And Meal Entitlements
### Rest And Release Consequences
### Roster And Transfer Consequences
### Day-Type And Special Circumstance Consequences
### Other

Additional rules:
- Only include a heading when the source supports at least one real rule for that heading.
- Do not add headings outside this structure.
- Keep the guide focused on what consequence applies once hours are already overtime.
- Place each rule under the most specific supported heading, not under `### Other` by default.
- Use `## All Employees`, `## Full-Time And Part-Time Employees`, `## Casual Employees`, or `## Part-Time Employees Only` whenever the reviewed rule clearly matches one of those cohorts.
- Use `### Other` only when a reviewed rule does not fit a more specific heading in the required structure.
- Include overtime multipliers, minimum payments, meal entitlements, ordinary-rate exceptions, paid-release outcomes, and weekend/public-holiday overtime consequences where supported.
- Keep the actual multiplier, block, minimum payment, entitlement, and cohort condition in the bullet text itself.
- You may merge or deduplicate two reviewed rules only where they have the same cohort scope, the same operative outcome, the same thresholds or time bands, and the same clause references.
- If any of cohort scope, operative outcome, thresholds, time bands, or clause references differ, keep the rules separate.
- Do not replace a specific reviewed rule with a shorter high-level paraphrase if that would remove an operational rate, threshold, minimum, or condition.
- Do not add new operational claims, even if they seem implied by the source.
- Do not rewrite rules as overtime-hour creation tests unless that condition is strictly necessary to explain when the consequence applies.
""",
    PENALTIES_RULESET: """Format the supplied reviewed penalties ruleset into a polished guide.

Use this heading structure and order exactly:

# Penalties

One short introductory sentence explaining that the following rules describe penalty rates, shift allowances, and break-between-work-period rules that affect or support payroll outcomes based on when work is performed.

## Shift-Based Allowances And Penalties
## Time-Band And Day-Based Penalties
## Day Workers
## Breaks Between Work Periods
## Supporting Conditions

Additional rules:
- Only include a heading when the source supports at least one real rule for that heading.
- Do not add headings outside this structure.
- Keep the guide focused on penalties, shift allowances, and supporting break-gap conditions for this ruleset.
- Place each rule under the most specific supported heading.
- Preserve explicit multipliers, fixed dollar add-ons, named days, public-holiday qualifiers, time bands, cohort splits, and clause references.
- Keep whole-shift qualification rules separate from specific-hours rules in the bullet text itself.
- Keep shift commencement tests distinct from shift end tests and distinct from actual-hours tests.
- Keep non-financial break-gap rules representable where the reviewed rules support them. Do not force every break-between-work-period rule into a premium-pay statement.
- Do not add new operational claims, even if they seem implied by the source.
- Do not drift into overtime creation or overtime consequence summaries unless a reviewed rule expressly requires that context to identify the penalties outcome.
""",
}


FORMAT_RULESET_STEP_FAMILY_INSTRUCTIONS = {
    "overtime": """Step 4.1 family instructions for overtime subsets:
- Keep the guide operational and audit-friendly.
- Preserve concrete thresholds, clause references, scope limits, and exceptions in the bullet text itself.
- Do not rewrite the formatted guide into a calculator outcome document or a high-level summary.""",
    "penalties": """Step 4.1 family instructions for penalties subsets:
- Keep the guide operational and audit-friendly.
- Preserve concrete multipliers, fixed add-ons, qualifying tests, scope limits, and clause references in the bullet text itself.
- Do not rewrite the formatted guide into a high-level narrative or into overtime-only commentary.""",
}


def build_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    template_path: Path | str,
    template_markdown: str,
    ruleset_key: str,
) -> list[dict[str, str]]:
    config = overtime_ruleset_config(ruleset_key)
    family_key = ruleset_prompt_family(ruleset_key)
    user_prompt = f"""Format the supplied reviewed {config.display_name.lower()} into the required heading structure.

Common clauses that may appear:

The following common clauses or rules may appear in an award. If they are supported by the supplied reviewed ruleset, place them near the top of the formatted ruleset. Do not add them when they are not supported by the reviewed ruleset.

{common_overtime_question_block(ruleset_key)}

Step 4.1 subset-specific formatting instructions:

{FORMAT_RULESET_VARIANT_INSTRUCTIONS[ruleset_key]}

Subset-wide instructions:

{subset_shared_prompt_block(ruleset_key)}

Step 4.1 family instructions:

{FORMAT_RULESET_STEP_FAMILY_INSTRUCTIONS[family_key]}

Template and required structure:

{FORMAT_RULESET_GENERIC_TEMPLATE_GUIDANCE}

```markdown
{template_markdown}
```

Reviewed ruleset content:

```markdown
{interpretation_markdown}
```
"""
    return [
        {"role": "system", "content": FORMAT_RULESET_GENERIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
