from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.output_paths import path_in_category, write_text_output
from src.common.rule_inventory import (
    RuleInventory,
    RuleRecord,
    employee_scope_from_heading,
    parse_rule_inventory_from_markdown,
)


OVERTIME_RULE_SCHEMA_VERSION = "overtime-rules-v1"
OVERTIME_RULE_REVIEW_SCHEMA_VERSION = "overtime-rule-review-v1"
ALLOWED_RULE_DECISIONS = ("keep", "modify", "remove")
ALLOWED_REVIEW_RECOMMENDATIONS = ("keep", "modify", "remove")
ALLOWED_EMPLOYEE_COHORTS = (
    "full-time",
    "part-time",
    "casual",
    "permanent",
    "all",
)
ALLOWED_WORK_ARRANGEMENTS = (
    "day-worker",
    "shiftworker",
    "all",
)


@dataclass(frozen=True)
class OvertimeRule:
    """One overtime rule carried through step 3 and step 3B."""

    rule_id: str
    section_heading: str
    employee_scope: tuple[str, ...]
    clause_references: tuple[str, ...]
    rule_markdown: str
    rule_plain_text: str
    source_clause_numbers: tuple[str, ...]
    source_classifications: tuple[str, ...]
    employee_cohort: str = "all"
    work_arrangement: str = "all"
    other_scope_notes: str = ""
    review_status: str = "confirmed"


def json_output_path_for_markdown(markdown_path: Path | str) -> Path:
    """Return the JSON sibling for a markdown overtime interpretation artifact."""
    path = Path(markdown_path)
    return path.with_suffix(".json")


def markdown_output_path_for_json(json_path: Path | str) -> Path:
    """Return the markdown sibling for a JSON overtime interpretation artifact."""
    path = Path(json_path)
    return path.with_suffix(".md")


def decision_output_path_for_markdown(markdown_path: Path | str) -> Path:
    """Return the JSON sibling for a creator decision artifact."""
    path = Path(markdown_path)
    return path.with_suffix(".json")


def _normalize_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array.")

    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            raise ValueError(f"{field_name} contains an empty value.")
        normalized.append(text)

    return tuple(normalized)


def employee_scope_from_employee_cohort(employee_cohort: str) -> tuple[str, ...]:
    """Convert a coarse employee cohort label into concrete employee scope tags."""
    normalized_cohort = employee_cohort.strip().lower()

    if normalized_cohort == "full-time":
        return ("full-time",)
    if normalized_cohort == "part-time":
        return ("part-time",)
    if normalized_cohort == "casual":
        return ("casual",)
    if normalized_cohort == "permanent":
        return ("full-time", "part-time")
    return ("full-time", "part-time", "casual")


def employee_cohort_from_employee_scope(employee_scope: Sequence[str]) -> str:
    """Collapse detailed employee scope tags into the standard cohort label."""
    normalized_scope = tuple(sorted({scope.strip().lower() for scope in employee_scope if scope}))

    if normalized_scope == ("full-time",):
        return "full-time"
    if normalized_scope == ("part-time",):
        return "part-time"
    if normalized_scope == ("casual",):
        return "casual"
    if normalized_scope == ("full-time", "part-time"):
        return "permanent"
    return "all"


def validate_rule_object(raw_rule: Mapping[str, Any], *, index: int) -> OvertimeRule:
    """Validate one overtime rule object and normalize it into a dataclass."""
    rule_id = str(raw_rule.get("rule_id") or "").strip()
    section_heading = str(raw_rule.get("section_heading") or "").strip()
    rule_markdown = str(raw_rule.get("rule_markdown") or "").strip()
    rule_plain_text = str(raw_rule.get("rule_plain_text") or "").strip()

    if not rule_id:
        raise ValueError(f"Rule {index} is missing rule_id.")
    if not section_heading:
        raise ValueError(f"Rule {rule_id} is missing section_heading.")
    if not rule_markdown:
        raise ValueError(f"Rule {rule_id} is missing rule_markdown.")
    if not rule_plain_text:
        raise ValueError(f"Rule {rule_id} is missing rule_plain_text.")

    employee_scope = _normalize_string_list(
        raw_rule.get("employee_scope", []),
        f"employee_scope for {rule_id}",
    )
    employee_cohort = str(
        raw_rule.get("employee_cohort")
        or employee_cohort_from_employee_scope(employee_scope)
    ).strip().lower()
    if employee_cohort not in ALLOWED_EMPLOYEE_COHORTS:
        raise ValueError(
            f"employee_cohort for {rule_id} must be one of: "
            + ", ".join(ALLOWED_EMPLOYEE_COHORTS)
        )
    work_arrangement = str(raw_rule.get("work_arrangement") or "all").strip().lower()
    if work_arrangement not in ALLOWED_WORK_ARRANGEMENTS:
        raise ValueError(
            f"work_arrangement for {rule_id} must be one of: "
            + ", ".join(ALLOWED_WORK_ARRANGEMENTS)
        )
    other_scope_notes = str(raw_rule.get("other_scope_notes") or "").strip()
    clause_references = _normalize_string_list(
        raw_rule.get("clause_references", []),
        f"clause_references for {rule_id}",
    )
    source_clause_numbers = _normalize_string_list(
        raw_rule.get("source_clause_numbers", []),
        f"source_clause_numbers for {rule_id}",
    )
    source_classifications = _normalize_string_list(
        raw_rule.get("source_classifications", []),
        f"source_classifications for {rule_id}",
    )
    review_status = str(raw_rule.get("review_status") or "confirmed").strip()

    return OvertimeRule(
        rule_id=rule_id,
        section_heading=section_heading,
        employee_scope=employee_scope,
        employee_cohort=employee_cohort,
        work_arrangement=work_arrangement,
        other_scope_notes=other_scope_notes,
        clause_references=clause_references,
        rule_markdown=rule_markdown,
        rule_plain_text=rule_plain_text,
        source_clause_numbers=source_clause_numbers,
        source_classifications=source_classifications,
        review_status=review_status,
    )


def rule_to_dict(rule: OvertimeRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "section_heading": rule.section_heading,
        "employee_scope": list(rule.employee_scope),
        "employee_cohort": rule.employee_cohort,
        "work_arrangement": rule.work_arrangement,
        "other_scope_notes": rule.other_scope_notes,
        "clause_references": list(rule.clause_references),
        "rule_markdown": rule.rule_markdown,
        "rule_plain_text": rule.rule_plain_text,
        "source_clause_numbers": list(rule.source_clause_numbers),
        "source_classifications": list(rule.source_classifications),
        "review_status": rule.review_status,
    }


def make_json_serializable(value: Any) -> Any:
    """Convert overtime rule dataclasses and nested structures into JSON-safe values."""
    if isinstance(value, OvertimeRule):
        return rule_to_dict(value)

    if isinstance(value, Mapping):
        return {
            str(key): make_json_serializable(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_serializable(item) for item in value]

    return value


def validate_rule_list(raw_rules: Sequence[Any]) -> list[OvertimeRule]:
    """Validate a full ordered rule list and enforce unique rule ids."""
    validated_rules: list[OvertimeRule] = []
    seen_rule_ids: set[str] = set()

    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"Rule {index} must be an object.")

        rule = validate_rule_object(raw_rule, index=index)
        if rule.rule_id in seen_rule_ids:
            raise ValueError(f"Duplicate rule_id in rules output: {rule.rule_id}")

        seen_rule_ids.add(rule.rule_id)
        validated_rules.append(rule)

    if not validated_rules:
        raise ValueError("Rules output must contain at least one rule.")

    return validated_rules


def render_rules_markdown(rules: Sequence[OvertimeRule]) -> str:
    """Render structured overtime rules into the markdown format used elsewhere."""
    grouped_rules: dict[str, list[OvertimeRule]] = {}
    ordered_headings: list[str] = []

    for rule in rules:
        if rule.section_heading not in grouped_rules:
            grouped_rules[rule.section_heading] = []
            ordered_headings.append(rule.section_heading)
        grouped_rules[rule.section_heading].append(rule)

    sections: list[str] = []
    for heading in ordered_headings:
        sections.append(f"## {heading}")
        sections.append("")
        for rule in grouped_rules[heading]:
            sections.append(rule.rule_markdown)
        sections.append("")

    return "\n".join(sections).strip() + "\n"


def prepend_validation_warnings(
    rendered_markdown: str,
    validation_warnings: Sequence[str],
) -> str:
    """Prepend a warning block when step-3 validation found non-fatal issues."""
    if not validation_warnings:
        return rendered_markdown

    warning_lines = [
        "# Validation notes",
        "",
        "The following step-3 validation issues were detected. The interpretation was",
        "written anyway so the review can continue, but these points require checking.",
        "",
    ]
    for warning in validation_warnings:
        warning_lines.append(f"- {warning}")

    warning_lines.extend(["", rendered_markdown.lstrip()])
    return "\n".join(warning_lines).rstrip() + "\n"


def clause_coverage_warnings(
    *,
    original_rules: Sequence[OvertimeRule],
    revised_rules: Sequence[OvertimeRule],
    context_label: str,
) -> list[str]:
    """Record clause references that were present before review but absent after review."""
    original_clause_numbers = {
        clause_number
        for rule in original_rules
        for clause_number in rule.source_clause_numbers
    }
    revised_clause_numbers = {
        clause_number
        for rule in revised_rules
        for clause_number in rule.source_clause_numbers
    }
    dropped_clause_numbers = sorted(original_clause_numbers - revised_clause_numbers)

    return [
        f"{context_label} clause {clause_number} was present before review but is not "
        "referenced after review."
        for clause_number in dropped_clause_numbers
    ]


def build_rule_inventory_from_rules(
    rules: Sequence[OvertimeRule],
    *,
    source_path: Path | str,
    inventory_name: str,
    source_stage: str,
    domain: str,
) -> RuleInventory:
    """Build a deterministic rule inventory from structured overtime rules."""
    rule_records: list[RuleRecord] = []

    for index, rule in enumerate(rules, start=1):
        rule_records.append(
            RuleRecord(
                rule_id=rule.rule_id,
                section_heading=rule.section_heading,
                rule_text=rule.rule_markdown,
                clause_references=rule.clause_references,
                employee_scope=rule.employee_scope,
                source_line_start=index,
                source_line_end=index,
            )
        )

    return RuleInventory(
        inventory_name=inventory_name,
        source_path=str(source_path),
        source_stage=source_stage,
        domain=domain,
        rules=tuple(rule_records),
    )


def rules_from_markdown_fallback(
    markdown_text: str,
    *,
    source_path: Path | str,
) -> list[OvertimeRule]:
    """Build a best-effort structured rule list from legacy markdown."""
    inventory = parse_rule_inventory_from_markdown(
        markdown_text,
        source_path=source_path,
        inventory_name="legacy_overtime_rules",
        source_stage="legacy",
        domain="overtime",
    )
    rules: list[OvertimeRule] = []

    for rule in inventory.rules:
        rules.append(
            OvertimeRule(
                rule_id=rule.rule_id,
                section_heading=rule.section_heading,
                employee_scope=rule.employee_scope
                or employee_scope_from_heading(rule.section_heading),
                employee_cohort=employee_cohort_from_employee_scope(
                    rule.employee_scope or employee_scope_from_heading(rule.section_heading)
                ),
                work_arrangement="all",
                other_scope_notes="",
                clause_references=rule.clause_references,
                rule_markdown=rule.rule_text,
                rule_plain_text=rule.rule_text.lstrip("- ").strip(),
                source_clause_numbers=rule.clause_references,
                source_classifications=("Overtime Trigger",),
            )
        )

    return rules


def build_step_3_rules_artifact(
    *,
    source_classification_file: Path | str,
    source_clause_classification_file: Path | str,
    rules: Sequence[OvertimeRule],
    validation_warnings: Sequence[str] = (),
) -> dict[str, Any]:
    rendered_markdown = prepend_validation_warnings(
        render_rules_markdown(rules),
        validation_warnings,
    )
    return {
        "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
        "source_classification_file": str(source_classification_file),
        "source_clause_classification_file": str(source_clause_classification_file),
        "rendered_markdown": rendered_markdown,
        "validation_warnings": list(validation_warnings),
        "rules": [rule_to_dict(rule) for rule in rules],
    }


def load_rules_artifact(
    json_path: Path | str,
    *,
    expected_schema_version: str = OVERTIME_RULE_SCHEMA_VERSION,
) -> dict[str, Any]:
    path = Path(json_path)
    with path.open(encoding="utf-8") as json_file:
        data = json.load(json_file)

    if not isinstance(data, Mapping):
        raise ValueError(f"Overtime rules artifact must be an object: {path}")

    schema_version = data.get("schema_version")
    if schema_version != expected_schema_version:
        raise ValueError(
            f"Unsupported overtime rules schema version {schema_version!r}: {path}"
        )

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError(f"Overtime rules artifact must contain rules array: {path}")

    validated_rules = validate_rule_list(raw_rules)
    rendered_markdown = str(data.get("rendered_markdown") or "").strip()
    if not rendered_markdown:
        raise ValueError(f"Overtime rules artifact missing rendered_markdown: {path}")

    loaded = dict(data)
    loaded["rules"] = validated_rules
    loaded["rendered_markdown"] = rendered_markdown
    return loaded


def write_rules_artifact(
    *,
    json_path: Path | str,
    markdown_path: Path | str,
    artifact: Mapping[str, Any],
) -> None:
    json_text = json.dumps(artifact, indent=2, ensure_ascii=False)
    write_text_output(json_path, json_text)
    write_text_output(markdown_path, str(artifact["rendered_markdown"]))


def validate_review_feedback_artifact(
    feedback_data: Mapping[str, Any],
    original_rules: Sequence[OvertimeRule],
) -> dict[str, Any]:
    """Validate structured evaluator feedback and require one review per original rule."""
    raw_rule_reviews = feedback_data.get("rule_reviews")
    if not isinstance(raw_rule_reviews, list):
        raise ValueError("Structured evaluator feedback must contain rule_reviews.")

    original_rule_ids = {rule.rule_id for rule in original_rules}
    seen_rule_ids: set[str] = set()
    validated_reviews: list[dict[str, Any]] = []

    for raw_review in raw_rule_reviews:
        if not isinstance(raw_review, Mapping):
            raise ValueError("Each evaluator rule review must be an object.")

        rule_id = str(raw_review.get("rule_id") or "").strip()
        recommendation = str(raw_review.get("recommendation") or "").strip().lower()
        rationale = str(raw_review.get("rationale") or "").strip()

        if rule_id not in original_rule_ids:
            raise ValueError(f"Evaluator returned unknown rule_id: {rule_id}")
        if rule_id in seen_rule_ids:
            raise ValueError(f"Evaluator returned duplicate rule_id: {rule_id}")
        if recommendation not in ALLOWED_REVIEW_RECOMMENDATIONS:
            raise ValueError(
                f"Evaluator returned unsupported recommendation for {rule_id}: {recommendation}"
            )
        if not rationale:
            raise ValueError(f"Evaluator rationale is empty for {rule_id}")

        seen_rule_ids.add(rule_id)
        validated_reviews.append(
            {
                "rule_id": rule_id,
                "recommendation": recommendation,
                "rationale": rationale,
            }
        )

    missing_rule_ids = original_rule_ids - seen_rule_ids
    if missing_rule_ids:
        missing_display = ", ".join(sorted(missing_rule_ids))
        raise ValueError(f"Evaluator feedback is missing rule reviews for: {missing_display}")

    summary_markdown = str(feedback_data.get("summary_markdown") or "").strip()
    if not summary_markdown:
        raise ValueError("Structured evaluator feedback must include summary_markdown.")

    raw_new_rules = feedback_data.get("new_rules", [])
    if not isinstance(raw_new_rules, list):
        raise ValueError("Structured evaluator feedback new_rules must be an array.")
    validated_new_rules = validate_rule_list(raw_new_rules) if raw_new_rules else []
    duplicate_new_rule_ids = {
        rule.rule_id for rule in validated_new_rules
    } & original_rule_ids
    if duplicate_new_rule_ids:
        duplicate_display = ", ".join(sorted(duplicate_new_rule_ids))
        raise ValueError(
            "Structured evaluator feedback new_rules duplicate original rule_ids: "
            f"{duplicate_display}"
        )

    return {
        "schema_version": OVERTIME_RULE_REVIEW_SCHEMA_VERSION,
        "summary_markdown": summary_markdown,
        "rule_reviews": validated_reviews,
        "new_rules": validated_new_rules,
    }


def apply_review_decisions(
    *,
    original_rules: Sequence[OvertimeRule],
    evaluator_feedback: Mapping[str, Any],
    creator_decision_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply creator decisions and reject any silent or one-sided removals or additions."""
    raw_rule_updates = creator_decision_data.get("rule_updates")
    if not isinstance(raw_rule_updates, list):
        raise ValueError("Creator review response must contain rule_updates.")

    original_rule_map = {rule.rule_id: rule for rule in original_rules}
    evaluator_review_map = {
        str(review["rule_id"]): str(review["recommendation"])
        for review in evaluator_feedback["rule_reviews"]
    }

    final_rules: list[OvertimeRule] = []
    review_decisions: list[dict[str, Any]] = []
    seen_rule_ids: set[str] = set()

    for raw_update in raw_rule_updates:
        if not isinstance(raw_update, Mapping):
            raise ValueError("Each creator rule update must be an object.")

        rule_id = str(raw_update.get("rule_id") or "").strip()
        decision = str(raw_update.get("decision") or "").strip().lower()
        reason = str(raw_update.get("reason") or "").strip()

        if rule_id not in original_rule_map:
            raise ValueError(f"Creator returned unknown rule_id: {rule_id}")
        if rule_id in seen_rule_ids:
            raise ValueError(f"Creator returned duplicate rule_id: {rule_id}")
        if decision not in ALLOWED_RULE_DECISIONS:
            raise ValueError(f"Unsupported creator decision for {rule_id}: {decision}")
        if not reason:
            raise ValueError(f"Creator decision reason is empty for {rule_id}")

        original_rule = original_rule_map[rule_id]
        evaluator_recommendation = evaluator_review_map.get(rule_id, "keep")

        if decision == "remove":
            if evaluator_recommendation != "remove":
                raise ValueError(
                    f"Rule {rule_id} cannot be removed unless both reviewer and creator "
                    "explicitly recommend removal."
                )
            final_decision = "removed"
        elif decision == "modify":
            updated_rule_data = raw_update.get("updated_rule")
            if isinstance(updated_rule_data, Mapping):
                merged_rule_data = rule_to_dict(original_rule)
                merged_rule_data.update(dict(updated_rule_data))
                merged_rule_data["rule_id"] = rule_id
                updated_rule = validate_rule_object(merged_rule_data, index=1)
                if updated_rule.rule_id != rule_id:
                    raise ValueError(
                        f"Modified rule {rule_id} must preserve its original rule_id."
                    )
                final_rules.append(updated_rule)
            else:
                # Be tolerant of creator outputs that flag a modification but omit the
                # replacement payload. Preserve the original rule rather than failing.
                final_rules.append(original_rule)
            final_decision = "modified"
        else:
            final_rules.append(original_rule)
            final_decision = "kept"

        review_decisions.append(
            {
                "rule_id": rule_id,
                "evaluator_recommendation": evaluator_recommendation,
                "creator_decision": decision,
                "final_decision": final_decision,
                "reason": reason,
            }
        )
        seen_rule_ids.add(rule_id)

    missing_rule_ids = set(original_rule_map) - seen_rule_ids
    if missing_rule_ids:
        missing_display = ", ".join(sorted(missing_rule_ids))
        raise ValueError(
            "Creator review response omitted rules. Every original rule requires an explicit "
            f"decision: {missing_display}"
        )

    raw_evaluator_new_rules = evaluator_feedback.get("new_rules", [])
    if not isinstance(raw_evaluator_new_rules, list):
        raise ValueError("Evaluator feedback new_rules must be an array.")
    evaluator_new_rules: list[OvertimeRule] = []
    for index, raw_rule in enumerate(raw_evaluator_new_rules, start=1):
        if isinstance(raw_rule, OvertimeRule):
            evaluator_new_rules.append(raw_rule)
            continue

        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"Evaluator new rule {index} must be an object.")

        evaluator_new_rules.append(validate_rule_object(raw_rule, index=index))
    evaluator_new_rule_map = {
        rule.rule_id: rule for rule in evaluator_new_rules
    }
    raw_new_rule_reviews = creator_decision_data.get("new_rule_reviews", [])
    if not isinstance(raw_new_rule_reviews, list):
        raise ValueError("Creator review response new_rule_reviews must be an array.")

    seen_new_rule_ids: set[str] = set()
    for raw_review in raw_new_rule_reviews:
        if not isinstance(raw_review, Mapping):
            raise ValueError("Each creator new_rule_reviews item must be an object.")

        rule_id = str(raw_review.get("rule_id") or "").strip()
        decision = str(raw_review.get("decision") or "").strip().lower()
        reason = str(raw_review.get("reason") or "").strip()

        if rule_id not in evaluator_new_rule_map:
            raise ValueError(
                f"Creator returned unknown evaluator-proposed new rule_id: {rule_id}"
            )
        if rule_id in seen_new_rule_ids:
            raise ValueError(
                f"Creator returned duplicate evaluator-proposed new rule_id: {rule_id}"
            )
        if decision not in {"accept", "modify", "reject"}:
            raise ValueError(
                f"Unsupported creator new-rule decision for {rule_id}: {decision}"
            )
        if not reason:
            raise ValueError(f"Creator new-rule decision reason is empty for {rule_id}")

        evaluator_new_rule = evaluator_new_rule_map[rule_id]
        if decision == "accept":
            final_rules.append(evaluator_new_rule)
            final_decision = "accepted"
        elif decision == "modify":
            updated_rule_data = raw_review.get("updated_rule")
            if not isinstance(updated_rule_data, Mapping):
                raise ValueError(
                    f"Creator new-rule decision for {rule_id} must include updated_rule when decision is modify."
                )

            merged_rule_data = rule_to_dict(evaluator_new_rule)
            merged_rule_data.update(dict(updated_rule_data))
            merged_rule_data["rule_id"] = rule_id
            updated_rule = validate_rule_object(merged_rule_data, index=1)
            if updated_rule.rule_id != rule_id:
                raise ValueError(
                    f"Modified evaluator-proposed new rule {rule_id} must preserve its original rule_id."
                )
            final_rules.append(updated_rule)
            final_decision = "modified"
        else:
            final_decision = "rejected"

        review_decisions.append(
            {
                "rule_id": rule_id,
                "evaluator_recommendation": "add",
                "creator_decision": decision,
                "final_decision": final_decision,
                "reason": reason,
            }
        )
        seen_new_rule_ids.add(rule_id)

    missing_new_rule_ids = set(evaluator_new_rule_map) - seen_new_rule_ids
    if missing_new_rule_ids:
        missing_display = ", ".join(sorted(missing_new_rule_ids))
        raise ValueError(
            "Creator review response omitted evaluator-proposed new rules. Every "
            f"proposed new rule requires an explicit decision: {missing_display}"
        )

    duplicate_final_rule_ids: set[str] = set()
    final_rule_ids: set[str] = set()
    for rule in final_rules:
        if rule.rule_id in final_rule_ids:
            duplicate_final_rule_ids.add(rule.rule_id)
        final_rule_ids.add(rule.rule_id)
    if duplicate_final_rule_ids:
        duplicate_display = ", ".join(sorted(duplicate_final_rule_ids))
        raise ValueError(f"Final reviewed rules contain duplicate rule_ids: {duplicate_display}")

    reviewed_rule_status_by_id = {
        decision["rule_id"]: (
            "added_in_review"
            if decision["evaluator_recommendation"] == "add"
            or (
                decision["final_decision"] == "modified"
                and decision["evaluator_recommendation"] == "remove"
            )
            else "confirmed"
        )
        for decision in review_decisions
    }

    if creator_decision_data.get("validation_error"):
        reviewed_rule_status_by_id = {
            **reviewed_rule_status_by_id,
            **{
                rule.rule_id: "preserved_pending_confirmation"
                for rule in final_rules
            },
        }

    normalized_final_rules: list[OvertimeRule] = []
    for rule in final_rules:
        rule_data = rule_to_dict(rule)
        rule_data["review_status"] = reviewed_rule_status_by_id.get(
            rule.rule_id,
            rule.review_status,
        )
        normalized_final_rules.append(validate_rule_object(rule_data, index=1))

    decision_record_markdown = str(
        creator_decision_data.get("decision_record_markdown") or ""
    ).strip()
    if not decision_record_markdown:
        raise ValueError("Creator review response must include decision_record_markdown.")

    rendered_markdown = render_rules_markdown(normalized_final_rules)

    return {
        "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
        "rendered_markdown": rendered_markdown,
        "rules": normalized_final_rules,
        "review_decisions": review_decisions,
        "decision_record_markdown": decision_record_markdown,
    }
