from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


CLAUSE_REFERENCE_PATTERN = re.compile(r"(?<!\d)\d+(?:\.\d+)*(?:\([A-Za-z0-9]+\))*")
CLAUSE_BLOCK_PATTERN = re.compile(r"Clauses?\s+(?P<content>[^\n]+)", re.IGNORECASE)
SOURCE_BLOCK_PATTERN = re.compile(r"Source:\s*(?P<content>[^\n]+)", re.IGNORECASE)
BRACKET_BLOCK_PATTERN = re.compile(r"\[(?P<content>[^\]]+)\]")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class RuleRecord:
    """One normalized rule extracted from a reviewed markdown artifact."""

    rule_id: str
    section_heading: str
    rule_text: str
    clause_references: tuple[str, ...]
    employee_scope: tuple[str, ...]
    source_line_start: int
    source_line_end: int


@dataclass(frozen=True)
class RuleInventory:
    """Ordered inventory of rules parsed from one source artifact."""

    inventory_name: str
    source_path: str
    source_stage: str
    domain: str
    rules: tuple[RuleRecord, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    slug = SLUG_PATTERN.sub("-", normalized).strip("-")
    return slug or "section"


def extract_clause_references(text: str) -> tuple[str, ...]:
    clause_references: list[str] = []

    for block_pattern in (CLAUSE_BLOCK_PATTERN, SOURCE_BLOCK_PATTERN, BRACKET_BLOCK_PATTERN):
        for clause_block_match in block_pattern.finditer(text):
            clause_block = clause_block_match.group("content")
            for clause_reference_match in CLAUSE_REFERENCE_PATTERN.finditer(clause_block):
                clause_reference = clause_reference_match.group(0)
                if clause_reference not in clause_references:
                    clause_references.append(clause_reference)

    return tuple(clause_references)


def employee_scope_from_heading(heading: str) -> tuple[str, ...]:
    normalized_heading = heading.strip().lower()

    if "all employees" in normalized_heading:
        return ("full-time", "part-time", "casual")

    scope: list[str] = []

    if "full-time" in normalized_heading:
        scope.append("full-time")
    if "part-time" in normalized_heading:
        scope.append("part-time")
    if "casual" in normalized_heading:
        scope.append("casual")

    return tuple(scope)


def parse_rule_inventory_from_markdown(
    markdown_text: str,
    *,
    source_path: Path | str,
    inventory_name: str,
    source_stage: str,
    domain: str,
) -> RuleInventory:
    """Parse heading-grouped top-level bullets into an ordered rule inventory."""
    current_heading = "Ungrouped"
    current_scope = ()
    rule_lines: list[str] = []
    rule_start_line = 0
    section_rule_counts: dict[str, int] = {}
    parsed_rules: list[RuleRecord] = []

    lines = markdown_text.splitlines()

    def flush_rule(end_line_number: int) -> None:
        nonlocal rule_lines, rule_start_line

        if not rule_lines:
            return

        rule_text = "\n".join(rule_lines).strip()
        section_slug = slugify(current_heading)
        section_rule_counts[section_slug] = section_rule_counts.get(section_slug, 0) + 1
        rule_id = f"{section_slug}_{section_rule_counts[section_slug]:03d}"

        parsed_rules.append(
            RuleRecord(
                rule_id=rule_id,
                section_heading=current_heading,
                rule_text=rule_text,
                clause_references=extract_clause_references(rule_text),
                employee_scope=current_scope,
                source_line_start=rule_start_line,
                source_line_end=end_line_number,
            )
        )

        rule_lines = []
        rule_start_line = 0

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            flush_rule(line_number - 1)
            current_heading = line.removeprefix("## ").strip()
            current_scope = employee_scope_from_heading(current_heading)
            continue

        if line.startswith("- "):
            flush_rule(line_number - 1)
            rule_lines = [line]
            rule_start_line = line_number
            continue

        if rule_lines:
            if line.startswith("  ") or not line.strip():
                rule_lines.append(line)
                continue

            flush_rule(line_number - 1)

    flush_rule(len(lines))

    return RuleInventory(
        inventory_name=inventory_name,
        source_path=str(source_path),
        source_stage=source_stage,
        domain=domain,
        rules=tuple(parsed_rules),
    )


def render_inventory_for_prompt(inventory: RuleInventory) -> str:
    """Render a compact, explicit rule inventory for downstream prompts."""
    rendered_rules: list[str] = []

    for rule in inventory.rules:
        scope_display = ", ".join(rule.employee_scope) if rule.employee_scope else "unspecified"
        clause_display = ", ".join(rule.clause_references) if rule.clause_references else "none"
        rendered_rules.append(
            "\n".join(
                [
                    f"- Rule ID: {rule.rule_id}",
                    f"  Section: {rule.section_heading}",
                    f"  Scope: {scope_display}",
                    f"  Clauses: {clause_display}",
                    f"  Rule: {rule.rule_text}",
                ]
            )
        )

    return "\n".join(rendered_rules)
