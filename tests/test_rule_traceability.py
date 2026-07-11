from pathlib import Path

from src.rule_traceability.core import PhaseArtifact, build_trace_report, parse_ruleset_python


RULESET = """
class AgedCareRules:
    ORDINARY_HOURS_LIMIT_DAILY = 12
    PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP = True
    SUNDAY_OVERTIME_RATE = 2.5
    WEEKEND_RULES = {'day': {'Sunday': {'rate': 2.5}}}
"""


def test_python_rules_are_extracted_with_source_lines_and_values():
    rules = parse_ruleset_python(RULESET, ignored_names={"PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP"})

    assert [rule.name for rule in rules] == ["ORDINARY_HOURS_LIMIT_DAILY", "SUNDAY_OVERTIME_RATE", "WEEKEND_RULES"]
    assert rules[0].value == 12
    assert rules[0].source_line == 3


def test_trace_report_distinguishes_missing_accurate_and_inaccurate_rules(tmp_path: Path):
    source = tmp_path / "rules.py"
    source.write_text(RULESET)
    phases = [
        PhaseArtifact("Expert A", "expert_a.md", "ordinary_hours_limit_daily: 12\nsunday_overtime_rate: 2.0"),
        PhaseArtifact("Python Output", "calculator.py", "ORDINARY_HOURS_LIMIT_DAILY = 12\n# WEEKEND_RULES omitted"),
    ]

    report = build_trace_report(
        source,
        phases,
        ignored_names={"PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP"},
    )
    statuses = {(finding.rule_name, finding.phase): finding.status for finding in report.findings}

    assert statuses[("ORDINARY_HOURS_LIMIT_DAILY", "Expert A")] == "present_accurate"
    assert statuses[("SUNDAY_OVERTIME_RATE", "Expert A")] == "present_inaccurate"
    assert statuses[("WEEKEND_RULES", "Expert A")] == "missing"
    assert statuses[("ORDINARY_HOURS_LIMIT_DAILY", "Python Output")] == "present_accurate"
    assert statuses[("WEEKEND_RULES", "Python Output")] == "present_inaccurate"


def test_multiline_python_and_json_values_are_compared_as_structures(tmp_path: Path):
    source = tmp_path / "rules.py"
    source.write_text(RULESET)
    python_phase = PhaseArtifact(
        "Formatted",
        "formatted.py",
        "WEEKEND_RULES = {\n    'day': {'Sunday': {'rate': 2.5}}\n}\n",
    )
    json_phase = PhaseArtifact(
        "Pseudocode",
        "pseudocode.json",
        '{"weekend_rules": {"day": {"Sunday": {"rate": 2.5}}}}',
    )

    report = build_trace_report(source, [python_phase, json_phase], ignored_names={"PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP"})
    statuses = {(finding.phase, finding.status) for finding in report.findings if finding.rule_name == "WEEKEND_RULES"}

    assert ("Formatted", "present_accurate") in statuses
    assert ("Pseudocode", "present_accurate") in statuses
