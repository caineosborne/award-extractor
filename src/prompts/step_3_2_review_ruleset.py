"""Prompt content for step 3.2 overtime ruleset review.

Used by:
- `src/step_3_2_review_ruleset/`
- `src/step_3_1_generate_ruleset/`
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.common.overtime_rulesets import (
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.prompts.step_3_2_prompt_config import step_3_2_prompt_subset_config
from src.prompts.overtime_common_prompt_blocks import (
    GENERIC_PAYROLL_CONFIGURATION_PROMPT,
    common_overtime_question_block,
)
from src.prompts.step_2_2_classify_overtime_clauses import (
    build_clause_classification_messages,
)
from src.prompts.step_3_1_generate_ruleset import (
    build_interpretation_messages as build_ruleset_interpretation_messages,
)
from src.common.overtime_clause_classification import (
    clause_source_text as clause_text,
    select_overtime_creation_clauses,
    select_ruleset_related_clauses,
    validate_overtime_clause_classifications,
)
from src.common.overtime_rules import (
    OvertimeRule,
    make_json_serializable,
    rule_to_dict,
)


CLAUSE_REFERENCE_PATTERN = re.compile(r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b", re.IGNORECASE)


def build_step_3_2_creator_prompt_context(
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
    ruleset_key: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Rebuild the core step-3 prompt context used by the creator model."""
    selected_ruleset_key = ruleset_key or str(
        overtime_clause_classification.get("ruleset_key") or OVERTIME_CREATION_RULESET
    )
    overtime_clauses = select_ruleset_related_clauses(
        payment_classification,
        selected_ruleset_key,
    )
    clause_classifications = validate_overtime_clause_classifications(
        overtime_clause_classification,
        overtime_clauses,
        selected_ruleset_key,
    )
    generation_ready_clauses = select_overtime_creation_clauses(
        clause_classifications,
        selected_ruleset_key,
    )

    return {
        "clause_classification_messages": build_clause_classification_messages(
            overtime_clauses,
            selected_ruleset_key,
        ),
        "interpretation_messages": build_ruleset_interpretation_messages(
            selected_ruleset_key,
            str(classification_path),
            generation_ready_clauses,
        ),
    }


def build_reviewer_shortlisted_clause_summary_markdown(
    payment_classification: Mapping[str, Any],
    overtime_clause_classification: Mapping[str, Any],
    ruleset_key: str | None = None,
) -> str:
    """Summarize only the generation-ready shortlisted clauses for the evaluator."""
    selected_ruleset_key = ruleset_key or str(
        overtime_clause_classification.get("ruleset_key") or OVERTIME_CREATION_RULESET
    )
    config = step_3_2_prompt_subset_config(selected_ruleset_key)
    overtime_clauses = select_ruleset_related_clauses(
        payment_classification,
        selected_ruleset_key,
    )
    clause_classifications = validate_overtime_clause_classifications(
        overtime_clause_classification,
        overtime_clauses,
        selected_ruleset_key,
    )
    generation_ready_clauses = select_overtime_creation_clauses(
        clause_classifications,
        selected_ruleset_key,
    )

    sections = [
        "# Reviewer-oriented shortlisted clause summary",
        "",
        (
            "These are the subset clauses the creator was expected to turn into "
            f"{config.display_name.lower()} rules."
        ),
    ]

    if not generation_ready_clauses:
        sections.extend(["", "No generation-ready shortlisted clauses were identified."])
        return "\n".join(sections).strip()

    for clause in generation_ready_clauses:
        sections.extend(
            [
                "",
                f"## Clause {clause.clause_number}",
                "",
                f"- Primary classification: {clause.classification}",
                f"- All classifications: {', '.join(clause.classifications)}",
                f"- Employee cohort: {clause.employee_cohort}",
                f"- Work arrangement: {clause.work_arrangement}",
                f"- Other scope notes: {clause.other_scope_notes or '(none)'}",
                f"- Explanation: {clause.explanation}",
            ]
        )

    return "\n".join(sections).strip()


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
    evaluator_feedback_data: Mapping[str, Any] | None = None,
    original_rules_artifact: Mapping[str, Any] | None = None,
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

    referenced_clause_numbers: list[str] = []

    if evaluator_feedback_data:
        referenced_clause_numbers = clause_references_from_structured_review(
            evaluator_feedback_data=evaluator_feedback_data,
            original_rules_artifact=original_rules_artifact,
        )

    if not referenced_clause_numbers:
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
        step_2_1_clause = classified_clauses.get(clause_number)
        step_2_2_clause = overtime_clause_by_number.get(clause_number)

        if not isinstance(step_2_1_clause, Mapping) and not isinstance(step_2_2_clause, Mapping):
            continue

        sections.extend(["", f"## Clause {clause_number}"])

        if isinstance(step_2_1_clause, Mapping):
            raw_tags = step_2_1_clause.get("tags", [])
            if isinstance(raw_tags, list):
                tags_text = ", ".join(str(tag) for tag in raw_tags)
            else:
                tags_text = str(raw_tags)

            sections.extend(
                [
                    "",
                    "Step 2.1 payment classification:",
                    f"- Tags: {tags_text}",
                    f"- Source text: {clause_text(step_2_1_clause)}",
                ]
            )

        if isinstance(step_2_2_clause, Mapping):
            raw_classifications = step_2_2_clause.get("classifications", [])
            if isinstance(raw_classifications, list):
                classifications_text = ", ".join(
                    str(classification) for classification in raw_classifications
                )
            else:
                classifications_text = str(raw_classifications)

            sections.extend(
                [
                    "",
                    "Step 2.2 subset clause classification:",
                    f"- Primary classification: {step_2_2_clause.get('classification', '')}",
                    f"- All classifications: {classifications_text}",
                    f"- Explanation: {step_2_2_clause.get('explanation', '')}",
                    f"- Clause text: {step_2_2_clause.get('clause_text', '')}",
                ]
            )

    if len(sections) == 1:
        sections.extend(["", "No clause excerpts were selected."])

    return "\n".join(sections).strip()


def clause_references_from_structured_review(
    *,
    evaluator_feedback_data: Mapping[str, Any],
    original_rules_artifact: Mapping[str, Any] | None = None,
) -> list[str]:
    """Extract clause references from the structured evaluator review first."""
    referenced_clause_numbers: list[str] = []
    original_rule_map: dict[str, Mapping[str, Any]] = {}

    if original_rules_artifact:
        raw_original_rules = original_rules_artifact.get("rules", [])
        if isinstance(raw_original_rules, list):
            for raw_rule in raw_original_rules:
                if isinstance(raw_rule, OvertimeRule):
                    original_rule_map[raw_rule.rule_id] = rule_to_dict(raw_rule)
                elif isinstance(raw_rule, Mapping):
                    rule_id = str(raw_rule.get("rule_id") or "").strip()
                    if rule_id:
                        original_rule_map[rule_id] = raw_rule

    raw_rule_reviews = evaluator_feedback_data.get("rule_reviews", [])
    if isinstance(raw_rule_reviews, list):
        for raw_review in raw_rule_reviews:
            if not isinstance(raw_review, Mapping):
                continue

            rationale = str(raw_review.get("rationale") or "").strip()
            referenced_clause_numbers.extend(extract_clause_references(rationale))

            recommendation = str(raw_review.get("recommendation") or "").strip().lower()
            if recommendation == "keep":
                continue

            rule_id = str(raw_review.get("rule_id") or "").strip()
            source_rule = original_rule_map.get(rule_id)
            if isinstance(source_rule, Mapping):
                raw_clause_numbers = source_rule.get("source_clause_numbers", [])
                if isinstance(raw_clause_numbers, list):
                    referenced_clause_numbers.extend(
                        str(clause_number).strip()
                        for clause_number in raw_clause_numbers
                        if str(clause_number).strip()
                    )

    raw_new_rules = evaluator_feedback_data.get("new_rules", [])
    if isinstance(raw_new_rules, list):
        for raw_rule in raw_new_rules:
            if isinstance(raw_rule, OvertimeRule):
                referenced_clause_numbers.extend(raw_rule.source_clause_numbers)
                referenced_clause_numbers.extend(raw_rule.clause_references)
                referenced_clause_numbers.extend(
                    extract_clause_references(
                        raw_rule.rule_markdown,
                        raw_rule.rule_plain_text,
                    )
                )
                continue

            if not isinstance(raw_rule, Mapping):
                continue

            for field_name in ("source_clause_numbers", "clause_references"):
                raw_values = raw_rule.get(field_name, [])
                if isinstance(raw_values, list):
                    referenced_clause_numbers.extend(
                        str(value).strip()
                        for value in raw_values
                        if str(value).strip()
                    )

            referenced_clause_numbers.extend(
                extract_clause_references(
                    str(raw_rule.get("rule_markdown") or ""),
                    str(raw_rule.get("rule_plain_text") or ""),
                )
            )

    return extract_clause_references("\n".join(referenced_clause_numbers))


def build_creator_review_action_pack(
    *,
    original_rules_artifact: Mapping[str, Any] | None,
    evaluator_feedback_data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the authoritative structured action pack for the creator step."""
    serialized_original_rules: list[dict[str, Any]] = []

    if original_rules_artifact:
        raw_original_rules = original_rules_artifact.get("rules", [])
        if isinstance(raw_original_rules, list):
            for raw_rule in raw_original_rules:
                if isinstance(raw_rule, OvertimeRule):
                    serialized_original_rules.append(rule_to_dict(raw_rule))
                elif isinstance(raw_rule, Mapping):
                    serialized_original_rules.append(dict(raw_rule))

    original_rule_map = {
        str(rule.get("rule_id") or "").strip(): rule
        for rule in serialized_original_rules
        if str(rule.get("rule_id") or "").strip()
    }

    original_rule_reviews: list[dict[str, Any]] = []
    raw_rule_reviews = (evaluator_feedback_data or {}).get("rule_reviews", [])
    if isinstance(raw_rule_reviews, list):
        for raw_review in raw_rule_reviews:
            if not isinstance(raw_review, Mapping):
                continue

            rule_id = str(raw_review.get("rule_id") or "").strip()
            if not rule_id:
                continue

            original_rule_reviews.append(
                {
                    "rule_id": rule_id,
                    "recommendation": str(raw_review.get("recommendation") or "").strip(),
                    "rationale": str(raw_review.get("rationale") or "").strip(),
                    "original_rule": original_rule_map.get(rule_id),
                }
            )

    serialized_new_rules: list[dict[str, Any]] = []
    raw_new_rules = (evaluator_feedback_data or {}).get("new_rules", [])
    if isinstance(raw_new_rules, list):
        for raw_rule in raw_new_rules:
            if isinstance(raw_rule, OvertimeRule):
                serialized_new_rules.append(rule_to_dict(raw_rule))
            elif isinstance(raw_rule, Mapping):
                serialized_new_rules.append(dict(raw_rule))

    return {
        "authoritative_review_contract": {
            "original_rule_reviews": original_rule_reviews,
            "evaluator_proposed_new_rules": serialized_new_rules,
        },
        "explanatory_summary_markdown": str(
            (evaluator_feedback_data or {}).get("summary_markdown") or ""
        ).strip(),
    }


def build_step_3_2_evaluator_user_prompt(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    original_rules_artifact: Mapping[str, Any] | None,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    ruleset_key: str,
) -> str:
    """Build the full evaluator prompt covering both step-3 artifacts."""
    config = step_3_2_prompt_subset_config(ruleset_key)
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
    reviewer_shortlisted_clause_summary_markdown = (
        build_reviewer_shortlisted_clause_summary_markdown(
            payment_classification,
            overtime_clause_classification,
            ruleset_key,
        )
    )

    subset_scope_notes = ""
    if config.subset_scope_notes:
        subset_scope_notes = "\n".join(
            f"- {scope_note}" for scope_note in config.subset_scope_notes
        )
    ruleset_question_block = common_overtime_question_block(ruleset_key)

    return f"""Review this {config.display_name.lower()} working document.

Do not rewrite the ruleset. Provide concise reviewer findings only.
You are to act as a payroll subject-matter expert and reviewer, reviewing the work of a junior employee. 
You will demonstrate professional skepticism and diligence in your review, and you will provide clear, actionable feedback to the employee.

Review the draft against the full step 2.1 payment classification JSON, the step 2.2 subset classification JSON, and the canonical step 3.1 rule JSON.
Do not limit the review to clauses already selected in step 2.2 if the wider payment classification suggests relevant support was missed.

Key review question - these are very common clauses which are present in many awards, but not necessarily all. These should be a guide to what to expect but not treated as the abolute standard. 
{config.review_question}

Shared configuration approach:
{GENERIC_PAYROLL_CONFIGURATION_PROMPT}

Reusable ruleset checks:
{ruleset_question_block}

Subset-specific scope notes:
{subset_scope_notes or "- No extra subset-specific scope note was defined."}

Check:
- whether step 2.2 selected the right clauses for this subset and avoided materially out-of-scope clauses;
- whether the step 3.1 ruleset includes only rules supported by the cited clauses and relevant to this subset;
- whether a shortlisted clause with multiple subclauses has been checked subclause by subclause, especially for any numeric daily, weekly, fortnightly, span-of-hours, roster-cycle, or shift-length limit;
- whether any supported rule appears to have been removed, weakened, or left unclear without justification;
- whether the ruleset is easy for a payroll reviewer to check and easy for an implementation team to convert into payroll logic.

Flag duplicate points, unclear employee scope, unclear work-arrangement scope, missing thresholds, missing clause references, and bullets that combine materially different payroll tests.
If you are substantively uncertain whether a plausible clause-supported rule should be excluded, prefer recommending narrower wording, clearer scope, or clearer clause support rather than immediate removal.
At this stage, overlap is generally less harmful than omission.
If a plausible clause-supported issue remains ambiguous or potentially incomplete rather than clearly wrong, include it under a short `## Potentially incomplete areas` section in `summary_markdown`.
Use that section only for unresolved reviewer decision points that may need later human pickup.
Keep that section brief. It is not a second full findings dump.

This will be passed back to the creator for review and feedback. 

Ruleset source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Canonical step 3.1 rule JSON - the rulesets defined by the creator. 

```json
{original_rules_json}
```

Full payment classification source from step 2.1  - This is every clause that is determined to be relevant for payment (which may or may not be relevant to this subset): {classification_path}


```json
{payment_classification_json}
```

Step 2.2 subset clause classification source - this is the classification of clauses relevant to this subset: {overtime_clause_classification_path}

```json
{overtime_clause_classification_json}
```

{reviewer_shortlisted_clause_summary_markdown}
"""


def build_step_3_2_creator_user_prompt(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    relevant_clause_excerpt_markdown: str,
    evaluator_feedback_markdown: str,
    creator_review_action_pack_json: str,
    ruleset_key: str,
    prior_creator_decision_markdown: str | None = None,
) -> str:
    """Build the one-pass creator prompt used to revise the interpretation draft."""
    config = step_3_2_prompt_subset_config(ruleset_key)
    prior_creator_decision_section = ""
    if prior_creator_decision_markdown and prior_creator_decision_markdown.strip():
        prior_creator_decision_section = f"""
Prior creator decision record:

```markdown
{prior_creator_decision_markdown}
```
"""

    subset_scope_notes = ""
    if config.subset_scope_notes:
        subset_scope_notes = "\n".join(
            f"- {scope_note}" for scope_note in config.subset_scope_notes
        )
    ruleset_question_block = common_overtime_question_block(ruleset_key)

    return f""" You have had the work of a colleague subsitted to a evaulator, who has reviewed the work against the source files to ensure the information produced aligns to the source material. 
    Review the evaluator feedback and update the original document where needed, with a focus on accuracy.  

This is a one-pass update. Do not ask for another review cycle.

Use the evaluator review action pack JSON as the authoritative source for evaluator decisions.
Use the evaluator summary markdown as explanation only.
Do not infer any extra add, remove, merge, or split action from evaluator prose unless it is reflected in the structured action pack.

Keep the revised ruleset simple. Include only rules that answer this question:
{config.review_question}

Shared configuration approach:
{GENERIC_PAYROLL_CONFIGURATION_PROMPT}

Reusable ruleset checks:
{ruleset_question_block}

Subset-specific scope notes:
{subset_scope_notes or "- No extra subset-specific scope note was defined."}

Apply accepted feedback about both:
- accuracy: whether the rule is supported by the cited clause text;
- presentation: whether the rule is clearly scoped, non-duplicative, traceable, and easy to implement.

Preserve supported rules unless accepted feedback requires a change.
Make the smallest changes necessary to address accepted feedback.
Do not rewrite unrelated rules.
If the choice is between removing a plausible clause-supported rule or retaining it with narrower wording or clearer scope, prefer retaining and clarifying it.
At this stage, overlap is generally less harmful than omission.

For original rules:
- use `keep` when the final rule remains substantively the same;
- use `modify` when any substantive field changes, including rule text, clause references, scope, heading, threshold, or arrangement logic;
- use `remove` only when the evaluator explicitly recommended removal and you explain why the rule is unsupported, duplicative, or out of scope.

If a rule is unaffected by accepted feedback, keep it.
If accepted feedback concerns a specific work arrangement, use a dedicated arrangement section when that is clearer than forcing the point into an employee-type section.
Keep one payroll circumstance per bullet where practical.
Keep clause references in the revised markdown bullets, preferably at the end in square brackets.

Original ruleset source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Authoritative evaluator review action pack:

```json
{creator_review_action_pack_json}
```

Explanatory evaluator summary markdown:

```markdown
{evaluator_feedback_markdown}
```

{relevant_clause_excerpt_markdown}
{prior_creator_decision_section}

Return exactly two tagged sections:

<creator_response>
Write a short markdown decision record in concise reviewer language.
Keep it brief.
Prefer one short bullet for accepted feedback and one short bullet for rejected feedback.

</creator_response>
<revised_interpretation>
Write the complete revised ruleset working document in markdown.
</revised_interpretation>
"""


def build_review_evaluator_messages(
    *,
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    original_rules_artifact: Mapping[str, Any] | None = None,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Build the evaluator prompt set for the step-3.2 review."""
    return [
        {"role": "system", "content": build_step_3_2_evaluator_system_prompt(ruleset_key)},
        {
            "role": "user",
            "content": build_step_3_2_evaluator_user_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                original_rules_artifact=original_rules_artifact,
                classification_path=classification_path,
                payment_classification=payment_classification,
                overtime_clause_classification_path=overtime_clause_classification_path,
                overtime_clause_classification=overtime_clause_classification,
                ruleset_key=ruleset_key,
            )
            + "\n\n"
            + build_step_3_2_evaluator_structured_output_instructions(),
        },
    ]


def build_review_creator_messages(
    *,
    interpretation_path: Path | str,
    interpretation_markdown: str,
    classification_path: Path | str,
    payment_classification: Mapping[str, Any],
    overtime_clause_classification_path: Path | str,
    overtime_clause_classification: Mapping[str, Any],
    evaluator_feedback_markdown: str,
    evaluator_feedback_data: Mapping[str, Any] | None = None,
    original_rules_artifact: Mapping[str, Any] | None = None,
    prior_creator_decision_markdown: str | None = None,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Build the creator prompt set used to revise the interpretation."""
    relevant_clause_excerpt_markdown = build_relevant_clause_excerpt_markdown(
        interpretation_markdown=interpretation_markdown,
        payment_classification=payment_classification,
        overtime_clause_classification=overtime_clause_classification,
        evaluator_feedback_markdown=evaluator_feedback_markdown,
        evaluator_feedback_data=evaluator_feedback_data,
        original_rules_artifact=original_rules_artifact,
        prior_creator_decision_markdown=prior_creator_decision_markdown,
    )
    creator_review_action_pack = build_creator_review_action_pack(
        original_rules_artifact=original_rules_artifact,
        evaluator_feedback_data=evaluator_feedback_data,
    )
    creator_prompt_context = build_step_3_2_creator_prompt_context(
        classification_path,
        payment_classification,
        overtime_clause_classification,
        ruleset_key,
    )

    return [
        creator_prompt_context["interpretation_messages"][0],
        {
            "role": "user",
            "content": build_step_3_2_creator_user_prompt(
                interpretation_path=interpretation_path,
                interpretation_markdown=interpretation_markdown,
                relevant_clause_excerpt_markdown=relevant_clause_excerpt_markdown,
                evaluator_feedback_markdown=evaluator_feedback_markdown,
                creator_review_action_pack_json=json.dumps(
                    creator_review_action_pack,
                    indent=2,
                    ensure_ascii=False,
                ),
                ruleset_key=ruleset_key,
                prior_creator_decision_markdown=prior_creator_decision_markdown,
            )
            + "\n\nOriginal step-3 rules JSON:\n```json\n"
            + json.dumps(
                {
                    **(dict(original_rules_artifact) if original_rules_artifact else {}),
                    "rules": [
                        rule_to_dict(rule) if isinstance(rule, OvertimeRule) else rule
                        for rule in (
                            list((original_rules_artifact or {}).get("rules", []))
                        )
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n"
            + "\n\nEvaluator structured review JSON:\n```json\n"
            + json.dumps(
                make_json_serializable(dict(evaluator_feedback_data or {})),
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n"
            + "\n\n"
            + build_step_3_2_creator_structured_output_instructions(),
        },
    ]


def build_step_3_2_pass_fail_evaluator_user_prompt(
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


def build_creator_repair_messages(
    original_messages: list[Mapping[str, str]],
    *,
    validation_error: str,
    prior_response_text: str,
) -> list[dict[str, str]]:
    """Ask the creator model to correct an invalid structured review response."""
    repair_instruction = (
        "Your previous structured JSON response failed validation.\n\n"
        f"Validation error:\n- {validation_error}\n\n"
        "Correct the JSON and return JSON only.\n"
        "Do not omit any original rule.\n"
        "Do not remove a rule unless both evaluator and creator explicitly support removal.\n"
        "If you marked a rule as modify but do not need to change any fields, use decision keep.\n"
        "If you mark a rule as modify, include an updated_rule object or change the decision to keep.\n"
        "Do not invent creator-only new rules.\n"
        "Treat the evaluator structured review JSON new_rules array as the only authoritative source of evaluator-proposed new rule_ids.\n"
        "Do not include any new_rule_reviews entry unless its rule_id appears in that evaluator structured review JSON new_rules array.\n"
        "Every evaluator-proposed new rule must appear in new_rule_reviews with decision accept, modify, or reject.\n"
        "If you use decision modify for an evaluator-proposed new rule, include updated_rule.\n\n"
        "Previous response:\n"
        f"```json\n{prior_response_text}\n```"
    )

    repaired_messages = [dict(message) for message in original_messages]
    repaired_messages.append({"role": "user", "content": repair_instruction})
    return repaired_messages


def build_evaluator_repair_messages(
    original_messages: list[Mapping[str, str]],
    *,
    validation_error: str,
    prior_response_text: str,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> list[dict[str, str]]:
    """Ask the evaluator model to correct an invalid structured review response."""
    del ruleset_key
    repair_instruction = (
        "Your previous structured JSON response failed validation.\n\n"
        f"Validation error:\n- {validation_error}\n\n"
        "Correct the JSON and return JSON only.\n"
        "You must keep one rule_reviews item for every original rule_id.\n"
        "Do not silently drop any original rule.\n"
        "If you recommend removal, the rationale must clearly support that removal.\n"
        "Only use new_rules for clearly supported missing rules for the selected ruleset.\n\n"
        "Previous response:\n"
        f"```json\n{prior_response_text}\n```"
    )

    repaired_messages = [dict(message) for message in original_messages]
    repaired_messages.append({"role": "user", "content": repair_instruction})
    return repaired_messages


def build_step_3_2_evaluator_structured_output_instructions() -> str:
    return (
        "Return JSON only with these top-level fields:\n"
        "- summary_markdown\n"
        "- rule_reviews\n"
        "- new_rules\n\n"
        "In summary_markdown, keep the review concise.\n"
        "If needed, include a short `## Potentially incomplete areas` section for unresolved ambiguity or plausible clause-supported gaps that may need later human pickup.\n"
        "Do not use that section as a second full findings dump.\n\n"
        "For every original rule_id, include one rule_reviews item with:\n"
        "- rule_id\n"
        "- recommendation: keep, modify, or remove\n"
        "- rationale\n\n"
        "Only recommend remove when the rule should not exist in downstream payroll logic.\n"
        "If you think two existing rules should be merged, express that through the relevant "
        "rule_reviews recommendations and rationales for those original rule_ids.\n"
        "Use new_rules only when a clearly supported rule for the selected ruleset is missing from the current draft.\n"
        "Every new_rules item must be a complete structured rule object with a unique rule_id.\n"
        "Do not silently replace an original rule with a new rule. Keep rule_reviews focused on the original rule_ids."
    )


def build_step_3_2_creator_structured_output_instructions() -> str:
    return (
        "Return JSON only with these top-level fields:\n"
        "- decision_record_markdown\n"
        "- rule_updates\n"
        "- new_rule_reviews\n\n"
        "You must provide one rule_updates item for every original rule_id.\n"
        "Each rule_updates item must contain:\n"
        "- rule_id\n"
        "- decision: keep, modify, or remove\n"
        "- reason\n"
        "- updated_rule when decision is modify, otherwise updated_rule must be null\n\n"
        "Keep `reason` short and specific. One sentence is usually enough.\n"
        "Do not omit any original rule. Do not remove a rule unless the evaluator explicitly recommended remove.\n\n"
        "You must also provide one new_rule_reviews item for every evaluator-proposed new rule.\n"
        "Each new_rule_reviews item must contain:\n"
        "- rule_id\n"
        "- decision: accept, modify, or reject\n"
        "- reason\n"
        "- updated_rule when decision is modify, otherwise updated_rule must be null\n\n"
        "Keep `decision_record_markdown` brief.\n"
        "The evaluator structured review JSON is the authoritative source for evaluator-proposed new rule_ids.\n"
        "The evaluator structured review JSON is also the authoritative source for add, remove, keep, and modify decisions on original rules.\n"
        "Only include new_rule_reviews for rule_ids that appear in the evaluator structured review JSON new_rules array.\n"
        "Do not invent standalone new rules in the creator response. The creator may only accept, modify, or reject evaluator-proposed new_rules.\n"
        "If the evaluator rationale suggests merging or splitting rules, implement that only through valid rule_updates and evaluator-proposed new_rules from the structured JSON contract.\n"
        "If you can address the issue by editing an existing rule only, prefer modifying an existing rule."
    )


def build_step_3_2_agentic_creator_instructions(
    max_feedback_cycles: int,
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> str:
    """Return the standing instructions for the agentic step-3.2 creator."""
    config = step_3_2_prompt_subset_config(ruleset_key)
    return f"""You are the creator responsible for finalising an Australian modern award {config.display_name.lower()}.

You are reviewing an existing step 3.1 first draft. Keep the final ruleset simple and include only rules that answer this question:
{config.review_question}

You have a tool named request_evaluator_feedback. Use it to ask the evaluator for review feedback on your current draft. You may use it up to {max_feedback_cycles} times. The first evaluator call is a substantive review. Later evaluator calls are lightweight pass/fail gates that return JSON only.

When you call request_evaluator_feedback after the first cycle, include a short creator decision record in creator_question_or_focus that explains what you changed and what feedback you believe remains unresolved.

Apply accepted feedback about both:
- accuracy: whether the rule is supported by the relevant clause excerpts and source clause text; and
- presentation: whether the rule is clearly scoped, non-duplicative, traceable, and easy to implement.

Preserve existing supported rules unless accepted feedback requires changing or removing them.
Do not remove a rule unless you explicitly state why it is unsupported, duplicative, or out of scope.
If a rule is unaffected by the accepted feedback, keep it in the revised ruleset.
If the choice is between removing a plausible supported rule or keeping it with narrower wording, clearer scope, or clearer evidence, prefer keeping it.
Do not over-merge or over-prune just to reduce repetition. Later aggregation may consolidate overlapping outputs.

Later cycles are confirmation cycles, not fresh rewrites.
After the first evaluator review, make the smallest changes necessary to resolve accepted feedback.
Do not restructure or remove unrelated rules during later cycles.

If you remain substantively uncertain whether a rule should be included or removed from this ruleset, do not treat the draft as ready to finalise. Record the uncertainty clearly so the evaluator can return needs_revision.

When you are finished, return structured final output with:
- conversation_markdown: a concise markdown audit record of the creator/evaluator conversation and your acceptance decisions;
- revised_interpretation_markdown: the complete final revised ruleset working document.
"""


def build_step_3_2_evaluator_system_prompt(
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> str:
    """Return the system prompt for the one-pass interpretation evaluator."""
    config = step_3_2_prompt_subset_config(ruleset_key)
    return f"""You are a supervisor reviewing an Australian modern award {config.display_name.lower()}.

Your job is to provide useful feedback to the creator. Do not rewrite the document.
Ask questions and identify concise issues that would help the creator decide whether an update is needed.

Keep the review simple and focused on this question:

{config.review_question}

Focus on:
- clauses in the full payment classification JSON that may answer the key question but were missed by the step 2.2 clause classification;
- clauses in the step 2.2 classification that do not actually answer the key question for this ruleset;
- final ruleset bullets that are unsupported, missing, too broad, or materially out of scope for this ruleset;
- valid rules in the current draft that appear to have been removed, weakened, or omitted without support;
- employee group, threshold, roster condition, span, spread, or clause-reference errors.
- presentation issues that make the ruleset harder to review or implement, including duplicate bullets, unclear grouping, unclear employee scope, combined rules that should be split, split rules that should be combined, or missing clause references.

If a rule is plausibly supported but imperfectly scoped, prefer asking for clarification, narrowing, or restructuring rather than recommending outright removal.
At this stage, overlap is generally less harmful than omission.

Return markdown only with this structure:

# Ruleset supervisor feedback

## Overall view

## Clause classification issues

## Interpretation issues

## Presentation issues

## Traceability notes
"""
