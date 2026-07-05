"""Prompt content for step 6.1 calculator YAML generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_messages(
    *,
    award_code: str,
    creation_json_path: Path,
    creation_rules: list[dict[str, Any]],
    consequence_json_path: Path,
    consequence_rules: list[dict[str, Any]],
    penalties_json_path: Path,
    penalties_rules: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build the prompt for calculator-ready YAML derivation."""
    payload = {
        "award_code": award_code,
        "source_artifacts": {
            "overtime_creation": {
                "path": str(creation_json_path),
                "rules": creation_rules,
            },
            "overtime_consequence": {
                "path": str(consequence_json_path),
                "rules": consequence_rules,
            },
            "penalties": {
                "path": str(penalties_json_path),
                "rules": penalties_rules,
            },
        },
    }

    instructions = """
You create a calculator-ready rules profile from reviewed award rules.

Use only the supplied step 3.2 reviewed JSON rules. Do not invent rules.
If a field cannot be answered confidently from the supplied rules, leave the field null
or an empty object as appropriate, and mark the evidence status as `needs_review`.

The target fields are:
- ordinary_hours_limit_daily
- ordinary_hours_limit_weekly
- day_worker_ordinary_hours_daily
- day_worker_ordinary_hours_weekly
- standard_overtime_rate
- extended_overtime_rate
- sunday_overtime_rate
- saturday_overtime_rate
- saturday_penalty_rate
- sunday_penalty_rate
- apply_span_overtime
- span_overtime_hour
- gap_penalty_hours
- gap_penalty_rate
- penalties
- hours_pen_rules
- weekend_rules
- two_tier_overtime
- two_tier_overtime_threshold

Return one YAML object with exactly this top-level shape:
- calculator_rules:
- field_evidence:

Formatting requirements for `calculator_rules`:
- Store plain calculator-consumable values only.
- Do not wrap scalar values in objects like `{value: ..., unit: ..., evidence_status: ...}`.
- Do not include `evidence_status`, `unit`, `status`, or reasoning text inside `calculator_rules`.
- Put all status, traceability, and reasoning metadata in `field_evidence` only.
- `penalties`, `hours_pen_rules`, and `weekend_rules` should be plain nested mappings with no embedded evidence fields.

Interpretation guidance:
- `ordinary_hours_limit_*` should represent the general shift-worker ordinary-hours limit when the award distinguishes day workers from other workers.
- `day_worker_ordinary_hours_*` should represent day-worker ordinary-hours limits where the award distinguishes them.
- `penalties` should preserve structured penalty rules when the reviewed rules clearly describe them.
- `weekend_rules` should preserve whether weekend work is overtime or penalty-based, separately for day workers and shift workers where the source supports that distinction.
- `hours_pen_rules` should only be used where the source clearly creates time-band penalties that apply by hour rather than by whole shift.
- `two_tier_overtime` and `two_tier_overtime_threshold` should only be set when the source expressly supports a first-band and later-band overtime structure.

Evidence requirements:
- For every populated top-level field, include source_ruleset_keys, source_rule_ids, and clause_references.
- source_rule_ids must exactly match the supplied rule_id values.
- Use `derived` when the answer is supported by the award rules.
- Use `needs_review` when the answer is incomplete, ambiguous, or only partially supported.
- Do not use `defaulted` for any field in this model response. Defaults are applied later by the application.
- Do not wrap the YAML in markdown fences.
""".strip()

    return [
        {
            "role": "system",
            "content": instructions,
        },
        {
            "role": "user",
            "content": json.dumps(payload, indent=2),
        },
    ]
