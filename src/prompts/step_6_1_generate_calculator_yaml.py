"""Prompt content for step 6.1 calculator Python generation."""

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
    """Build the prompt for the structured calculator questionnaire."""
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
You answer a fixed calculator questionnaire from reviewed award rules.

Use only the supplied step 3.2 reviewed JSON rules. Do not invent rules.
Return structured questionnaire answers only.

Important:
- This is one questionnaire, not free-form calculator code.
- Every answer must include evidence fields.
- If the source does not support a confident live answer, set `answer` to null,
  use status `needs_review` or `not_found`, and explain why.
- Prefer the standard case that should drive a first-pass payroll calculator.
- Record special cases in `special_case_notes`.
- Do not let exceptional variants replace the standard live rule.

Business interpretation rules:
- For core-hours limits, separate day workers and shift workers where the source supports that distinction.
- For two-tier overtime, answer whether there is a standard higher overtime tier, the higher multiplier, and the threshold in hours.
- For overtime multipliers, return the total paid rate, not the loading above base. Example: return `1.5` for 150% and `2.0` for 200%.
- For span overtime, answer only for day workers. If the award has a more complex span than one live cutoff, choose the best single live cutoff and explain the limitation in `special_case_notes`.
- For weekend treatment, answer whether weekend hours are overtime or penalty-based for each worker group and weekend day.
- If the reviewed creation rules say day-worker ordinary hours are confined to Monday to Friday or otherwise exclude Saturday/Sunday ordinary hours, do not classify day-worker weekend hours as penalty-based unless the reviewed rules also clearly provide a day-worker ordinary-weekend penalty regime. In that situation, prefer `overtime` for day workers and reserve `penalty` for worker groups such as shiftworkers whose ordinary hours can validly fall on the weekend.
- For gap between shifts, the calculator can only use one live threshold. Choose the standard live threshold and record differing worker-group thresholds in `special_case_notes`.
- For the gap breach answer, use the calculator loading above base rather than the total paid rate. Example: if the award says pay 200%, answer `1.0`, not `2.0`.
- For weekday penalties, include only standard cases that can be represented with numeric start and end hours. Do not include special cases that depend on rotation patterns, permanence, or non-time conditions unless they can be safely expressed in the structured rule shape.
- Exclude permanent night shift variants from the live weekday penalty list unless the reviewed rules clearly show that permanent night is the standard default case.
- Treat `weekday_penalties` as weekday extra penalties only. Do not include Saturday, Sunday, public holiday, meal-break, or other calendar/fact-dependent rules in the live weekday penalty lists.
- Do not treat casual loading as a penalty rule. Casual loading is part of the employee classification rate, not a separate live weekday penalty.
- If a weekday penalty is based on shift start time, shift finish time, or how long the shift runs, record that explicitly.
- If a weekday shift penalty is based on shift classification, prefer the real basis:
  - use `start` when the rule depends on when the shift starts
  - use `end` when the rule depends on when the shift finishes
  - use `duration` when the rule depends on how long the shift runs
- If a weekday penalty window crosses midnight, encode it with `end_hour < start_hour`. Example: 4.00 pm to before 4.00 am must be `start_hour = 16`, `end_hour = 4`.
- Do not use a `0` to `24` placeholder unless the award truly applies the same weekday shift penalty regardless of timing.
- Example: if an afternoon or night shift penalty applies because the shift finishes after 7.00 pm and by midnight, use `basis = end`, `start_hour = 19`, `end_hour = 24`.

Weekday penalty rule requirements:
- `code_name` must be a stable snake_case identifier.
- `type` must be `shift_based` or `time_based`.
- `basis` must be one of `start`, `end`, or `duration`.
- `start_hour` and `end_hour` must be numeric 24-hour clock values.
- `rate` must be the penalty loading above base time, such as `0.15` for 115%.
- `applies_to` must only use `day` and/or `shift`.
- `shift_based` can use either `start` or `end`.
- `time_based` usually uses `duration` only if the rule truly depends on shift length; otherwise use the basis that best reflects the trigger.
- Do not encode a whole-day `0` to `24` placeholder when the real rule depends on finishing time, permanence, rotation, Saturday/Sunday, or public holidays.
- If a penalty cannot be expressed with numeric windows, omit it from the live list and explain it in `other_penalty_notes` or `special_case_notes`.

Evidence rules:
- `source_rule_ids` must exactly match supplied `rule_id` values.
- `source_ruleset_keys` should use `overtime_creation`, `overtime_consequence`, and `penalties`.
- `reasoning_summary` should briefly explain how the answer was derived.
- `special_case_notes` should record anything important that does not fit the live calculator field cleanly.

Do not wrap the response in markdown fences.
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
