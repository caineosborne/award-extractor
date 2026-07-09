"""Step 5.1 stage 3: validate and write pseudocode outputs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from src.common.output_naming import (
    validation_json_path_for_pseudocode as naming_validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode as naming_validation_markdown_path_for_pseudocode,
)
from src.common.output_paths import write_text_output
from src.common.rule_inventory import RuleInventory, RuleRecord, extract_clause_references

SECTION_HEADING_PATTERN = re.compile(r"^##\s+(?P<heading>.+?)\s*$")
STOPWORDS = {
    "the","and","for","that","with","this","will","where","when","over","than","time",
    "worked","hours","hour","employee","employees","ordinary","overtime","any","all",
    "after","before","into","from","they","them","more","week","day","work",
}


@dataclass(frozen=True)
class ImplementationRule:
    rule_text: str
    clause_references: tuple[str, ...]
    employee_scope: tuple[str, ...]


@dataclass(frozen=True)
class ExcludedCondition:
    condition_text: str
    clause_references: tuple[str, ...]


@dataclass(frozen=True)
class RuleValidationResult:
    rule_id: str
    status: str
    source_rule_text: str
    source_clause_references: tuple[str, ...]
    matched_clause_references: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ValidationIssue:
    issue_type: str
    severity: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    source_path: str
    target_path: str
    overall_status: str
    passed_rule_count: int
    failed_rule_count: int
    unresolved_rule_count: int
    rule_results: tuple[RuleValidationResult, ...]
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validation_json_path_for_pseudocode(pseudocode_path: Path | str) -> Path:
    return naming_validation_json_path_for_pseudocode(pseudocode_path)


def validation_markdown_path_for_pseudocode(pseudocode_path: Path | str) -> Path:
    return naming_validation_markdown_path_for_pseudocode(pseudocode_path)


def split_markdown_sections(markdown_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading = ""
    for line in markdown_text.splitlines():
        heading_match = SECTION_HEADING_PATTERN.match(line)
        if heading_match:
            current_heading = heading_match.group("heading")
            sections[current_heading] = []
            continue
        if current_heading:
            sections[current_heading].append(line)
    return sections


def parse_top_level_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("- "):
            if current_lines:
                bullets.append("\n".join(current_lines).strip())
            current_lines = [line]
            continue
        if current_lines and (line.startswith("  ") or not line.strip()):
            current_lines.append(line)
            continue
        if current_lines:
            bullets.append("\n".join(current_lines).strip())
            current_lines = []
    if current_lines:
        bullets.append("\n".join(current_lines).strip())
    return bullets


def parse_numbered_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped_line = line.strip()
        if re.match(r"^\d+\.\s+", stripped_line):
            items.append(re.sub(r"^\d+\.\s+", "", stripped_line))
    return items


def parse_required_inputs(lines: list[str]) -> list[str]:
    bullets = parse_top_level_bullets(lines)
    parsed_inputs: list[str] = []
    for bullet in bullets:
        value = bullet.removeprefix("- ").strip()
        if value:
            parsed_inputs.append(value)
    if not parsed_inputs:
        stripped_lines = [line.strip() for line in lines if line.strip()]
        if len(stripped_lines) == 1 and stripped_lines[0].lower() == "none":
            return ["None"]
    return parsed_inputs


def implementation_scope_from_text(rule_text: str) -> tuple[str, ...]:
    normalized_text = rule_text.lower()
    scope: list[str] = []
    if "full-time" in normalized_text:
        scope.append("full-time")
    if "part-time" in normalized_text:
        scope.append("part-time")
    if "casual" in normalized_text:
        scope.append("casual")
    return tuple(scope)


def parse_implementation_rules(pseudocode_markdown: str) -> tuple[ImplementationRule, ...]:
    sections = split_markdown_sections(pseudocode_markdown)
    pseudocode_lines = sections.get("Pseudocode", [])
    parsed_rules: list[ImplementationRule] = []
    for bullet in parse_top_level_bullets(pseudocode_lines):
        clause_references = extract_clause_references(bullet)
        parsed_rules.append(
            ImplementationRule(
                rule_text=bullet,
                clause_references=clause_references,
                employee_scope=implementation_scope_from_text(bullet),
            )
        )
    return tuple(parsed_rules)


def parse_excluded_conditions(pseudocode_markdown: str) -> tuple[ExcludedCondition, ...]:
    sections = split_markdown_sections(pseudocode_markdown)
    excluded_lines = sections.get("Conditions not considered by the pseudocode", [])
    parsed_conditions: list[ExcludedCondition] = []
    for bullet in parse_top_level_bullets(excluded_lines):
        clause_references = extract_clause_references(bullet)
        parsed_conditions.append(
            ExcludedCondition(condition_text=bullet, clause_references=clause_references)
        )
    return tuple(parsed_conditions)


def normalize_text_for_keywords(value: str) -> list[str]:
    normalized_text = re.sub(r"[^a-z0-9\s]+", " ", value.lower())
    keywords: list[str] = []
    for token in normalized_text.split():
        if len(token) <= 2 or token in STOPWORDS:
            continue
        keywords.append(token)
    return keywords


def keyword_overlap_ratio(source_text: str, target_text: str) -> float:
    source_keywords = set(normalize_text_for_keywords(source_text))
    if not source_keywords:
        return 0.0
    target_keywords = set(normalize_text_for_keywords(target_text))
    return len(source_keywords & target_keywords) / len(source_keywords)


def scopes_conflict(source_rule: RuleRecord, target_rule: ImplementationRule) -> bool:
    if not source_rule.employee_scope or not target_rule.employee_scope:
        return False
    return not bool(set(source_rule.employee_scope) & set(target_rule.employee_scope))


def find_best_matching_rule(
    source_rule: RuleRecord,
    implementation_rules: tuple[ImplementationRule, ...],
    excluded_conditions: tuple[ExcludedCondition, ...],
) -> tuple[ImplementationRule | None, str, str]:
    best_clause_match: ImplementationRule | None = None
    best_clause_overlap: tuple[str, ...] = ()
    for implementation_rule in implementation_rules:
        overlapping_clauses = tuple(
            clause_reference
            for clause_reference in source_rule.clause_references
            if clause_reference in implementation_rule.clause_references
        )
        if overlapping_clauses and len(overlapping_clauses) > len(best_clause_overlap):
            best_clause_match = implementation_rule
            best_clause_overlap = overlapping_clauses
    if best_clause_match is not None:
        if scopes_conflict(source_rule, best_clause_match):
            return best_clause_match, "failed", (
                "Matching clause references were found, but the employee scope is narrower than the source rule."
            )
        return best_clause_match, "passed", (
            "Matching clause references were found in the pseudocode implementation rules."
        )
    if source_rule.clause_references:
        for excluded_condition in excluded_conditions:
            overlapping_clauses = tuple(
                clause_reference
                for clause_reference in source_rule.clause_references
                if clause_reference in excluded_condition.clause_references
            )
            if overlapping_clauses:
                return None, "unresolved", (
                    "This reviewed source rule was explicitly excluded from executable pseudocode in `Conditions not considered by the pseudocode`."
                )
        return None, "failed", (
            "No matching clause references were found in the pseudocode implementation rules for this reviewed source rule."
        )
    best_text_match: ImplementationRule | None = None
    best_text_score = 0.0
    for implementation_rule in implementation_rules:
        overlap_ratio = keyword_overlap_ratio(source_rule.rule_text, implementation_rule.rule_text)
        if overlap_ratio > best_text_score:
            best_text_match = implementation_rule
            best_text_score = overlap_ratio
    if best_text_match is not None and best_text_score >= 0.45:
        return None, "unresolved", (
            "A similar implementation rule was found by text overlap, but no matching clause references were present."
        )
    return None, "failed", "No matching implementation rule was found for this reviewed source rule."


def find_missing_required_inputs(
    required_inputs: list[str],
    implementation_rules: tuple[ImplementationRule, ...],
) -> list[ValidationIssue]:
    normalized_inputs = [required_input.strip().lower() for required_input in required_inputs]
    if normalized_inputs != ["none"]:
        return []
    missing_messages: list[str] = []
    for implementation_rule in implementation_rules:
        normalized_rule = implementation_rule.rule_text.lower()
        if "works in accordance with a roster" in normalized_rule:
            missing_messages.append(
                "The pseudocode depends on whether a casual employee works in accordance with a roster, but `Required additional inputs` says `None`."
            )
        if "2-, 3-, or 4-week averaging arrangement" in normalized_rule or "roster cycle exceed" in normalized_rule:
            missing_messages.append(
                "The pseudocode depends on roster-cycle arrangement details, but `Required additional inputs` says `None`."
            )
    deduplicated_messages: list[str] = []
    for message in missing_messages:
        if message not in deduplicated_messages:
            deduplicated_messages.append(message)
    return [
        ValidationIssue(issue_type="required_inputs", severity="failed", message=message)
        for message in deduplicated_messages
    ]


def find_invalid_excluded_conditions(
    excluded_conditions: tuple[ExcludedCondition, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for excluded_condition in excluded_conditions:
        normalized_text = excluded_condition.condition_text.lower()
        if not excluded_condition.clause_references:
            issues.append(
                ValidationIssue(
                    issue_type="excluded_condition_missing_clause_reference",
                    severity="failed",
                    message="Each item in `Conditions not considered by the pseudocode` must include the source clause reference.",
                )
            )
        has_reason = any(
            marker in normalized_text
            for marker in ("because", "cannot", "can't", "unable", "not coded", "not modelled", "not modeled", "manual", "judgement", "judgment", "review", "outside scope")
        )
        if not has_reason:
            issues.append(
                ValidationIssue(
                    issue_type="excluded_condition_missing_reason",
                    severity="failed",
                    message="Each excluded condition should say why it is not represented in executable pseudocode.",
                )
            )
    return issues


def find_priority_items_without_matching_rules(
    pseudocode_markdown: str,
    implementation_rules: tuple[ImplementationRule, ...],
) -> list[ValidationIssue]:
    sections = split_markdown_sections(pseudocode_markdown)
    priority_items = parse_numbered_items(sections.get("Rule priority", []))
    issues: list[ValidationIssue] = []

    for priority_item in priority_items:
        normalized_priority = priority_item.strip().lower()
        if (
            " before " in normalized_priority
            and normalized_priority.startswith(("apply ", "process ", "check ", "review "))
        ):
            continue

        best_overlap = 0.0

        for implementation_rule in implementation_rules:
            overlap_ratio = keyword_overlap_ratio(
                priority_item,
                implementation_rule.rule_text,
            )
            if overlap_ratio > best_overlap:
                best_overlap = overlap_ratio

        if best_overlap < 0.45:
            issues.append(
                ValidationIssue(
                    issue_type="priority_without_rule",
                    severity="failed",
                    message=(
                        "Each `Rule priority` item should correspond to a real pseudocode "
                        f"rule. No matching pseudocode rule was found for: `{priority_item}`."
                    ),
                )
            )

    return issues


def validate_overtime_pseudocode_against_inventory(
    source_inventory: RuleInventory,
    pseudocode_markdown: str,
    *,
    target_path: Path | str,
) -> ValidationReport:
    sections = split_markdown_sections(pseudocode_markdown)
    implementation_rules = parse_implementation_rules(pseudocode_markdown)
    excluded_conditions = parse_excluded_conditions(pseudocode_markdown)
    required_inputs = parse_required_inputs(sections.get("Required additional inputs", []))

    rule_results: list[RuleValidationResult] = []
    issues: list[ValidationIssue] = []

    for source_rule in source_inventory.rules:
        matched_rule, status, message = find_best_matching_rule(
            source_rule,
            implementation_rules,
            excluded_conditions,
        )
        matched_clause_references = (
            matched_rule.clause_references if matched_rule is not None else ()
        )
        rule_results.append(
            RuleValidationResult(
                rule_id=source_rule.rule_id,
                status=status,
                source_rule_text=source_rule.rule_text,
                source_clause_references=source_rule.clause_references,
                matched_clause_references=matched_clause_references,
                message=message,
            )
        )

    issues.extend(find_missing_required_inputs(required_inputs, implementation_rules))
    issues.extend(find_invalid_excluded_conditions(excluded_conditions))
    issues.extend(
        find_priority_items_without_matching_rules(
            pseudocode_markdown,
            implementation_rules,
        )
    )

    passed_rule_count = len([result for result in rule_results if result.status == "passed"])
    failed_rule_count = len([result for result in rule_results if result.status == "failed"])
    unresolved_rule_count = len([result for result in rule_results if result.status == "unresolved"])
    has_failed_issues = any(issue.severity == "failed" for issue in issues)
    if failed_rule_count > 0 or has_failed_issues:
        overall_status = "failed"
    elif unresolved_rule_count > 0:
        overall_status = "unresolved"
    else:
        overall_status = "passed"

    return ValidationReport(
        source_path=str(source_inventory.source_path),
        target_path=str(target_path),
        overall_status=overall_status,
        passed_rule_count=passed_rule_count,
        failed_rule_count=failed_rule_count,
        unresolved_rule_count=unresolved_rule_count,
        rule_results=tuple(rule_results),
        issues=tuple(issues),
    )


def render_validation_report_markdown(report: ValidationReport) -> str:
    lines = [
        "# Step 5.1 validation report",
        "",
        f"- Overall status: `{report.overall_status}`",
        f"- Passed rules: `{report.passed_rule_count}`",
        f"- Failed rules: `{report.failed_rule_count}`",
        f"- Unresolved rules: `{report.unresolved_rule_count}`",
        "",
        "## Rule results",
        "",
    ]
    for result in report.rule_results:
        lines.extend(
            [
                f"### {result.rule_id}",
                "",
                f"- Status: `{result.status}`",
                f"- Source clauses: {', '.join(result.source_clause_references) or '(none)'}",
                f"- Matched clauses: {', '.join(result.matched_clause_references) or '(none)'}",
                f"- Message: {result.message}",
                "",
            ]
        )
    if report.issues:
        lines.extend(["## Issues", ""])
        for issue in report.issues:
            lines.append(f"- [{issue.severity}] {issue.message}")
    return "\n".join(lines).strip() + "\n"


def write_validation_artifacts(
    report: ValidationReport,
    *,
    json_path: Path | str,
    markdown_path: Path | str,
) -> tuple[Path, Path]:
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    write_text_output(
        json_destination,
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
    )
    write_text_output(
        markdown_destination,
        render_validation_report_markdown(report),
    )
    return json_destination, markdown_destination


def validate_and_write_outputs(
    *,
    destination: Path,
    output_text: str,
    source_inventory: RuleInventory,
) -> tuple[ValidationReport, str]:
    """Write pseudocode and validation artifacts, then return the validation state."""
    write_text_output(destination, output_text)
    validation_report = validate_overtime_pseudocode_against_inventory(
        source_inventory,
        output_text,
        target_path=destination,
    )
    validation_markdown_path = write_validation_artifacts(
        validation_report,
        json_path=validation_json_path_for_pseudocode(destination),
        markdown_path=validation_markdown_path_for_pseudocode(destination),
    )[1]
    validation_markdown = validation_markdown_path.read_text(encoding="utf-8")
    return validation_report, validation_markdown
