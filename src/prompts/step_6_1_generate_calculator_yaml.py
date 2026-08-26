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
                "rules": creation_rules,
            },
            "overtime_consequence": {
                "rules": consequence_rules,
            },
            "penalties": {
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
- The questionnaire covers only overtime creation, overtime consequences, and penalties.
- Do not infer minimum engagement, default breaks, top-up entitlements, or other rule families outside those three reviewed sources.
- Every answer must include evidence fields.
- Treat the supplied questionnaire schema as the authoritative calculator
  output contract. Use the reviewed step 3.2 rulesets as the source for values
  and document any assumption needed to fit those values into that contract.
- If the source does not support a confident live answer, set `answer` to null,
  use status `needs_review` or `not_found`, and explain why.
- Use status `not_applicable` when the calculator field has no role because of
  another structured answer. Populate the field with its neutral contract value
  (`0` for a loading, `[]` for a penalty list) and explain why it is not used.
- Prefer the standard case that should drive a first-pass payroll calculator.
- Put every supported value that has a questionnaire field into that structured answer. Use `special_case_notes` only for conditions that the questionnaire cannot represent.
- Do not let exceptional variants replace the standard live rule.

Business interpretation rules:
- For core-hours limits, separate day workers and shift workers where the source supports that distinction.
- For two-tier overtime, answer whether there is a standard higher overtime tier, the higher multiplier, the threshold in hours, and which named days use the extended overtime structure.
- Interpret `extended_overtime_days` as the answer to: "On which days does extended overtime apply?" List every exact day name on which the higher overtime tier applies after the threshold. Include Saturday and/or Sunday when the same two-tier overtime rule applies on those days; do not limit the list to Monday-Friday merely because ordinary hours are usually described as weekday hours.
- On a day listed in `extended_overtime_days`, if `has_two_tier_overtime` is true, weekend overtime multipliers such as Saturday or Sunday overtime do not control overtime-rate selection for that day.
- That override is limited to overtime-rate selection. Weekend penalty logic is separate.
- The extended overtime rate starts only when overtime hours are greater than the threshold, not when they are equal to the threshold.
- For overtime multipliers, return the total paid rate, not the loading above base. Example: return `1.5` for 150% and `2.0` for 200%.
- Answer permanent/non-casual and casual overtime multipliers separately. Casual overtime answers are total paid rates and must not be copied from the permanent rate when the reviewed rules state a distinct casual rate.
- Answer public-holiday overtime rates when they are present in the reviewed overtime-consequence rules.
- For span overtime, answer only for day workers. Return both the ordinary-span start and end when supported. If the award has day-specific variants that do not fit the default window, record those variants in `special_case_notes`.
- For weekend treatment, answer whether weekend hours are overtime or penalty-based for each worker group and weekend day.
- When a worker group's weekend treatment is `overtime`, set that worker group's
  ordinary penalty loading and casual ordinary penalty loading to `0` with
  status `not_applicable`. Overtime rates are supplied through `PAY_RATES`.
- Answer casual day-treatment loadings separately from permanent loadings. These answers are loadings above base, not total paid rates.
- Answer public-holiday day and shift treatment only when supported by the reviewed overtime or penalties rules.
- If the reviewed creation rules say day-worker ordinary hours are confined to Monday to Friday or otherwise exclude Saturday/Sunday ordinary hours, do not classify day-worker weekend hours as penalty-based unless the reviewed rules also clearly provide a day-worker ordinary-weekend penalty regime. In that situation, prefer `overtime` for day workers and reserve `penalty` for worker groups such as shiftworkers whose ordinary hours can validly fall on the weekend.
- For gap between shifts, the calculator can only use one live threshold. Choose the standard live threshold and record differing worker-group thresholds in `special_case_notes`.
- Answer the casual gap loading separately when the reviewed rules state one.
- If the reviewed gap payment expressly excludes casual employees, answer the
  casual gap loading as `0` with status `not_applicable`. Explain that the live
  gap-rule contract cannot exclude casual employees and therefore requires
  human confirmation.
- For the gap breach answer, use the calculator loading above base rather than the total paid rate. Example: if the award says pay 200%, answer `1.0`, not `2.0`.
- For ordinary-hour penalties, include only cases that can be represented with numeric start and end hours. Do not include special cases that depend on rotation patterns, permanence, or non-time conditions unless they can be safely expressed in the structured rule shape.
- An empty ordinary-hour penalty list is a complete answer when the reviewed
  rules confirm there are no rules of that type that fit the contract. Return
  `[]` with status `not_applicable`, rather than `not_found`.
- Exclude permanent night shift variants from the live weekday penalty list unless the reviewed rules clearly show that permanent night is the standard default case.
- Do not put standalone Saturday, Sunday, or public-holiday rules in the ordinary-hour penalty lists; those belong in day treatment. A shift penalty that can operate on several days should list every supported day in its `days` field.
- Do not analyse or answer questions about the employee's ordinary casual loading. It is outside this overtime-and-penalties questionnaire.
- A casual penalty rate is still required for each live penalty rule. If the reviewed rule applies to employees generally and states no different casual penalty, use the same loading as `rate` for `casual_rate`.
- The daily calculator contract varies by worker type, not by shift timing.
  `day_worker_daily_limit_hours` is the `day` worker threshold and
  `shift_worker_daily_limit_hours` is the `shift` worker threshold. If the
  reviewed rules provide only an 8-hour day-shift boundary and a 10-hour
  night-shift boundary, use `8` for the day-worker field and `10` for the
  shiftworker field as an explicit contract-alignment assumption. Record that
  assumption in `reasoning_summary` and `special_case_notes`.
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
- `basis` must be `start`, `end`, or `duration` for a shift-based rule, and `time` for a time-based payable window.
- `start_hour` and `end_hour` must be numeric 24-hour clock values.
- `rate` must be the penalty loading above base time, such as `0.15` for 115%.
- `casual_rate` is the penalty loading above base that applies to a casual employee. If no distinct casual penalty is stated, use the same value as `rate`; do not add ordinary casual loading.
- `applies_to` must only use `day` and/or `shift`.
- `days` must list every named day on which the penalty may operate according to the reviewed rules.
- `shift_based` can use either `start` or `end`.
- `time_based` uses `time` because its start and end are the payable clock-time window.
- Do not encode a whole-day `0` to `24` placeholder when the real rule depends on finishing time, permanence, rotation, Saturday/Sunday, or public holidays.
- If a penalty cannot be expressed with numeric windows, omit it from the live list and explain it in `other_penalty_notes` or `special_case_notes`.

Evidence rules:
- `source_rule_ids` are optional evidence breadcrumbs only. Include them when helpful, but do not block an answer on exact rule-id matching.
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
