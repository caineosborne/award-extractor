"""Prompt content for step 2.2 overtime clause classification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
    overtime_ruleset_config,
)
from src.prompts.shared_overtime_clause_classification import (
    SHARED_OVERTIME_CATEGORIES,
    SHARED_PRIMARY_CLASSIFICATION_RULES,
)
from src.prompts.overtime_common_prompt_blocks import (
    GENERIC_PAYROLL_CONFIGURATION_PROMPT,
    common_overtime_question_block,
)
from src.prompts.step_2_1_classify_payments import (
    PAYMENT_CLASSIFICATION_GENERIC_DEFINITIONS,
    PAYMENT_CLASSIFICATION_GENERIC_TAG_DEFINITIONS,
)
from src.prompts.ruleset_subset_prompt_blocks import (
    ruleset_prompt_family,
    subset_shared_prompt_block,
)


CLAUSE_CLASSIFICATION_GENERIC_SYSTEM_PROMPT = """You classify Australian modern award clauses for payroll implementation.

Analyse the provided award clauses carefully and conservatively.

Do not invent rules.

Do not calculate dollar amounts.

Keep clause references visible.
"""


CLAUSE_CLASSIFICATION_GENERIC_RULESET_LANGUAGE = f"""Shared classification glossary:

Use the shared classifier glossary and tag definitions below:
{PAYMENT_CLASSIFICATION_GENERIC_DEFINITIONS}

{PAYMENT_CLASSIFICATION_GENERIC_TAG_DEFINITIONS}

Shared classification rules:
- Use only the supplied clauses selected for this ruleset subset from step 2.1.
- Classify every supplied clause into one or more categories.
- Return one primary classification and the complete list of applicable classifications.
- Explain each classification in one sentence.
- Classify the operative clause text that is actually supplied, not the heading you expect.
- Be conservative: do not label a clause as a trigger or consequence unless the text supports that label.

Shared categories:
{SHARED_OVERTIME_CATEGORIES}

Shared decision rules:
- A clause can carry more than one classification when it genuinely does more than one thing.
- If a clause plausibly contributes to this ruleset and the text supports that contribution, prefer inclusion with a conservative classification and explanation rather than exclusion.
- Do not exclude a clause merely because another clause appears to cover similar ground. Overlap can be resolved later; missed clause coverage is harder to recover.
- Use `Overtime Consequence` only where the clause text tells the payroll system what result applies once overtime already exists, such as a multiplier, minimum payment, TOIL option, paid rest outcome, allowance consequence, or other post-overtime entitlement.
- Do not use `Overtime Consequence` merely because the clause says hours "will be paid at overtime rates" as part of explaining when the hours become overtime. In that case the clause is usually primarily an `Overtime Trigger`, even if it also carries a secondary consequence label.
- Use `Related Rule` for supporting clauses that affect interpretation context, procedure, or surrounding conditions, but that do not themselves create overtime and do not themselves state the post-overtime outcome.

Primary classification rules:
{SHARED_PRIMARY_CLASSIFICATION_RULES}

{GENERIC_PAYROLL_CONFIGURATION_PROMPT}
"""


CLAUSE_CLASSIFICATION_STEP_FAMILY_INSTRUCTIONS = {
    "overtime": """Step 2.2 family instructions for overtime subsets:
- Classify the shortlisted clauses for the selected overtime subset rather than for the entire award.
- Keep the language definitive, concrete, and implementation-oriented.
- Expect mixed clauses and classify the operative part conservatively rather than excluding plausible supported scope too early.
""",
    "penalties": """Step 2.2 family instructions for penalties subsets:
- Classify the shortlisted clauses for the penalties subset rather than for the entire award.
- Keep the language definitive, concrete, and implementation-oriented.
- Preserve supporting penalties-domain operational conditions even where they do not create a separate premium outcome.
""",
}


CLAUSE_CLASSIFICATION_STEP_SUBSET_INSTRUCTIONS = {
    OVERTIME_CREATION_RULESET: """Important:
- Ordinary Hours Boundary clauses matter because work outside ordinary hours limits may create overtime even if the clause does not use the word overtime.
- Overtime Trigger clauses matter because this ruleset is identifying what causes overtime, not how overtime is paid.
- A clause can be both Overtime Trigger and Overtime Consequence.
- If one part of a clause states when time is overtime, when overtime applies, or when time worked will be paid at overtime rates, include Overtime Trigger in classifications even if other parts of the same clause set rates or payment consequences.
- Do not classify a clause as Overtime Trigger merely because it mentions overtime rates or payment after overtime exists.
- If an ordinary-hours boundary clause states that ordinary hours may be worked between times or within a span, classify it as applying to all employees unless the clause expressly narrows the cohort.
- Do not narrow a general ordinary-hours boundary to full-time employees just because the clause also contains a full-time example, adjacent clause, or nearby averaging rule.
- If a clause plausibly helps determine when hours become overtime, prefer keeping it in scope with an explicit explanation rather than excluding it too aggressively.
- Consequence handling is deferred for this ruleset, but consequence clauses should still be classified accurately.
""",
    OVERTIME_CONSEQUENCE_RULESET: """Important:
- This ruleset is identifying what happens after overtime exists, not what causes overtime.
- A clause can still include both Overtime Trigger and Overtime Consequence, but only the consequence part is in scope for the downstream ruleset.
- Include clauses that define overtime rates, minimum payments, time off instead of overtime payment, rest-after-overtime outcomes, or other direct overtime consequences.
- Do not treat a clause as an overtime consequence merely because it helps define ordinary hours.
- Boundary and trigger labels can still be used when they genuinely appear in the clause, but consequence handling is the focus for this ruleset.
- If a clause plausibly contains an overtime consequence and the text supports that reading, prefer including it with a careful explanation rather than excluding it because the clause is mixed.
""",
    PENALTIES_RULESET: """Important:
- This ruleset is identifying penalty rates, shift allowances, and break-between-work-period rules that are relevant to the penalties subset.
- For the penalties subset, downstream handling is deterministic and all shortlisted clauses are treated as `Penalty Rule`.
- Focus on whether the clause is relevant to additional payment outcomes based on when work is performed, or to supporting break-gap and broken-shift conditions that remain in scope for penalties even without a direct premium outcome.
- Keep whole-shift qualification rules, specific-hours rules, day-type rules, and supporting break-gap rules in scope when the clause text supports them.
- Do not treat a clause as relevant to this subset merely because it describes overtime creation or an overtime-only consequence.
- If a clause plausibly contains a penalties-domain rule and the text supports it, prefer inclusion over exclusion. Duplication can be handled later; missing coverage should be avoided.
""",
}


CLAUSE_CLASSIFICATION_VARIANT_USER_PROMPTS = {
    OVERTIME_CREATION_RULESET: """Using the selected subset clauses below, classify every listed clause for the `{ruleset_label}` ruleset.""",
    OVERTIME_CONSEQUENCE_RULESET: """Using the selected subset clauses below, classify every listed clause for the `{ruleset_label}` ruleset.""",
    PENALTIES_RULESET: """Using the selected subset clauses below, classify every listed clause for the `{ruleset_label}` ruleset.""",
}


def _build_clause_classification_user_prompt(
    *,
    variant_prompt: str,
    subset_shared_instructions: str,
    step_family_instructions: str,
    ruleset_question_block: str,
    clauses_text: str,
    step_subset_instructions: str,
) -> str:
    return (
        f"{variant_prompt}\n\n"
        "Step 2.2 scope and classification instructions:\n\n"
        f"{subset_shared_instructions}\n\n"
        f"{step_family_instructions}\n\n"
        f"{step_subset_instructions}\n\n"
        "Generic prompt instructions:\n\n"
        f"{GENERIC_PAYROLL_CONFIGURATION_PROMPT}\n\n"
        f"{CLAUSE_CLASSIFICATION_GENERIC_RULESET_LANGUAGE}\n\n"
        "Reusable ruleset checks:\n\n"
        f"{ruleset_question_block}\n\n"
        "Required output for every clause:\n\n"
        f"{CLAUSE_CLASSIFICATION_OUTPUT_CONTRACT}\n\n"
        "Clauses:\n\n"
        f"{clauses_text}"
    )


CLAUSE_CLASSIFICATION_OUTPUT_CONTRACT = """For each clause return:

- clause_number
- classification: the primary classification for the clause
- classifications: all applicable classifications for the clause
- clause_text
- explanation
- employee_cohort
- work_arrangement
- other_scope_notes
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
    clauses_text = format_clauses_for_prompt(overtime_clauses)
    family_key = ruleset_prompt_family(ruleset_key)
    return [
        {"role": "system", "content": CLAUSE_CLASSIFICATION_GENERIC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_clause_classification_user_prompt(
                variant_prompt=CLAUSE_CLASSIFICATION_VARIANT_USER_PROMPTS[
                    ruleset_key
                ].format(ruleset_label=config.display_name.lower()),
                subset_shared_instructions=subset_shared_prompt_block(ruleset_key),
                step_family_instructions=CLAUSE_CLASSIFICATION_STEP_FAMILY_INSTRUCTIONS[
                    family_key
                ],
                ruleset_question_block=common_overtime_question_block(ruleset_key),
                clauses_text=clauses_text,
                step_subset_instructions=CLAUSE_CLASSIFICATION_STEP_SUBSET_INSTRUCTIONS[
                    ruleset_key
                ],
            ),
        },
    ]
