"""Prompt content for step 3 overtime interpretation.

Used by:
- `src/script_3_interpret_overtime.py`
"""

import json
from pathlib import Path

from src.prompts.payment_clause_classification import DEFINITIONS, TAG_DEFINITIONS


OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT = f"""You classify Australian modern award clauses for payroll implementation.

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

Categories:
- Ordinary Hours Boundary: defines ordinary hours limits, including ordinary hours per day, week, averaging period, span, spread, roster cycle, or ordinary hours arrangement.
- Overtime Trigger: directly states when hours are overtime or when overtime applies.
- Overtime Consequence: defines overtime rates, payment calculation, time off instead of payment, minimum payment, or what happens after overtime already exists.
- Related Rule: influences interpretation but does not itself create overtime and is not an overtime consequence.
- Not Relevant: does not materially affect overtime creation or overtime consequences.

Important:
- Ordinary Hours Boundary clauses matter because work outside ordinary hours limits may create overtime even if the clause does not use the word overtime.
- Overtime Trigger clauses matter because this step is identifying what causes overtime, not how overtime is paid. This includes generally includes any clause mentioning overitme, that does not specificy the consequences. 
- A clause can be both Overtime Trigger and Overtime Consequence.
- If one part of a clause states when time is overtime, when overtime applies, or when time worked will be paid at overtime rates, include Overtime Trigger in classifications even if other parts of the same clause set rates or payment consequences.
- Do not classify a clause as Overtime Trigger merely because it mentions overtime rates or payment after overtime exists.
- Do not classify a clause as Ordinary Hours Boundary unless it defines a limit, threshold, span, spread, roster condition, or arrangement for ordinary hours.
- Consequence handling is deferred. Still classify consequence clauses accurately so they can be used later.
"""


OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT = """Using the Ordinary Hours & Overtime clauses below, classify every listed clause.

For each clause return:
- clause_number
- classification: the primary classification for the clause
- classifications: all applicable classifications for the clause
- clause_text
- explanation

Clauses:

{clauses_text}

Special Instructions:

When identifying overtime triggers, consider both explicit and implicit triggers.

An explicit trigger is a clause that directly states overtime applies.

An implicit trigger is a clause that defines the limits of ordinary hours. Where a clause defines ordinary hours, work performed outside those ordinary hour limits may create an overtime entitlement, even if the clause itself does not use the word overtime.

This includes clauses that impose maximum ordinary hour limits, maximum ordinary days, maximum ordinary weekly hours, or other boundaries beyond which work can no longer be treated as ordinary hours.

Do not include clauses that are solely rostering, fatigue-management, break, spread-of-hours, minimum engagement or administrative requirements unless the clause expressly provides an overtime consequence.

Examples include:
- Maximum ordinary hours per day.
- Maximum ordinary hours per week.
- Ordinary hour spans.
- Roster cycle limits.
- Agreed ordinary hour arrangements.
- Shiftworker ordinary hour provisions.

Where relying on an implicit trigger, clearly identify both:
1. The ordinary hours rule.
2. Why work outside that rule may result in overtime.
""".strip()


OVERTIME_INTERPRETATION_SYSTEM_PROMPT = """You are an expert payroll award interpretation assistant.

Analyse the provided award clauses carefully and conservatively.

Do not invent rules.

Do not infer beyond the provided clauses unless clearly marked as an assumption.

Use clause references wherever possible.
"""


OVERTIME_INTERPRETATION_SPECIAL_INSTRUCTIONS = """When identifying overtime triggers, consider both explicit and implicit triggers.

An explicit trigger is a clause that directly states overtime applies.

An implicit trigger is a clause that defines the limits of ordinary hours. Where a clause defines ordinary hours, work performed outside those ordinary hour limits may create an overtime entitlement, even if the clause itself does not use the word 'overtime'.

Examples include:
- Maximum ordinary hours per day.
- Maximum ordinary hours per week.
- Ordinary hour spans.
- Roster cycle limits.
- Agreed ordinary hour arrangements.
- Shiftworker ordinary hour provisions.

Where relying on an implicit trigger, clearly identify both:
1. The ordinary hours rule.
2. Why work outside that rule may result in overtime.
"""


def build_overtime_interpretation_user_prompt(
    source_file: str,
    working_paper_input: str,
) -> str:
    return f"""Source classification file: {source_file}

The clauses below have already been identified as relevant to determining when overtime is created.

Your task is to turn them into a payroll implementation working paper. This will be a plain english document to be used by the payroll management time to configure their payroll system. 

As such it should be written clearly, in definitive language to display specific points that answer the question 'What circumstances incraese total overtime hours'

What circumstances increase Total Overtime Hours?

Return JSON only.

For each rule return:
- rule_id: stable snake or kebab style identifier, for example `all-employees_span-outside-hours`
- section_heading
- employee_scope
- clause_references
- rule_markdown: one markdown bullet beginning with `- `
- rule_plain_text
- source_clause_numbers
- source_classifications

Important:
- Every distinct overtime circumstance must be a separate rule object.
- Do not silently merge rules that require different payroll tests.
- Preserve ordinary-hours-boundary rules where work outside the boundary may become overtime.
- Use the same rule wording in `rule_markdown` that you would otherwise have written in the working paper.
- `employee_scope` must be explicit. Use `["full-time", "part-time", "casual"]` where the rule applies generally.
- `source_clause_numbers` must point only to clauses in the supplied working paper.
- `source_classifications` must contain only `Ordinary Hours Boundary` and/or `Overtime Trigger`.

For each overtime rule:

- Write a standalone bullet point. Where there are subpoints, additional bullet points should be used, a new bullet point should be used for each way overtime may be increased. 
- Each bullet must contain only one payroll test, threshold, boundary, span, roster condition, break condition, or other circumstance that can cause hours to become overtime.
- State the employee type affected only when the rule applies to a specific employee segment. Where the clause does not specify an employee type, assuming it is relevant to all employees. 
- If the clause uses general wording such as "employee" and does not limit the rule to a specific cohort, treat it as applying to all employees.
- Clearly describe the work, event, threshold, limit, roster condition, or break condition that causes hours to become overtime.
- Include all conditions, thresholds, limits and requirements needed to implement the rule. Do not simply refer to other clauses, make sure we say what what the clauses say. 
- Include all relevant clause references.
- Write the clause references directly in the markdown bullet, preferably at the end in square brackets such as `[22.1, 22.2(a)]`.
- Where multiple clauses must be read together, combine them into a single rule.
- Do not use the words "trigger" or "boundary" in the final output.
- Split rules where different facts, thresholds, or data fields are required to calculate overtime. Even where this may be from the same clause. 

Do not include:

- Overtime rates.
- Overtime calculations.
- Penalty rates.
- Allowances.
- Explanations of how overtime is paid.
- Clauses that do not affect whether hours become overtime.

Group the output by rule scope:

- Use a "All employees" section for rules that apply across employee types. Where employee cohorts are not specified, assume these rules apply to all employees. 
- Do not place a general rule under `Full time`, `Part-time employees`, or `Casual employees` unless the clause genuinely limits that rule to the narrower cohort.
- Add a specific employee segment section only when that segment has a distinct overtime circumstance, threshold, condition, or clause source.
- Add a dedicated work-arrangement section when several overtime rules arise from the same named arrangement, such as sleepovers, broken shifts, recall, on-call work, remote work, travel, or another specific arrangement.
- In a work-arrangement section, still state the employee type affected in each bullet where the rule is not identical for all employees.
- Do not create empty employee segment sections.
- Do not repeat a general rule under Full Time, Part Time, Casual, Day Workers, or Shift Workers unless the segment-specific version is materially different.
- If a general rule applies to multiple employee types in the same way, write it once and identify the covered employee types in that bullet if needed.

Do not combine multiple overtime circumstances into one bullet.

Each bullet must describe only one circumstance that increases Total Overtime Hours.

Avoid duplicate rules:
- If two bullets have the same threshold, condition, and clause source, combine them.
- If the only difference is employee type, combine the employee types into one bullet.
- Keep separate bullets only where the payroll data or calculation test would be different.

For example, split these into separate bullets:
- More than 40 ordinary hours per week.
- More than 8 ordinary hours in a day.
- Work outside Monday to Friday.
- Work outside the ordinary span of 6.00 am to 6.30 pm.

Use definitive language where supported by the clauses.

Use the phrase "the hours will be overtime", not "the employee will be overtime".

Clauses:

{working_paper_input}

Special Instructions:

{OVERTIME_INTERPRETATION_SPECIAL_INSTRUCTIONS}
""".strip()


def build_expert_comparison_messages(
    *,
    source_path: Path,
    shortlisted_clauses: list[dict],
    run_a_rules_json: list[dict],
    run_b_rules_json: list[dict],
) -> list[dict[str, str]]:
    system_prompt = (
        "You are comparing two structured overtime rule extraction outputs for the same "
        "award. Merge them into one best structured rule set.\n\n"
        "Preserve the business meaning of the rules. Do not drop a rule merely because "
        "it is named differently. Treat the same rule with different wording as a merge "
        "candidate. If one run split a rule and the other combined it, produce the clearest "
        "merged structure.\n\n"
        "When merge candidates differ in employee scope, preserve the widest scope that is "
        "supported by the cited clause text. Do not silently narrow a rule from a broader "
        "scope such as `permanent team members` or `all employees` to a narrower scope such "
        "as `full-time team members` unless the clause text expressly requires that narrower "
        "scope. If one run is broader and the broader wording is supported by the cited "
        "clauses, prefer the broader wording.\n\n"
        "Every input rule from run A and run B must be accounted for. Every shortlisted "
        "source clause must still be represented somewhere in the merged output or the "
        "comparison summary must say why the clause does not produce a standalone rule.\n\n"
        "Return JSON only."
    )
    user_prompt = (
        f"Source classification file: {source_path}\n\n"
        "Shortlisted source clauses from step 3.2:\n```json\n"
        f"{json.dumps(shortlisted_clauses, indent=2, ensure_ascii=False)}\n```\n\n"
        "Run A structured rules:\n```json\n"
        f"{json.dumps(run_a_rules_json, indent=2, ensure_ascii=False)}\n```\n\n"
        "Run B structured rules:\n```json\n"
        f"{json.dumps(run_b_rules_json, indent=2, ensure_ascii=False)}\n```\n\n"
        "Return a merged ruleset with:\n"
        "- comparison_summary_markdown: short markdown summary of overlaps, one-sided rules, "
        "and unresolved judgement calls\n"
        "- accounted_run_a_rule_ids: every run A rule_id that was considered\n"
        "- accounted_run_b_rule_ids: every run B rule_id that was considered\n"
        "- merged_rules: the final structured rules to use\n"
        "- merge_explanations: mapping of merged rules back to the run A and run B rule_ids"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
