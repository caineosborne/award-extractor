"""Prompt content for reusable overtime rulesets.

Used by:
- `src/step_2_2_classify_overtime_clauses/`
- `src/step_3_1_generate_ruleset/`
"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    overtime_ruleset_config,
)
from src.prompts.overtime_prompt_shared import (
    SHARED_OVERTIME_CATEGORIES,
    SHARED_PRIMARY_CLASSIFICATION_RULES,
)
from src.prompts.payment_clause_classification import DEFINITIONS, TAG_DEFINITIONS


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


INTERPRETATION_SYSTEM_PROMPT = """You are an expert payroll award interpretation assistant.

Analyse the provided award clauses carefully and conservatively.

Do not invent rules.

Do not infer beyond the provided clauses unless clearly marked as an assumption.

Use clause references wherever possible.
"""


INTERPRETATION_VARIANT_SYSTEM_PROMPTS = {
    OVERTIME_CREATION_RULESET: INTERPRETATION_SYSTEM_PROMPT,
    OVERTIME_CONSEQUENCE_RULESET: """You are an expert payroll award interpretation assistant.

Analyse the provided award clauses carefully and conservatively.

Do not invent rules.

Do not infer beyond the provided clauses unless clearly marked as an assumption.

Use clause references wherever possible.

For overtime consequence, the most important implementation outcome is the actual overtime consequence applied after overtime already exists, especially overtime pay multipliers and minimum payments.

Treat employee-cohort coverage as critical:
- Make sure the output clearly states the overtime multiplier or other direct consequence for each employee cohort supported by the clauses.
- Prioritise full-time and part-time employee multipliers where the award states them.
- Also capture casual employee overtime multipliers or rate rules where the clauses state them.
- Do not leave a cohort's multiplier unstated if the supplied clauses provide it.
- If different cohorts have different overtime multiplier rules, keep them separate and explicit.
""",
}


INTERPRETATION_VARIANT_USER_PROMPTS = {
    OVERTIME_CREATION_RULESET: """Source classification file: {source_file}

The clauses below have already been identified as relevant to determining when overtime is created.

Your task is to turn them into a payroll implementation working paper. This will be a plain english document to be used by the payroll management team to configure their payroll system.

As such it should be written clearly, in definitive language to display specific points that answer the question 'What circumstances increase total overtime hours'

What circumstances increase Total Overtime Hours?

Return JSON only.

For each rule return:
- rule_id: stable snake or kebab style identifier
- section_heading
- employee_scope
- employee_cohort
- work_arrangement
- other_scope_notes
- clause_references
- rule_markdown: one markdown bullet beginning with `- `
- rule_plain_text
- source_clause_numbers
- source_classifications

Important:
- Every distinct overtime circumstance must be a separate rule object.
- Do not silently merge rules that require different payroll tests.
- Preserve ordinary-hours-boundary rules where work outside the boundary may become overtime.
- source_classifications must contain only `Ordinary Hours Boundary` and/or `Overtime Trigger`.
- Use the upstream scope tags as the starting point for scope. Do not narrow or broaden scope unless the cited clause text clearly requires it.
- Each rule must be readable in isolation by a payroll reviewer. State the operative threshold, limit, or condition in the rule text itself.
- Do not rely on a clause reference as a substitute for the rule content. If a clause says 11.5 ordinary hours is the daily maximum, say that 11.5-hour limit in the rule.
- Include all conditions, thresholds, limits, and requirements needed to implement the rule. Spell out the operational rule, then include clause references as evidence.
- Keep clause references in the markdown bullet, preferably at the end in square brackets such as `[15.1(c)(ii), 15.2(b)]`.
- Each bullet must contain only one payroll test, threshold, boundary, span, roster condition, break condition, or other circumstance that can cause hours to become overtime.
- Consider both explicit and implicit triggers. An implicit trigger includes an ordinary-hours boundary where work outside that boundary may become overtime.
- If the clause uses general wording such as "employee" and does not limit the rule to a narrower cohort, treat it as a general rule.
- Do not place a general rule under `Full time`, `Part-time employees`, or `Casual employees` unless the clause genuinely limits that rule to the narrower cohort.
- Add a specific employee segment section only when that segment has a distinct overtime circumstance, threshold, condition, or clause source.
- Add a dedicated work-arrangement section when several overtime rules arise from the same named arrangement.
- In a work-arrangement section, still state the employee type affected when the rule is not identical for all employees.
- Do not repeat a general rule under narrower headings unless the segment-specific version is materially different.
- Do not include overtime rates, overtime calculations, penalty rates, allowances, or clauses that do not affect whether hours become overtime.
- Avoid duplicate rules. If two bullets have the same threshold, condition, and clause source, combine them. Keep separate bullets where the payroll test is materially different.

Clauses:

{working_paper_input}
""".strip(),
    OVERTIME_CONSEQUENCE_RULESET: """Source classification file: {source_file}

The clauses below have already been identified as relevant to determining the consequences once overtime already exists.

Your task is to turn them into a payroll implementation working paper. This will be a plain english document to be used by the payroll management team to configure their payroll system.

As such it should be written clearly, in definitive language to display specific points that answer the question 'What overtime consequence applies once hours are already overtime?'

Return JSON only.

For each rule return:
- rule_id: stable snake or kebab style identifier
- section_heading
- employee_scope
- employee_cohort
- work_arrangement
- other_scope_notes
- clause_references
- rule_markdown: one markdown bullet beginning with `- `
- rule_plain_text
- source_clause_numbers
- source_classifications

Important:
- Every distinct overtime consequence must be a separate rule object.
- Split rules where different pay outcomes, minimum payments, multipliers, TOIL choices, or rest consequences require different payroll handling.
- source_classifications must contain `Overtime Consequence` and may also include boundary or trigger labels when the source clause contains both.
- Do not restate what causes overtime unless it is necessary to understand the consequence.
- If a clause is mixed, extract only the consequence component that answers what payment, rate, minimum, allowance, TOIL outcome, or rest entitlement applies after overtime already exists.
- Prune trigger-only or boundary-only content from the drafted rule unless that context is strictly necessary to identify when the consequence applies.
- Do not produce a standalone rule whose main purpose is to say when hours become overtime.
- If a shortlisted clause does not yield a standalone consequence rule after pruning, omit it from the rules and let the comparison step explain why.
- Do not include penalty rates or allowances unless the clause expressly says they form part of the overtime consequence.
- Prioritise overtime pay multipliers and other direct rate outcomes for each employee cohort. If the clauses state different overtime multiplier outcomes for full-time, part-time, or casual employees, include those cohort-specific rules explicitly.
- Do not assume that a full-time or part-time multiplier rule automatically covers casual employees. State the casual overtime rate rule separately when the clauses do so.

Clauses:

{working_paper_input}
""".strip(),
}


def build_clause_classification_messages(
    ruleset_key: str,
    clauses_text: str,
) -> list[dict[str, str]]:
    config = overtime_ruleset_config(ruleset_key)
    return [
        {"role": "system", "content": CLAUSE_CLASSIFICATION_SHARED_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": CLAUSE_CLASSIFICATION_USER_PROMPT_TEMPLATE.format(
                ruleset_label=config.display_name.lower(),
                clauses_text=clauses_text,
                variant_instructions=CLAUSE_CLASSIFICATION_VARIANT_INSTRUCTIONS[ruleset_key],
            ),
        },
    ]


def build_interpretation_messages(
    ruleset_key: str,
    source_file: str,
    working_paper_input: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": INTERPRETATION_VARIANT_SYSTEM_PROMPTS[ruleset_key],
        },
        {
            "role": "user",
            "content": INTERPRETATION_VARIANT_USER_PROMPTS[ruleset_key].format(
                source_file=source_file,
                working_paper_input=working_paper_input,
            ),
        },
    ]


def build_expert_comparison_messages(
    *,
    ruleset_key: str,
    source_path: Path,
    shortlisted_clauses: list[dict],
    run_a_rules_json: list[dict],
    run_b_rules_json: list[dict],
) -> list[dict[str, str]]:
    config = overtime_ruleset_config(ruleset_key)
    variant_system_instructions = ""
    variant_user_instructions = ""

    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        variant_system_instructions = (
            "\n\nFor overtime consequence, prefer pruning over preserving mixed trigger content. "
            "If a drafted rule mainly states what causes overtime, do not keep it as a standalone "
            "merged rule unless the consequence itself cannot be understood without it."
        )
        variant_user_instructions = (
            "\n\nAdditional merge instructions for overtime consequence:\n"
            "- Keep only rules whose main payroll purpose is the consequence after overtime already exists.\n"
            "- For mixed clauses, keep only the consequence-oriented part of the rule where possible.\n"
            "- Remove standalone trigger/boundary rules that survived expert drafting by mistake.\n"
            "- If a shortlisted clause is mixed and does not produce a clean standalone consequence rule, "
            "do not force it into merged_rules; explain that decision in comparison_summary_markdown or merge_explanations."
        )

    system_prompt = (
        "You are comparing two structured payroll ruleset extraction outputs for the same "
        f"{config.display_name.lower()} ruleset. Merge them into one best structured rule set.\n\n"
        "Preserve the business meaning of the rules. Do not drop a rule merely because "
        "it is named differently. Treat the same rule with different wording as a merge "
        "candidate. If one run split a rule and the other combined it, produce the clearest "
        "merged structure.\n\n"
        "Every input rule from run A and run B must be accounted for. Every shortlisted "
        "source clause must still be represented somewhere in the merged output or the "
        "comparison summary must say why the clause does not produce a standalone rule.\n\n"
        "Return JSON only."
        f"{variant_system_instructions}"
    )
    user_prompt = (
        f"Source classification file: {source_path}\n\n"
        f"Shortlisted source clauses from the {config.display_name.lower()} clause classification step:\n```json\n"
        f"{json.dumps(shortlisted_clauses, indent=2, ensure_ascii=False)}\n```\n\n"
        "Run A structured rules:\n```json\n"
        f"{json.dumps(run_a_rules_json, indent=2, ensure_ascii=False)}\n```\n\n"
        "Run B structured rules:\n```json\n"
        f"{json.dumps(run_b_rules_json, indent=2, ensure_ascii=False)}\n```\n\n"
        "Return a merged ruleset with:\n"
        "- comparison_summary_markdown\n"
        "- accounted_run_a_rule_ids\n"
        "- accounted_run_b_rule_ids\n"
        "- merged_rules\n"
        "- merge_explanations"
        f"{variant_user_instructions}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
