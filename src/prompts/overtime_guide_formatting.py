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
- Preserve employee groups, thresholds, assumptions, consequences, and clause references from the source.
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
- Include overtime multipliers, minimum payments, meal entitlements, ordinary-rate exceptions, paid-release outcomes, and weekend/public-holiday overtime consequences where supported.
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
