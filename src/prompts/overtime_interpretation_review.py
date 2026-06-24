"""Prompt content for step 3B overtime interpretation review.

Used by:
- `src/script_3b_review_overtime_interpretation.py`
- `src/script_3b_agentic_review_workflow.py`
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.script_3_interpret_overtime import (
    build_classification_messages,
    build_messages as build_overtime_interpretation_messages,
    clause_text,
    filter_overtime_clauses,
    filter_overtime_creation_clauses,
    validate_overtime_clause_classifications,
)
from src.common.overtime_rules import OvertimeRule, rule_to_dict


CLAUSE_REFERENCE_PATTERN = re.compile(r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b", re.IGNORECASE)


def build_script_3_creator_prompt_context(
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """Rebuild the core step-3 prompt context used by the creator model."""
    overtime_clauses = filter_overtime_clauses(payment_classification)
    clause_classifications = validate_overtime_clause_classifications(
        overtime_clause_classification,
        overtime_clauses,
    )
    overtime_creation_clauses = filter_overtime_creation_clauses(clause_classifications)

    return {
        "clause_classification_messages": build_classification_messages(overtime_clauses),
        "interpretation_messages": build_overtime_interpretation_messages(
            str(classification_path),
            overtime_creation_clauses,
        ),
    }


def clause_reference_sort_key(clause_reference: str) -> tuple[int, ...]:
    """Sort clause references numerically by their dotted parts."""
    sort_parts = re.findall(r"\d+", clause_reference)
    if not sort_parts:
        return (10**9,)

    return tuple(int(part) for part in sort_parts)


def extract_clause_references(*texts: str) -> list[str]:
    """Extract and sort distinct clause references from one or more text blocks."""
    clause_references: set[str] = set()

    for text in texts:
        for clause_reference in CLAUSE_REFERENCE_PATTERN.findall(text or ""):
            clause_references.add(clause_reference)

    return sorted(clause_references, key=clause_reference_sort_key)


def interpretation_clause_references(interpretation_markdown: str) -> list[str]:
    """Extract clause references mentioned in an interpretation draft."""
    return extract_clause_references(interpretation_markdown)


def build_relevant_clause_excerpt_markdown(
    interpretation_markdown: str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    prior_creator_decision_markdown: str | None = None,
) -> str:
    """Build a focused clause excerpt pack for the creator revision step."""
    classified_clauses = payment_classification.get("classified_clauses", {})
    if not isinstance(classified_clauses, Mapping):
        classified_clauses = {}

    overtime_clause_entries = overtime_clause_classification.get("clauses", [])
    overtime_clause_by_number: dict[str, Mapping[str, Any]] = {}
    if isinstance(overtime_clause_entries, list):
        for raw_clause in overtime_clause_entries:
            if not isinstance(raw_clause, Mapping):
                continue
            clause_number = str(raw_clause.get("clause_number") or "").strip()
            if clause_number:
                overtime_clause_by_number[clause_number] = raw_clause

    referenced_clause_numbers = extract_clause_references(
        evaluator_feedback_markdown,
        prior_creator_decision_markdown or "",
    )

    if not referenced_clause_numbers:
        referenced_clause_numbers = interpretation_clause_references(interpretation_markdown)

    if not referenced_clause_numbers:
        referenced_clause_numbers = sorted(
            overtime_clause_by_number,
            key=clause_reference_sort_key,
        )

    sections = ["# Relevant clause excerpts"]

    for clause_number in referenced_clause_numbers:
        script_2_clause = classified_clauses.get(clause_number)
        script_3_clause = overtime_clause_by_number.get(clause_number)

        if not isinstance(script_2_clause, Mapping) and not isinstance(script_3_clause, Mapping):
            continue

        sections.extend(["", f"## Clause {clause_number}"])

        if isinstance(script_2_clause, Mapping):
            raw_tags = script_2_clause.get("tags", [])
            if isinstance(raw_tags, list):
                tags_text = ", ".join(str(tag) for tag in raw_tags)
            else:
                tags_text = str(raw_tags)

            sections.extend(
                [
                    "",
                    "Script 2 payment classification:",
                    f"- Tags: {tags_text}",
                    f"- Source text: {clause_text(script_2_clause)}",
                ]
            )

        if isinstance(script_3_clause, Mapping):
            raw_classifications = script_3_clause.get("classifications", [])
            if isinstance(raw_classifications, list):
                classifications_text = ", ".join(
                    str(classification) for classification in raw_classifications
                )
            else:
                classifications_text = str(raw_classifications)

            sections.extend(
                [
                    "",
                    "Script 3 clause classification:",
                    f"- Primary classification: {script_3_clause.get('classification', '')}",
                    f"- All classifications: {classifications_text}",
                    f"- Explanation: {script_3_clause.get('explanation', '')}",
                    f"- Clause text: {script_3_clause.get('clause_text', '')}",
                ]
            )

    if len(sections) == 1:
        sections.extend(["", "No clause excerpts were selected."])

    return "\n".join(sections).strip()


def build_full_evaluator_review_prompt(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    original_rules_artifact: Mapping[str, Any] | None,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
) -> str:
    """Build the full evaluator prompt covering both step-3 artifacts."""
    payment_classification_json = json.dumps(
        payment_classification,
        indent=2,
        ensure_ascii=False,
    )
    serializable_original_rules_artifact: dict[str, Any] = {}
    if original_rules_artifact:
        serializable_original_rules_artifact = dict(original_rules_artifact)
        raw_rules = serializable_original_rules_artifact.get("rules", [])
        if isinstance(raw_rules, list):
            serializable_original_rules_artifact["rules"] = [
                rule_to_dict(rule) if isinstance(rule, OvertimeRule) else rule
                for rule in raw_rules
            ]

    original_rules_json = json.dumps(
        serializable_original_rules_artifact,
        indent=2,
        ensure_ascii=False,
    )
    overtime_clause_classification_json = json.dumps(
        overtime_clause_classification,
        indent=2,
        ensure_ascii=False,
    )
    script_3_creator_prompt_context_json = json.dumps(
        build_script_3_creator_prompt_context(
            classification_path,
            payment_classification,
            overtime_clause_classification,
        ),
        indent=2,
        ensure_ascii=False,
    )

    return f"""Review this overtime interpretation working document.

Do not rewrite the interpretation. Provide supervisor-style questions and concise issue notes only.

Review against the full payment clause identifier JSON from Script 2. Do not limit the review to clauses already tagged Ordinary Hours & Overtime.

Check both Script 3 steps:
1. The intermediate clause classification JSON: did it correctly preserve clauses whose classifications include Ordinary Hours Boundary or Overtime Trigger, and avoid treating consequence-only clauses as overtime-creation sources?
2. The final interpretation markdown: does it include only core overtime-creation rules supported by those clauses?

Key review question:
Will this clause increase overtime entitlement by causing worked time to become overtime?

Also review presentation. The final document should be easy for a payroll reviewer to check and for a payroll implementation team to convert into configuration rules. Identify duplicate points, unclear employee scope, missing thresholds, unclear grouping, missing clause references, or bullets that combine materially different tests.

Check whether the interpretation silently dropped any supported overtime-creation rule from the current draft.
If a rule appears valid and unaffected by the feedback, call out any apparent removal or weakening of that rule.

Interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Canonical Script 3 rule JSON:

```json
{original_rules_json}
```

Full payment classification source from Script 2: {classification_path}

```json
{payment_classification_json}
```

Script 3 intermediate overtime clause classification source: {overtime_clause_classification_path}

```json
{overtime_clause_classification_json}
```

Script 3 creator prompt context reconstructed from the current Step 3 code.
This is included so the evaluator reviews against the same data and instructions that the creator received.

```json
{script_3_creator_prompt_context_json}
```
"""


def build_minimal_creator_revision_prompt(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    relevant_clause_excerpt_markdown: str,
    evaluator_feedback_markdown: str,
    prior_creator_decision_markdown: str | None = None,
) -> str:
    """Build the one-pass creator prompt used to revise the interpretation draft."""
    prior_creator_decision_section = ""
    if prior_creator_decision_markdown and prior_creator_decision_markdown.strip():
        prior_creator_decision_section = f"""
Prior creator decision record:

```markdown
{prior_creator_decision_markdown}
```
"""

    return f"""Review the supervisor feedback and decide whether the interpretation needs updating.

This is a one-pass update. Do not ask for another review cycle.

Keep the revised interpretation simple. Include only clauses that answer this question:
Will this clause increase overtime entitlement by causing worked time to become overtime?

Apply accepted feedback about both:
- accuracy: whether the rule is supported by the cited clause text; and
- presentation: whether the rule is clearly scoped, non-duplicative, traceable, and easy to implement.

Preserve existing supported rules unless the accepted feedback requires changing or removing them.
Do not remove a rule unless you explicitly state why it is unsupported, duplicative, or out of scope.
If a rule is unaffected by the accepted feedback, keep it in the revised interpretation.

Make the smallest changes necessary to address accepted feedback.
Do not rewrite or simplify unrelated parts of the interpretation.

If you remain substantively uncertain whether a clause should stay in or be removed as an overtime-creation rule, record that uncertainty explicitly in the creator response rather than silently finalising the point.

Where accepted feedback concerns a named work arrangement, such as sleepovers, broken shifts, recall, on-call work, remote work, travel, or another specific arrangement, use a dedicated arrangement section if that is clearer than spreading the rules across employee-type sections. In that arrangement section, still state the employee type affected in each bullet where the rule is not identical for all employees.
Keep one overtime circumstance per bullet. Split combined bullets where they contain separate thresholds, spans, roster conditions, or other distinct payroll tests.
Keep clause references in the revised markdown bullets, preferably at the end in square brackets.
If a clause uses general wording such as "employee" and does not limit the rule to a narrower cohort, place that rule under `All employees` or a general work-arrangement section, not under a narrower employee-type heading.

Original interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Supervisor feedback:

```markdown
{evaluator_feedback_markdown}
```

{relevant_clause_excerpt_markdown}
{prior_creator_decision_section}

Return exactly two tagged sections:

<creator_response>
Write a short markdown decision record. Explain which feedback you accepted, which feedback you rejected, and why.

</creator_response>
<revised_interpretation>
Write the complete revised overtime interpretation working document in markdown.
</revised_interpretation>
"""


def build_minimal_pass_fail_evaluator_prompt(
    current_draft_markdown: str,
    evaluator_feedback_markdown: str,
    prior_creator_decision_markdown: str | None = None,
) -> str:
    """Build the lightweight evaluator gate used in later agentic feedback cycles."""
    prior_creator_decision_section = ""
    if prior_creator_decision_markdown and prior_creator_decision_markdown.strip():
        prior_creator_decision_section = f"""
Prior creator decision record:

```markdown
{prior_creator_decision_markdown}
```
"""

    return f"""Check whether the latest draft has addressed the earlier evaluator feedback and remains substantively safe.

Use only the latest draft, the earlier evaluator feedback, and the prior creator decision record if provided.

Return needs_revision if any of the following apply:
- a previously supported rule appears to have been removed or weakened without justification;
- the creator decision record identifies unresolved substantive uncertainty about whether a rule should be included or excluded;
- the latest draft appears materially less complete than the earlier draft in a way that is not justified by the feedback;
- the earlier evaluator feedback is not actually resolved.

Latest draft:

```markdown
{current_draft_markdown}
```

Earlier evaluator feedback:

```markdown
{evaluator_feedback_markdown}
```

{prior_creator_decision_section}

Return JSON only:
{{"status":"pass"|"needs_revision","reason":"..."}}
"""


def evaluator_structured_output_instructions() -> str:
    return (
        "Return JSON only with these top-level fields:\n"
        "- summary_markdown\n"
        "- rule_reviews\n"
        "- new_rules\n\n"
        "For every original rule_id, include one rule_reviews item with:\n"
        "- rule_id\n"
        "- recommendation: keep, modify, or remove\n"
        "- rationale\n\n"
        "Only recommend remove when the rule should not exist in downstream payroll logic.\n"
        "If a missing supported rule should be added, include it in new_rules using the same structured shape as the step-3 rules JSON."
    )


def creator_structured_output_instructions() -> str:
    return (
        "Return JSON only with these top-level fields:\n"
        "- decision_record_markdown\n"
        "- rule_updates\n"
        "- new_rules\n\n"
        "You must provide one rule_updates item for every original rule_id.\n"
        "Each rule_updates item must contain:\n"
        "- rule_id\n"
        "- decision: keep, modify, or remove\n"
        "- reason\n"
        "- updated_rule when decision is modify\n\n"
        "Do not omit any original rule. Do not remove a rule unless the evaluator explicitly recommended remove."
    )


def build_agentic_creator_instructions(max_feedback_cycles: int) -> str:
    """Return the standing instructions for the agentic step-3B creator."""
    return f"""You are the creator responsible for finalising an Australian modern award overtime creation interpretation.

You are reviewing an existing Script 3 first draft. Keep the final interpretation simple and include only clauses that answer this question:
Will this clause increase overtime entitlement by causing worked time to become overtime?

You have a tool named request_evaluator_feedback. Use it to ask the evaluator for review feedback on your current draft. You may use it up to {max_feedback_cycles} times. The first evaluator call is a substantive review. Later evaluator calls are lightweight pass/fail gates that return JSON only.

When you call request_evaluator_feedback after the first cycle, include a short creator decision record in creator_question_or_focus that explains what you changed and what feedback you believe remains unresolved.

Apply accepted feedback about both:
- accuracy: whether the rule is supported by the relevant clause excerpts and source clause text; and
- presentation: whether the rule is clearly scoped, non-duplicative, traceable, and easy to implement.

Preserve existing supported rules unless accepted feedback requires changing or removing them.
Do not remove a rule unless you explicitly state why it is unsupported, duplicative, or out of scope.
If a rule is unaffected by the accepted feedback, keep it in the revised interpretation.

Later cycles are confirmation cycles, not fresh rewrites.
After the first evaluator review, make the smallest changes necessary to resolve accepted feedback.
Do not restructure or remove unrelated rules during later cycles.

If you remain substantively uncertain whether a clause should be included or removed as an overtime-creation rule, do not treat the draft as ready to finalise. Record the uncertainty clearly so the evaluator can return needs_revision.

Do not review rates, calculations, penalties, allowances, payment mechanics, or other consequences except to exclude them from overtime-creation rules.

When you are finished, return structured final output with:
- conversation_markdown: a concise markdown audit record of the creator/evaluator conversation and your acceptance decisions;
- revised_interpretation_markdown: the complete final revised overtime interpretation working document.
"""


def evaluation_system_prompt() -> str:
    """Return the system prompt for the one-pass interpretation evaluator."""
    return """You are a supervisor reviewing an Australian modern award overtime creation interpretation.

Your job is to provide useful feedback to the creator. Do not rewrite the document.
Ask questions and identify concise issues that would help the creator decide whether an update is needed.

Keep the review simple and focused on this question:

Will this clause increase overtime entitlement by causing worked time to become overtime

Focus on:
- clauses in the full payment classification JSON that may answer the key question but were missed by the Script 3 clause classification;
- clauses whose Script 3 classifications include Ordinary Hours Boundary or Overtime Trigger but that do not actually answer the key question;
- final interpretation bullets that are unsupported, missing, too broad, or include consequence-only rules;
- valid overtime-creation rules in the current draft that appear to have been removed, weakened, or omitted without support;
- employee group, threshold, roster condition, span, spread, or clause-reference errors.
- presentation issues that make the interpretation harder to review or implement, including duplicate bullets, unclear grouping, unclear employee scope, combined rules that should be split, split rules that should be combined, missing clause references, or consequence wording that should be removed.

Do not review rates, calculations, penalties, allowances, payment mechanics, or other consequences except to say they should not be included as overtime-creation rules.

Return markdown only with this structure:

# Overtime interpretation supervisor feedback

## Overall view

## Clause classification issues

## Interpretation issues

## Presentation issues

## Traceability notes
"""
