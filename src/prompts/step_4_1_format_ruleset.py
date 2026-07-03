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


FORMATTER_SYSTEM_PROMPT = f"""You convert a reviewed payroll ruleset into a polished
human-readable payroll guide.

Requirements:
{GENERIC_PAYROLL_CONFIGURATION_PROMPT}

- Use only the supplied reviewed ruleset for award-specific facts.
- This is a formatting step, not a summarisation or rewriting step.
- The output must be lossless in substance: every reviewed rule must remain represented in the formatted guide.
- Do not delete, omit, merge, split, generalise, or invent substantive rules.
- Do not move a rule into a different meaning just to make the guide shorter or fit the template better.
- Treat the supplied template as a structural guide, not a hard contract.
- Only keep headings and sections that are supported by the reviewed ruleset.
- Do not force rare cohort splits or empty sections just because they appear in the template.
- Keep the output concise and easy to scan, but never at the expense of losing a reviewed rule.
- Use short markdown bullet points under each heading.
- Write each rule as clearly and operationally as possible so it can be read in isolation by a payroll reviewer.
- Preserve the substantive rule content from the reviewed ruleset. Do not omit a reviewed rule merely to make the guide shorter.
- Do not collapse distinct thresholds, limits, spans, spreads, multipliers, minimum payments, cohort-specific rules, or clause-specific exceptions into vague summaries.
- Preserve employee groups, thresholds, assumptions, consequences, and clause references from the source.
- Keep clause references visible in every rule bullet, preferably at the end in square brackets.
- Do not invent rules, clause references, headings, or categories that are not supported by the source.
- Do not add a rule that is not already present in the reviewed ruleset.
- Ignore any validation-notes preamble in the source and format only the actual rules.
- Every rule must stay traceable to the source clauses.
- If a reviewed rule does not fit the template cleanly, keep it intact under the closest supported heading rather than rewriting its substance.
- Return markdown only.
- Do not wrap the answer in a markdown code fence.
"""


CORE_TEMPLATE_GUIDANCE = """Core template structure:

Use the supplied template as the starting shape for the output, but only retain headings that are supported by the source.
If a section is not supported by the reviewed ruleset, leave it out rather than forcing a placeholder.
"""


FORMATTER_VARIANT_INSTRUCTIONS = {
    OVERTIME_CREATION_RULESET: """Format the supplied reviewed overtime creation ruleset into a polished guide.

Use this heading structure and order exactly:

# Overtime Triggers

One short introductory sentence explaining that the following circumstances increase total overtime hours.

## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)
## Full-Time Employees Only
## Part-Time Employees Only
## Casual Employees Only
## Shift Workers
### Meal Breaks
### Rest Periods Between Shifts
### Other

Additional rules:
- Only include a heading when the source supports at least one real rule for that heading.
- Do not add headings outside this structure.
- Keep the guide focused on what causes hours to become overtime.
- Place each rule under the most specific supported heading, not under `Other` by default.
- Use `## All Employees (Full-Time, Part-Time, Casual, Day Workers And Shift Workers)` for general rules that apply across employee cohorts or are expressed generally as `employee` or `ordinary hours`, including ordinary-hours boundaries, spans, spreads, daily limits, agreed daily extensions, and Monday-to-Friday ordinary-hours rules, unless the reviewed source clearly narrows them to a smaller cohort.
- Use `### Other` only when a reviewed rule does not fit a more specific heading in the required structure.
- Do not place a general rule in `### Other` merely because it was added during review or evaluator feedback.
- Preserve ordinary-hours boundary rules clearly and explicitly where work outside that boundary may become overtime.
- Keep the actual operative numbers and conditions in the bullet text, such as daily limits, agreed extensions, spans, spreads, roster conditions, and break conditions.
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


def build_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    template_path: Path | str,
    template_markdown: str,
    ruleset_key: str,
) -> list[dict[str, str]]:
    config = overtime_ruleset_config(ruleset_key)
    user_prompt = f"""Format the supplied reviewed {config.display_name.lower()} into the required heading structure.

Reviewed ruleset source: {interpretation_path}

Template source: {template_path}

{CORE_TEMPLATE_GUIDANCE}

```markdown
{template_markdown}
```

Reusable ruleset checks:

{common_overtime_question_block(ruleset_key)}

Reviewed ruleset:

```markdown
{interpretation_markdown}
```

Subset-specific instructions:

{FORMATTER_VARIANT_INSTRUCTIONS[ruleset_key]}
"""
    return [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
