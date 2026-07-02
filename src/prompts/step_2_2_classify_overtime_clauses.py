"""Prompt content for step 2.2 overtime clause classification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)
from src.prompts.shared_overtime_clause_classification import (
    SHARED_OVERTIME_CATEGORIES,
    SHARED_PRIMARY_CLASSIFICATION_RULES,
)
from src.prompts.step_2_1_classify_payments import DEFINITIONS, TAG_DEFINITIONS


CLAUSE_CLASSIFICATION_SHARED_SYSTEM_PROMPT = f"""You classify Australian modern award clauses for payroll implementation.

Use the shared classifier glossary and tag definitions below:
{DEFINITIONS}

{TAG_DEFINITIONS}

Task:
- Use only the supplied clauses tagged Ordinary Hours & Overtime.
- Classify every supplied clause into one or more categories.
- Return one primary classification and the complete list of applicable classifications.
- Keep clause references visible.
- Do not invent rules.
- Do not calculate dollar amounts.
- Explain each classification in one sentence.
- Classify the operative clause text that is actually supplied, not the heading you expect.
- Be conservative: do not label a clause as a trigger or consequence unless the text supports that label.

Shared categories:
{SHARED_OVERTIME_CATEGORIES}

Shared decision rules:
- A clause can carry more than one classification when it genuinely does more than one thing.
- Use `Overtime Consequence` only where the clause text tells the payroll system what result applies once overtime already exists, such as a multiplier, minimum payment, TOIL option, paid rest outcome, allowance consequence, or other post-overtime entitlement.
- Do not use `Overtime Consequence` merely because the clause says hours "will be paid at overtime rates" as part of explaining when the hours become overtime. In that case the clause is usually primarily an `Overtime Trigger`, even if it also carries a secondary consequence label.
- Use `Related Rule` for supporting clauses that affect interpretation context, procedure, or surrounding conditions, but that do not themselves create overtime and do not themselves state the post-overtime outcome.

Primary classification rules:
{SHARED_PRIMARY_CLASSIFICATION_RULES}
"""


CLAUSE_CLASSIFICATION_VARIANT_INSTRUCTIONS = {
    OVERTIME_CREATION_RULESET: """Important:
- Ordinary Hours Boundary clauses matter because work outside ordinary hours limits may create overtime even if the clause does not use the word overtime.
- Overtime Trigger clauses matter because this ruleset is identifying what causes overtime, not how overtime is paid.
- A clause can be both Overtime Trigger and Overtime Consequence.
- If one part of a clause states when time is overtime, when overtime applies, or when time worked will be paid at overtime rates, include Overtime Trigger in classifications even if other parts of the same clause set rates or payment consequences.
- Do not classify a clause as Overtime Trigger merely because it mentions overtime rates or payment after overtime exists.
- Consequence handling is deferred for this ruleset, but consequence clauses should still be classified accurately.
""",
    OVERTIME_CONSEQUENCE_RULESET: """Important:
- This ruleset is identifying what happens after overtime exists, not what causes overtime.
- A clause can still include both Overtime Trigger and Overtime Consequence, but only the consequence part is in scope for the downstream ruleset.
- Include clauses that define overtime rates, minimum payments, time off instead of overtime payment, rest-after-overtime outcomes, or other direct overtime consequences.
- Do not treat a clause as an overtime consequence merely because it helps define ordinary hours.
- Boundary and trigger labels can still be used when they genuinely appear in the clause, but consequence handling is the focus for this ruleset.
""",
}


CLAUSE_CLASSIFICATION_USER_PROMPT_TEMPLATE = """Using the Ordinary Hours & Overtime clauses below, classify every listed clause for the `{ruleset_label}` ruleset.

For each clause return:
- clause_number
- classification: the primary classification for the clause
- classifications: all applicable classifications for the clause
- clause_text
- explanation
- employee_cohort
- work_arrangement
- other_scope_notes

Clauses:

{clauses_text}

Special Instructions:

{variant_instructions}
""".strip()


def format_clauses_for_prompt(overtime_clauses: Mapping[str, Any]) -> str:
    """Format shortlisted clauses into clear markdown sections for the model."""
    sections: list[str] = []

    for clause_number, clause in overtime_clauses.items():
        if not isinstance(clause, Mapping):
            continue

        text = clause.get("text")
        if isinstance(text, str):
            clause_text = text
        else:
            clause_text = str(clause)

        sections.append(f"## Clause {clause_number}\n\n{clause_text}")

    return "\n\n---\n\n".join(sections)


def build_clause_classification_messages(
    overtime_clauses: Mapping[str, Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Build the prompt messages for step 2.2 clause classification."""
    config = overtime_ruleset_config(ruleset_key)
    return [
        {"role": "system", "content": CLAUSE_CLASSIFICATION_SHARED_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": CLAUSE_CLASSIFICATION_USER_PROMPT_TEMPLATE.format(
                ruleset_label=config.display_name.lower(),
                clauses_text=format_clauses_for_prompt(overtime_clauses),
                variant_instructions=CLAUSE_CLASSIFICATION_VARIANT_INSTRUCTIONS[ruleset_key],
            ),
        },
    ]
