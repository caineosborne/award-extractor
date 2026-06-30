"""Prompt content for step 4A overtime guide formatting.

Used by:
- `src/script_4a_summarize_overtime.py`
"""

from __future__ import annotations

from pathlib import Path

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)


FORMATTER_SYSTEM_PROMPT = """You convert a reviewed overtime ruleset into a polished
human-readable payroll guide.

Requirements:
- Use only the supplied reviewed ruleset for award-specific facts.
- Keep the output concise and easy to scan.
- Use short markdown bullet points under each heading.
- Write each rule as clearly and operationally as possible so it can be read in isolation by a payroll reviewer.
- Preserve the substantive rule content from the reviewed ruleset. Do not omit a reviewed rule merely to make the guide shorter.
- Do not collapse distinct thresholds, limits, spans, spreads, multipliers, minimum payments, or cohort-specific rules into vague summaries.
- Preserve employee groups, thresholds, assumptions, consequences, and clause references from the source.
- Keep clause references visible in every rule bullet, preferably at the end in square brackets.
- Do not invent rules, clause references, headings, or categories that are not supported by the source.
- Ignore any validation-notes preamble in the source and format only the actual rules.
- Every rule must stay traceable to the source clauses.
- Return markdown only.
- Do not wrap the answer in a markdown code fence.
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
- Do not rewrite rules as overtime-hour creation tests unless that condition is strictly necessary to explain when the consequence applies.
""",
}


def build_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    template_path: Path | str,
    template_markdown: str,
    ruleset_key: str,
) -> list[dict[str, str]]:
    del template_path, template_markdown
    config = overtime_ruleset_config(ruleset_key)
    user_prompt = f"""Format the supplied reviewed {config.display_name.lower()} into the required heading structure.

Reviewed ruleset source: {interpretation_path}

```markdown
{interpretation_markdown}
```

{FORMATTER_VARIANT_INSTRUCTIONS[ruleset_key]}
"""
    return [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
