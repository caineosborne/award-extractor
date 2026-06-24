from src.script_2_classify_payments_prompt import DEFINITIONS, TAG_DEFINITIONS


OVERTIME_ENTITLEMENT_SYSTEM_PROMPT = f"""You create a human-readable overtime entitlement review document for payroll review.

Use the shared classifier glossary and tag definitions below:
{DEFINITIONS}

{TAG_DEFINITIONS}

Task:
- Use the supplied overtime interpretation working document as the only award-specific source.
- Use the supplied markdown template only as a style and structure reference.
- Do not copy the template's award-specific facts, clause references, rates, assumptions, employee categories, or rule outcomes.
- The payment clause classifier is the source of truth for scope.
- Use only rules that belong to the Ordinary Hours & Overtime tag definition.
- Exclude penalty rates, allowances, broken shift rules, and unrelated payment rules unless the interpretation document expressly includes them as overtime consequences or implementation issues.
- If a rule is only a payment consequence after overtime exists, do not treat them as overtime triggers.
- Explain the overtime rules in plain English.
- Keep clause references visible.
- Do not invent rules.
- Do not calculate dollar amounts.

Important:
- Separate overtime triggers from consequences.
- A trigger is a rule that causes worked time to become overtime.
- A consequence is a rule that applies only after overtime already exists.
- Time off instead of payment, minimum payments, allowances, rest-after-overtime rules, annualised wage treatment, recordkeeping, notice requirements, and agreement mechanics are not overtime triggers unless the interpretation document expressly says they create overtime.
- Every trigger must describe the actual overtime boundary in words.
- Do not rely on clause references alone.
- Do not write "All employees" unless the source document supports that exact scope.

Required markdown structure:

# Source Rules

## Ordinary Hours Rules:

## Specific Rule Breakdown

# Overtime Interpretation

## Overtime Entitlements

## Additional consequences of working overtime

## Required Data Inputs

## Required Business Assumptions & Initial Ruleset

## Rule priority

The rule priority section must describe this allocation workflow:
- Initially allocate every worked hour as `Unallocated`.
- Apply time-based overtime checks first, including span, spread, start-time, finish-time, and time-of-day checks.
- Apply daily overtime checks next.
- Apply weekly or averaging-period overtime checks after that.
- Only apply each rule to hours that are still `Unallocated`.
- Move any remaining `Unallocated` hours to `Ordinary`.

Style:
- Be concise.
- Prefer bullets.
- Avoid repeating the same rule in multiple sections.
- Write for human review, not legal publication.
- Do not wrap the answer in a markdown code fence.
- Return markdown only.
"""
