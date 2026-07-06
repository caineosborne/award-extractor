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

Interpret the award first, then map it to the calculator fields.
Do not let the target field list prevent you from answering the real award question.
When the award clearly answers a business question, prefer answering it in the closest
calculator field rather than suppressing it just because the calculator shape is narrow.

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

Interpretation questions you must answer from the reviewed rules:
- Do any employees get overtime because they work outside a span or spread of ordinary hours?
- If yes, which employees and what standard span boundary should be used for the calculator field?
- Do any employees get penalties because of when in the day they work?
- If yes, are those penalties shift-based or time-based?
- Which of those are standard/default cases versus exceptional/special cases?

Standard-case rule:
- Prefer the standard or default case that would usually be implemented first in a payroll calculator.
- Do not choose a special variant when a broader standard rule exists.
- Example: if there is a general afternoon/night shift penalty and also a special permanent night shift penalty, treat the general afternoon/night shift penalty as the standard live rule.
- Keep exceptional, rarer, or special-case variants in evidence/reasoning unless the calculator clearly has a separate field or structure for them.

Calculator formatting requirements:
- Use calculator-ready numeric values, not strings like `150%` or `25%`.
- Overtime rates must be decimal multipliers such as `1.5` and `2.0`.
- Penalty rates must be decimal loadings above base time such as `0.15`, `0.25`, `0.5`, or `1.0`.
- `gap_penalty_rate` should be the extra penalty loading, not the total paid rate.
- The current calculator runtime is strict. Prefer a safe null or empty mapping over a richer structure that the runtime cannot execute.
- If the reviewed rules clearly say some employees get overtime based on time-of-day boundaries, set `apply_span_overtime` to `true` and provide the best single standard boundary the current calculator can use.
- If the real award rule is more complex than one single boundary, still provide the best standard live boundary and explain the limitation in evidence.
- `gap_penalty_hours` must be a single numeric threshold or `null`. If the award has different gap thresholds by worker type, return `null` and explain that in evidence rather than returning a mapping.
- `two_tier_overtime_threshold` should be a single number when one threshold applies generally. Use a mapping only when the source clearly requires different thresholds by worker type.
- `weekend_rules` should use this shape where supported:
  day:
    Saturday: {is_overtime: true|false, rate: number|null}
    Sunday: {is_overtime: true|false, rate: number|null}
  shift:
    Saturday: {is_overtime: true|false, rate: number|null, penalty_rate: number|null}
    Sunday: {is_overtime: true|false, rate: number|null, penalty_rate: number|null}
- For shift-worker weekend rules, use `penalty_rate` when weekend work is penalty-based rather than overtime-based.
- For day-worker weekend rules, only populate entries that the current runtime can safely represent. If the award creates an ordinary-hours weekend penalty that the runtime cannot safely execute from `WEEKEND_RULES`, leave that entry out and explain it in evidence.
- `penalties` should use named entries with this shape where supported:
  some_penalty_name:
    type: shift_based | time_based
    start: number
    end: number
    rate: number
    description: string
    applies_to: [shift, day] or a narrower supported subset
- For shift penalties, prefer live entries for standard/default penalties that the calculator can apply broadly.
- Keep rarer variants such as permanent-night-only rules in evidence unless they are the main standard rule being applied.
- Only include a live `penalties` entry when both `start` and `end` are numeric runtime-safe values. Do not return live penalty entries with `start: null` or `end: null`.
- `hours_pen_rules` should be a plain mapping of calculator-ready time-band penalties only. If the source does not clearly support such a structure, return `{}`.
- If the reviewed rules do not clearly support an exact calculator structure for `penalties`, `hours_pen_rules`, or `weekend_rules`, prefer `{}` and mark the evidence as `needs_review` rather than inventing a shape.

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
