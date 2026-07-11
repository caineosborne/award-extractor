from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuleDefinition:
    """One auditable rule extracted from the ruleset source of truth."""

    rule_id: str
    name: str
    value: Any
    source_line: int
    source_text: str


@dataclass(frozen=True)
class PhaseArtifact:
    """A named output from one pipeline phase."""

    name: str
    path: str
    text: str


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    rule_name: str
    phase: str
    path: str
    status: str
    expected_value: Any
    observed_value: Any
    evidence: str
    line: int | None
    reason: str


@dataclass(frozen=True)
class TraceReport:
    source_path: str
    ignored_names: tuple[str, ...]
    rules: tuple[RuleDefinition, ...]
    findings: tuple[RuleFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _literal_value(node: ast.AST) -> Any:
    """Convert a Python literal into JSON-like values for exact comparison."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return ast.unparse(node)


def parse_ruleset_python(
    source_text: str,
    *,
    ignored_names: set[str] | None = None,
) -> tuple[RuleDefinition, ...]:
    """Extract class-level assignments, preserving their source line and value."""
    ignored = ignored_names or set()
    tree = ast.parse(source_text)
    rules: list[RuleDefinition] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value_node = node.value
        if value_node is None:
            continue

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id.startswith("_") or target.id in ignored:
                continue
            rules.append(
                RuleDefinition(
                    rule_id=target.id.lower(),
                    name=target.id,
                    value=_literal_value(value_node),
                    source_line=node.lineno,
                    source_text=source_text.splitlines()[node.lineno - 1].strip(),
                )
            )

    return tuple(sorted(rules, key=lambda rule: (rule.source_line, rule.name)))


def _normalise_name(name: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _value_candidates(value: Any) -> set[str]:
    candidates = {
        str(value).lower(),
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).lower(),
    }
    if isinstance(value, bool):
        candidates.update({str(value).lower(), ("true" if value else "false")})
    if isinstance(value, (list, tuple)):
        candidates.add(", ".join(str(item).lower() for item in value))
    return candidates


def _parsed_phase_value(text: str, rule_name: str) -> tuple[Any, int] | None:
    """Read an exact assignment from Python or a top-level JSON object."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == rule_name for target in targets):
                if node.value is not None:
                    return _literal_value(node.value), node.lineno

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        for key, value in parsed.items():
            if _normalise_name(str(key)) == _normalise_name(rule_name):
                return value, 1
    return None


def _find_rule_in_phase(rule: RuleDefinition, phase: PhaseArtifact) -> RuleFinding:
    parsed_value = _parsed_phase_value(phase.text, rule.name)
    if parsed_value is not None:
        observed_value, line_number = parsed_value
        status = "present_accurate" if observed_value == rule.value else "present_inaccurate"
        reason = (
            "The parsed phase value exactly matches the ruleset value."
            if status == "present_accurate"
            else "The parsed phase value differs from the ruleset value."
        )
        evidence = phase.text.splitlines()[line_number - 1].strip() if phase.text.splitlines() else ""
        return RuleFinding(rule.rule_id, rule.name, phase.name, phase.path, status, rule.value, observed_value, evidence, line_number, reason)

    expected_name = _normalise_name(rule.name)
    lines = phase.text.splitlines()
    name_pattern = re.compile(
        rf"(?<![a-z0-9])(?:{re.escape(rule.name.lower())}|{re.escape(expected_name)})(?![a-z0-9])"
    )
    value_candidates = _value_candidates(rule.value)

    for line_number, line in enumerate(lines, start=1):
        if not name_pattern.search(line.lower()):
            continue

        lower_line = line.lower()
        observed_value = next((candidate for candidate in value_candidates if candidate in lower_line), None)
        if observed_value is not None:
            status = "present_accurate"
            reason = "The rule name and expected value were found in this phase."
            if isinstance(rule.value, bool):
                observed_value = observed_value == "true"
            else:
                observed_value = rule.value
            return RuleFinding(rule.rule_id, rule.name, phase.name, phase.path, status, rule.value, observed_value, line.strip(), line_number, reason)

        return RuleFinding(
            rule.rule_id, rule.name, phase.name, phase.path, "present_inaccurate", rule.value, line.strip(), line.strip(), line_number,
            "The rule name was found, but the expected value was not found on the same line.",
        )

    return RuleFinding(
        rule.rule_id, rule.name, phase.name, phase.path, "missing", rule.value, None, "", None,
        "No matching rule name was found in this phase.",
    )


def build_trace_report(
    source_path: Path | str,
    phases: list[PhaseArtifact],
    *,
    ignored_names: set[str] | None = None,
) -> TraceReport:
    """Trace every included ruleset assignment through every supplied phase."""
    source = Path(source_path)
    ignored = ignored_names or set()
    rules = parse_ruleset_python(source.read_text(), ignored_names=ignored)
    findings = tuple(
        finding
        for rule in rules
        for phase in phases
        for finding in [_find_rule_in_phase(rule, phase)]
    )
    return TraceReport(str(source), tuple(sorted(ignored)), rules, findings)


def _markdown_report(report: TraceReport) -> str:
    rows = [
        "# Rule traceability report",
        "",
        f"Source ruleset: `{report.source_path}`",
        "",
        "| Rule | Phase | Status | Evidence | Location |",
        "|---|---|---|---|---|",
    ]
    for finding in report.findings:
        evidence = finding.evidence.replace("|", "\\|") or "—"
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        rows.append(f"| `{finding.rule_name}` | {finding.phase} | **{finding.status}** | `{evidence}` | `{location}` |")
    rows.extend(["", "Ignored rule names: " + (", ".join(report.ignored_names) or "none")])
    return "\n".join(rows) + "\n"


def write_trace_report(report: TraceReport, destination: Path | str) -> None:
    """Write JSON or Markdown according to the destination suffix."""
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n")
    else:
        output.write_text(_markdown_report(report))


def _phase_argument(value: str) -> PhaseArtifact:
    if "=" not in value:
        raise argparse.ArgumentTypeError("phase must use LABEL=PATH")
    name, path_text = value.split("=", 1)
    path = Path(path_text)
    if not name.strip() or not path.is_file():
        raise argparse.ArgumentTypeError(f"phase must name an existing file: {value}")
    return PhaseArtifact(name.strip(), str(path), path.read_text())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trace ruleset rules across pipeline phase artifacts.")
    parser.add_argument("ruleset_python", help="Python file containing the ruleset class.")
    parser.add_argument("--phase", action="append", type=_phase_argument, required=True, help="Phase label and file: 'Expert A=path'. Repeat for each phase.")
    parser.add_argument("--ignore-name", action="append", default=[], help="Ruleset constant to exclude. Repeat as needed.")
    parser.add_argument("--output", required=True, help="Output .json or .md path.")
    args = parser.parse_args(argv)
    report = build_trace_report(args.ruleset_python, args.phase, ignored_names=set(args.ignore_name))
    write_trace_report(report, args.output)
    print(f"Wrote {args.output} ({len(report.rules)} rules, {len(report.findings)} findings).")


if __name__ == "__main__":
    main()
