"""Deterministic validation for step 5.1 pseudocode outputs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from src.common.output_naming import (
    validation_json_path_for_pseudocode as naming_validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode as naming_validation_markdown_path_for_pseudocode,
)
from src.common.output_paths import write_text_with_archive
from src.common.rule_inventory import RuleInventory, RuleRecord, extract_clause_references


SECTION_HEADING_PATTERN = re.compile(r"^##\s+(?P<heading>.+?)\s*$")
STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "will",
    "where",
    "when",
    "over",
    "than",
    "time",
    "worked",
    "hours",
    "hour",
    "employee",
    "employees",
    "ordinary",
    "overtime",
    "any",
    "all",
    "after",
    "before",
    "into",
    "from",
    "they",
    "them",
    "more",
    "week",
    "day",
    "work",
}


@dataclass(frozen=True)
class ImplementationRule:
    """One rule-like bullet extracted from 5B pseudocode output."""

    rule_text: str
    clause_references: tuple[str, ...]
    employee_scope: tuple[str, ...]


@dataclass(frozen=True)
class RuleValidationResult:
    """Coverage result for one required source rule."""

    rule_id: str
    status: str
    source_rule_text: str
    source_clause_references: tuple[str, ...]
    matched_clause_references: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation issue."""

    issue_type: str
    severity: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """Full validation report for one source/target pair."""

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


def normalize_text_for_keywords(value: str) -> list[str]:
    normalized_text = re.sub(r"[^a-z0-9\s]+", " ", value.lower())
    keywords: list[str] = []

    for token in normalized_text.split():
        if len(token) <= 2:
            continue
        if token in STOPWORDS:
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
) -> tuple[ImplementationRule | None, str, str]:
    best_clause_match: ImplementationRule | None = None
    best_clause_overlap: tuple[str, ...] = ()

    for implementation_rule in implementation_rules:
        overlapping_clauses = tuple(
            clause_reference
            for clause_reference in source_rule.clause_references
            if clause_reference in implementation_rule.clause_references
        )
        if overlapping_clauses:
            if len(overlapping_clauses) > len(best_clause_overlap):
                best_clause_match = implementation_rule
                best_clause_overlap = overlapping_clauses

    if best_clause_match is not None:
        if scopes_conflict(source_rule, best_clause_match):
            return (
                best_clause_match,
                "failed",
                "Matching clause references were found, but the employee scope is narrower than the source rule.",
            )

        return (
            best_clause_match,
            "passed",
            "Matching clause references were found in the pseudocode implementation rules.",
        )

    if source_rule.clause_references:
        return (
            None,
            "failed",
            "No matching clause references were found in the pseudocode implementation rules for this reviewed source rule.",
        )

    best_text_match: ImplementationRule | None = None
    best_text_score = 0.0

    for implementation_rule in implementation_rules:
        overlap_ratio = keyword_overlap_ratio(
            source_rule.rule_text,
            implementation_rule.rule_text,
        )
        if overlap_ratio > best_text_score:
            best_text_match = implementation_rule
            best_text_score = overlap_ratio

    if best_text_match is not None and best_text_score >= 0.45:
        return (
            best_text_match,
            "unresolved",
            "A similar implementation rule was found by text overlap, but no matching clause references were present.",
        )

    return (
        None,
        "failed",
        "No matching implementation rule was found for this reviewed source rule.",
    )


def find_missing_required_inputs(
    required_inputs: list[str],
    implementation_rules: tuple[ImplementationRule, ...],
) -> list[ValidationIssue]:
    normalized_inputs = [required_input.strip().lower() for required_input in required_inputs]
    declares_none = normalized_inputs == ["none"]
    if not declares_none:
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
        ValidationIssue(
            issue_type="required_inputs",
            severity="failed",
            message=message,
        )
        for message in deduplicated_messages
    ]


def find_priority_issues(
    priority_items: list[str],
    implementation_rules: tuple[ImplementationRule, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for priority_item in priority_items:
        if keyword_overlap_ratio(
            priority_item,
            "\n".join(implementation_rule.rule_text for implementation_rule in implementation_rules),
        ) >= 0.45:
            continue

        issues.append(
            ValidationIssue(
                issue_type="priority_without_rule",
                severity="unresolved",
                message=(
                    "Rule priority item does not have a corresponding implementation rule: "
                    f"{priority_item}"
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
    priority_items = parse_numbered_items(sections.get("Rule priority", []))
    required_inputs = parse_required_inputs(sections.get("Required additional inputs", []))

    rule_results: list[RuleValidationResult] = []

    for source_rule in source_inventory.rules:
        matched_rule, status, message = find_best_matching_rule(
            source_rule,
            implementation_rules,
        )
        matched_clause_references = ()
        if matched_rule is not None:
            matched_clause_references = matched_rule.clause_references

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

    issues = find_priority_issues(priority_items, implementation_rules)
    issues.extend(find_missing_required_inputs(required_inputs, implementation_rules))

    passed_rule_count = sum(1 for result in rule_results if result.status == "passed")
    failed_rule_count = sum(1 for result in rule_results if result.status == "failed")
    unresolved_rule_count = sum(1 for result in rule_results if result.status == "unresolved")
    failed_issue_count = sum(1 for issue in issues if issue.severity == "failed")

    overall_status = "passed"
    if failed_rule_count or failed_issue_count:
        overall_status = "failed"
    elif unresolved_rule_count:
        overall_status = "unresolved"

    return ValidationReport(
        source_path=source_inventory.source_path,
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
        "# 5B validation report",
        "",
        f"- Source path: `{report.source_path}`",
        f"- Target path: `{report.target_path}`",
        f"- Overall status: `{report.overall_status}`",
        f"- Passed rules: `{report.passed_rule_count}`",
        f"- Failed rules: `{report.failed_rule_count}`",
        f"- Unresolved rules: `{report.unresolved_rule_count}`",
        "",
        "## Rule results",
        "",
    ]

    for result in report.rule_results:
        lines.append(f"### {result.rule_id}")
        lines.append("")
        lines.append(f"- Status: `{result.status}`")
        lines.append(
            "- Source clauses: "
            f"`{', '.join(result.source_clause_references) if result.source_clause_references else 'none'}`"
        )
        lines.append(
            "- Matched clauses: "
            f"`{', '.join(result.matched_clause_references) if result.matched_clause_references else 'none'}`"
        )
        lines.append(f"- Message: {result.message}")
        lines.append("- Source rule:")
        lines.append("")
        lines.append(result.source_rule_text)
        lines.append("")

    lines.append("## Additional issues")
    lines.append("")

    if not report.issues:
        lines.append("- None")
    else:
        for issue in report.issues:
            lines.append(f"- `{issue.severity}` {issue.issue_type}: {issue.message}")

    return "\n".join(lines)


def write_validation_artifacts(
    report: ValidationReport,
    *,
    json_path: Path | str,
    markdown_path: Path | str,
) -> tuple[Path, Path]:
    json_output_path = Path(json_path)
    markdown_output_path = Path(markdown_path)

    write_text_with_archive(
        json_output_path,
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
    )
    write_text_with_archive(
        markdown_output_path,
        render_validation_report_markdown(report),
    )

    return json_output_path, markdown_output_path
