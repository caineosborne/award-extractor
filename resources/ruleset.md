# Pay Calculator Ruleset Contract

Last reviewed against the current codebase: 18 August 2026 (code at
`5515321`).

This is the canonical contract for award rules consumed by the pay calculator.
It is written for both people and agents authoring rulesets. It describes the
software contract implemented by the live calculator, not industrial-award
advice. Where a limitation is recorded below, upstream calculations must
preserve that limitation rather than infer a more complete award treatment.

## Scope and vocabulary

- A **shift** is one attendance segment. A logical **workday** groups every
  segment with the same `week` and `day` and can contain more than one
  non-overlapping segment.
- The request supports exactly two numbered weeks (`1` and `2`), so a
  `pay_period` is a fortnight in the current product.
- `day` is one of `Monday` through `Sunday`.
- `worker_type` is `day` or `shift`; `employment_type` is `full_time`,
  `part_time`, or `casual`.
- A **multiplier** is total pay (for example `1.5` means 150% of base pay).
  A **loading** is extra pay (for example `0.25` means base pay plus 25%).

Hours finish in exactly one base bucket: **ordinary** or **overtime**. A
penalty is a loading on final ordinary hours, not a third hours bucket. The
calculator removes or caps penalty hours when ordinary time becomes overtime.
Day-treatment, one matching whole-shift penalty, and matching time-based
penalties can add together on the same ordinary hours. Multiple matching
time-based penalties are additive. If multiple `shift_based` penalties match,
only the last one in dictionary order is retained by the current calculator.
A public-holiday treatment suppresses custom penalties for the holiday
attendance, and a gap-between-shifts loading suppresses all other ordinary-hour
loadings for the affected workday.

## Authoring a ruleset

Register an award in `backend/config/awards.json`, then provide a Python class in
`backend/services/rules/`. New rulesets should use this grouped contract:

```python
class ExampleRules:
    SHIFT_RULES = {...}
    ORDINARY_TIME_RULES = {...}
    DAY_TREATMENT_RULES = {...}
    PAY_RATES = {...}
    GAP_BETWEEN_SHIFTS_RULE = {...}
    ORDINARY_HOUR_PENALTIES = {...}
    TOP_UP_RULES = {...}
```

`CANONICAL_RULESET` is not read by the live loader and is not required. All
seven grouped attributes below are required by both the source validator and
the calculator. Do not use legacy flat attributes: the live loader reads the
grouped attributes directly and does not adapt flat fields.

### Required and optional groups

Every group is required as a class attribute. `SHIFT_RULES`,
`GAP_BETWEEN_SHIFTS_RULE`, `ORDINARY_HOUR_PENALTIES`, and `TOP_UP_RULES` may
be empty dictionaries when that family of rules is not used. In practice,
`SHIFT_RULES` will normally retain `default_break_hours` and
`minimum_paid_shift_hours`.

Use an empty dictionary to disable an optional family:

```python
SHIFT_RULES = {}
GAP_BETWEEN_SHIFTS_RULE = {}
ORDINARY_HOUR_PENALTIES = {}
TOP_UP_RULES = {}
```

Do not use `None` in place of a group. The calculator expects dictionaries.
Within a configured rule, prefer the explicit disabling values documented
below rather than an empty partial record.

## Editable custom configurations

The built-in award modules are immutable at runtime. To edit a ruleset in the
application, open **Edit rule configuration**, change the guided fields or
Advanced Python, and save. Saving a built-in creates a new custom copy; saving
an existing custom configuration replaces that custom copy after validation.

Custom configurations are identified as `custom:<award_key>:<slug>`, for
example `custom:fast_food:late-shift-review`. Built-ins use
`builtin:<award_key>`. The API exposes the configuration workflow:

```text
GET  /rule-configurations
GET  /rule-configurations/{id}
POST /rule-configurations/validate
POST /rule-configurations
PUT  /rule-configurations/{id}
```

`POST` creates a custom configuration with `base_award`, `name`, `source`, and
optionally `questionnaire`; `PUT` accepts `source` and optionally
`questionnaire`. The source must parse as Python, define the award's expected
top-level class, and assign all seven grouped attributes. Its detailed values
are then consumed by the calculator, so use this document as the authoring
contract and validate representative calculations before publishing a change.

The source validator checks file size, Python syntax, the expected top-level
class name, and the presence of direct assignments for the seven attributes.
It does not prove that those assignments are dictionaries or validate every
nested key, type, rate, or interaction described in this contract. Guided
questionnaire validation covers only the fields represented by that editor.
Advanced Python is executed only when the custom configuration is loaded for a
calculation, and malformed nested values can therefore fail or miscalculate at
that later stage.

To calculate with a saved configuration, pass its ID as `rule_configuration`
in `POST /calculate`. The configuration's award must match the request's
`award`; otherwise the API rejects the request. The bulk employee-master CSV
has the same `rule_configuration` column and forwards its value unchanged to
each calculation.

Custom files are stored in `backend/custom_rules` by default, or in the
directory specified by `PAYCHECKER_CUSTOM_RULES_DIR`. A deployment must use
persistent storage for that directory if custom edits must survive restarts or
redeployments. Custom rules execute as trusted Python code; do not expose the
write endpoints to untrusted users.

## Complete minimal example

This is a valid starting point with a daily and weekly OT limit and no
penalties, gap rule, minimum engagement, or top-up.

```python
class ExampleRules:
    SHIFT_RULES = {
        "default_break_hours": 0.5,
        "minimum_paid_shift_hours": {},
    }

    ORDINARY_TIME_RULES = {
        "span_overtime": {},
        "daily": {"variation": "default", "default": 8},
        "period": {
            "variation": "default",
            "default": 38,
            "basis": "weekly",
            "part_time_uses_contracted_hours": False,
        },
    }

    DAY_TREATMENT_RULES = {
        "Saturday": {
            "day": {"base_classification": "ordinary", "ordinary_loading": 0,
                    "overtime_rate_key": "saturday"},
            "shift": {"base_classification": "ordinary", "ordinary_loading": 0,
                      "overtime_rate_key": "saturday"},
        },
        "Sunday": {
            "day": {"base_classification": "ordinary", "ordinary_loading": 0,
                    "overtime_rate_key": "sunday"},
            "shift": {"base_classification": "ordinary", "ordinary_loading": 0,
                      "overtime_rate_key": "sunday"},
        },
    }

    PAY_RATES = {
        "overtime": {
            "weekday": {"multiplier": 1.5},
            "saturday": {"multiplier": 1.5},
            "sunday": {"multiplier": 2.0},
            "extended": {"multiplier": 2.0},
            "two_tier": {"enabled": False, "threshold": 0, "days": []},
        }
    }

    GAP_BETWEEN_SHIFTS_RULE = {}
    ORDINARY_HOUR_PENALTIES = {}
    TOP_UP_RULES = {"part_time": False, "full_time": False}
```

## `SHIFT_RULES`

```python
SHIFT_RULES = {
    "default_break_hours": 0.5,
    "minimum_paid_shift_hours": {
        "variation": "employment_type",
        "full_time": 4,
        "part_time": 3,
        "casual": 3,
    },
}
```

- `default_break_hours` is used when a request sends `break_duration: null`.
  Merely omitting `break_duration` does not select the ruleset value: the API
  request model currently inserts `0.5` before the calculator sees the shift.
- `minimum_paid_shift_hours` extends a shorter attendance period to its paid
  minimum before other rules run. It applies separately to every attendance
  segment. Use `{}` to disable it.
- The current minimum-engagement evaluator supports an employment-type map:
  `variation: "employment_type"` with `full_time`, `part_time`, and `casual`
  keys. A zero value disables the minimum for that type. It also accepts a
  legacy unlabelled map keyed directly by employment type or worker type.
  Do not use `variation: "default"` or `"worker_type"` in a new grouped
  minimum-engagement record; unlike daily and period limits, those variations
  are not interpreted by the current evaluator.

### Multiple attendance segments

Segments with the same `week` and `day` are one logical workday. The calculator
sums their actual paid durations, applies span overtime to each segment, and
applies the daily limit to their combined hours. It rejects overlapping input
segments. Whole-shift penalty triggers and the gap rule use the logical day's
earliest start and latest finish; time-based penalties use only the actual
segments and do not include gaps between them.

`minimum_engagement_exempt: true` is an accepted per-segment request field. It
bypasses minimum-engagement expansion for that segment and is used by the
frontend when a single rostered shift is divided around a specifically timed
unpaid lunch. Without it, every segment is independently expanded to the
configured minimum. If minimum-engagement expansion itself makes two segments
overlap, the current calculator merges the expanded periods rather than raising
the normal overlap error.

Important current limitation: the `long_day` exception is evaluated for a
single-segment workday, but the split-workday calculation path uses the normal
daily limit and does not apply `long_day`.

## `ORDINARY_TIME_RULES`

### Span overtime

Span OT applies to `day` workers only. Each window has optional `start` and
`end` cut-offs: time before `start` and after `end` is overtime.

```python
"span_overtime": {
    "day": {
        "default": {"start": 6, "end": 18, "enabled": True},
        "Saturday": {"start": 7, "end": 12, "enabled": True},
        "Sunday": {"enabled": False},
    }
}
```

- The day-specific record overrides `default` for the shift's entered `day`.
  An overnight shift keeps the start day's span window after midnight.
- Omit `start` to disable before-span OT; omit `end` to disable after-span OT.
- Set `enabled: False` to disable span OT for that day.
- Use `"span_overtime": {}` to disable span OT entirely.

### Daily limits and the long-day exception

```python
"daily": {
    "variation": "employment_type",
    "full_time": 8,
    "part_time": 7.6,
    "casual": 8,
},
"long_day": {"uses_per_week": 1, "ordinary_limit_hours": 10},
```

Every limit record has exactly one variation method:

```python
{"variation": "default", "default": 8}
{"variation": "worker_type", "day": 8, "shift": 10}
{"variation": "employment_type", "full_time": 8, "part_time": 7.6, "casual": 8}
```

`long_day` is optional. Any positive `uses_per_week` value lets the first
single-segment workday in each week whose ordinary hours exceed the standard
daily limit use `ordinary_limit_hours` instead. The current implementation
tracks only used/not-used per week, so values greater than `1` do not grant
additional long days. Omit `long_day` or use `{"uses_per_week": 0}` to disable
it.

### Period hours and maximum worked days

```python
"period": {
    "variation": "employment_type",
    "full_time": 76,
    "part_time": 38,
    "casual": 38,
    "basis": {
        "full_time": "pay_period",
        "part_time": "weekly",
        "casual": "weekly",
    },
    "max_work_days": 10,
    "max_work_days_basis": "pay_period",
    "part_time_uses_contracted_hours": False,
},
```

- The hours threshold uses the same `variation` forms as `daily`.
- `basis` is either `"weekly"`/`"pay_period"` for every employee, or an
  employment-type map when `variation` is `"employment_type"`.
- A weekly limit is enforced independently in each week. A pay-period limit
  is one threshold across both weeks; do not supply a weekly number and
  expect it to be multiplied automatically.
- `max_work_days` is optional. Later worked days in its group have their
  remaining ordinary hours converted to overtime. Set it to `None` or omit it
  to disable the days cap.
- `max_work_days_basis` is `"weekly"` or `"pay_period"`. It defaults to
  weekly when omitted, so set it explicitly when a weekly hour limit is paired
  with a fortnight-wide days cap.
- `part_time_uses_contracted_hours: True` replaces a part-time threshold with
  the request's `contracted_hours` value. It does not affect full-time or
  casual thresholds. With a weekly basis this value is enforced separately in
  each week. With a `pay_period` basis, the current calculator uses the value
  as the entire fortnight threshold; it does not multiply the contracted
  weekly value by two.
- Workdays marked `manual_ordinary` are excluded from both the period-hours
  calculation and the eligible-day sequence used by `max_work_days`. They do
  not consume the configured days cap.

`ordinary_rates.casual_loading` is an optional ordinary-hours loading. It is
used only for casual ordinary hours that have no other ordinary-hours loading:

```python
"ordinary_rates": {"casual_loading": 0.25}
```

For whole-workday loadings, any selected day-treatment, shift-based, or gap
loading suppresses the casual ordinary loading across all ordinary hours. For
time-based loadings, the calculator subtracts the sum of their reported hours
from casual-loading hours. It does not form a union first, so overlapping
time-based penalties can subtract the same ordinary hour more than once.

## `DAY_TREATMENT_RULES`

Define Saturday and Sunday for both worker types. Add `public_holiday` when
the award supports manually selected public holidays.

```python
DAY_TREATMENT_RULES = {
    "Saturday": {
        "day": {"base_classification": "overtime", "ordinary_loading": 0,
                "overtime_rate_key": "saturday"},
        "shift": {"base_classification": "ordinary", "ordinary_loading": 0.5,
                  "casual_rate": 0.65, "overtime_rate_key": "saturday"},
    },
    "Sunday": {...},
    "public_holiday": {
        "day": {"base_classification": "overtime", "ordinary_loading": 0,
                "overtime_rate_key": "public_holiday"},
        "shift": {"base_classification": "ordinary", "ordinary_loading": 1.5,
                  "casual_rate": 1.5, "overtime_rate_key": "public_holiday"},
    },
}
```

For each worker record:

- `base_classification` is `"ordinary"` or `"overtime"`.
- `ordinary_loading` is an additional loading on ordinary hours.
- `casual_rate`, when present, replaces `ordinary_loading` for casuals.
- `overtime_rate_key` selects an entry in `PAY_RATES["overtime"]` for overtime
  on that day. It is also used when a day initially classified as ordinary is
  later converted by daily, maximum-days, or period overtime.

Public holidays have two request forms:

```json
{
  "public_holidays": [{"week": 1, "day": "Monday"}],
  "shifts": [
    {"week": 1, "day": "Tuesday", "start": 9, "end": 13,
     "public_holiday": true}
  ]
}
```

- A top-level `public_holidays` entry selects the entire logical workday. The
  calculator rejects that request if the ruleset has no `public_holiday`
  treatment. Whole-day public-holiday treatment replaces the normal
  weekday/weekend and custom penalty treatment.
- `public_holiday: true` on a shift selects one attendance segment. If every
  segment in the logical workday is flagged, the whole day receives the
  public-holiday treatment.
- If only some segments are flagged, the workday's ordinary/overtime
  classification is calculated without making the whole workday a public
  holiday. Flagged segments receive the public-holiday `ordinary_loading` (or
  `casual_rate`) as a time-based loading, and their custom time-based penalties
  are suppressed. The initial holiday candidate is the segment's paid hours
  multiplied by the workday's post-span/post-daily ordinary proportion. During
  finalisation, the calculator also subtracts the workday's preallocated
  overtime from each hourly penalty record and removes later period overtime
  from the latest records. Upstream calculations should reproduce that
  allocation literally; it is not always a simple proportional share of final
  ordinary hours.
- In that mixed-segment path, `base_classification: "overtime"` does not turn
  only the flagged segment into overtime. The ordinary loading is the only
  segment-level public-holiday value applied. Normal day-treatment loading for
  the logical workday is not removed, so it may coexist with the segment-level
  public-holiday loading.
- Current validation limitation: a per-segment `public_holiday: true` does not
  trigger the missing-treatment error used by the top-level list. Ruleset
  authors and upstream callers must therefore ensure `public_holiday` exists
  before using segment flags.

For an overnight attendance, the logical workday and overtime rate key remain
those of the entered start day. Ordinary weekend/day-treatment loadings and
time-based penalty `days`, however, are evaluated against the actual calendar
day on each side of midnight.

## `PAY_RATES`

```python
PAY_RATES = {
    "overtime": {
        "weekday": {"multiplier": 1.5, "casual": 1.75},
        "saturday": {"multiplier": 2.0, "casual": 2.25},
        "sunday": {"multiplier": 2.0, "casual": 2.25},
        "public_holiday": {"multiplier": 2.5, "casual": 2.5},
        "extended": {"multiplier": 2.0, "casual": 2.25},
        "two_tier": {
            "enabled": True,
            "threshold": 2,
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        },
    }
}
```

- `weekday`, `saturday`, and `sunday` are the standard day-based fallbacks and
  should be supplied. `extended` is required when two-tier overtime is enabled.
- `public_holiday` should be supplied when a public-holiday treatment can
  classify hours as overtime. If a selected named key is absent, the calculator
  delegates to its standard day/tier rate selector; this is a fallback, not a
  substitute for defining the intended profile.
- `manual_overtime` is a request classification, not a rate key. It uses the
  selected calendar-day treatment's `overtime_rate_key`, or the public-holiday
  treatment's key when the whole workday is a public holiday. Existing built-in
  classes still contain a `manual` entry for historical reasons, but the live
  calculator does not select `PAY_RATES["overtime"]["manual"]`.
- `casual` is a total casual OT multiplier; it does not stack with the casual
  ordinary loading.
- With `two_tier.enabled: True`, OT on listed `days` is split at `threshold`.
  First-tier OT uses the workday's selected rate key; later OT uses `extended`.
  Overtime is excluded from two-tier splitting when its selected rate key is
  exactly `public_holiday`. Use
  `{"enabled": False, "threshold": 0, "days": []}` to disable it.

## `ORDINARY_HOUR_PENALTIES`

Use a dictionary keyed by a stable code name. `days` lets every penalty define
its own calendar-day scope, such as Monday–Friday or Monday–Saturday.

```python
ORDINARY_HOUR_PENALTIES = {
    "late_shift": {
        "type": "shift_based",
        "basis": "start",
        "start": 18,
        "end": 24,
        "rate": 0.15,
        "casual_rate": 0.25,
        "description": "Late shift loading",
        "applies_to": ["shift"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    },
    "night_hours": {
        "type": "time_based",
        "basis": "time",
        "start": 22,
        "end": 6,
        "rate": 0.2,
        "description": "Night-hours loading",
        "applies_to": ["day", "shift"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    },
}
```

Common fields:

- `type`: `"shift_based"` or `"time_based"`.
- `rate`: ordinary-hours loading; `casual_rate` optionally replaces it for
  casual employees.
- `description`: user-facing applied-rule text.
- `applies_to`: a non-empty list containing `day`, `shift`, or both.
- `days`: optional explicit day list. If omitted, the rule is weekday-style
  and is skipped on Saturday and Sunday.

For `shift_based`, `basis` is `start`, `end`, `duration`, or `start_and_end`.
If `basis` is absent, the calculator accepts the legacy `match_on` alias and
otherwise defaults to `start`; new rulesets should write `basis` explicitly.
`start`/`end` define the trigger range. A `duration` basis uses `duration` or
`min_duration` as an optional minimum override and `duration_end` or
`max_duration` as an optional maximum override; otherwise it uses `start` and
`end` as the minimum-inclusive and maximum-exclusive duration bounds.
`start_and_end` additionally requires `finish_start` and `finish_end`. If more
than one `shift_based` rule matches, each new match overwrites the previous
whole-shift penalty, so only the last matching dictionary entry is paid.

For `time_based`, use `basis: "time"`; `start` and `end` are the payable
window and may cross midnight. The engine calculates attendance-window
overlap. Its `days` filter uses the actual calendar day of each overlap,
including after midnight. Multiple matching time-based rules remain separate
and are additive.

For a split attendance with a specifically timed break, time-based penalties
exclude the gap. For a single continuous attendance with only a numeric
`break_duration`, the engine does not know where the break occurred and does
not subtract it from or otherwise cap a configured time-based penalty window.
Consequently, reported time-based penalty hours can exceed paid ordinary hours
when an untimed break lies inside the window. Ordinary day-treatment loading on
an overnight shift apportions an untimed break across the calendar-day segments
instead.

Use `{}` to disable all custom ordinary-hour penalties. Whole-day
public-holiday treatment suppresses them, segment-level public-holiday status
suppresses them for that segment, and a gap-between-shifts loading suppresses
them for the affected logical workday.

## `GAP_BETWEEN_SHIFTS_RULE`

```python
GAP_BETWEEN_SHIFTS_RULE = {
    "minimum_hours": 10,
    "loading": 1.0,
    "casual_rate": 1.0,
}
```

When the gap before a shift is below `minimum_hours`, the current shift's
final ordinary hours receive `loading`. `casual_rate` optionally replaces it
for casual employees. The gap loading has priority: it suppresses normal
day-treatment loading, public-holiday loading, shift-based penalties, and
time-based penalties on that logical workday. Overtime hours never receive the
gap loading. Use `{}` or a missing/zero `minimum_hours` to disable this rule.

The rule is evaluated once per logical workday, from the preceding processed
workday's latest finish to the current workday's earliest start. The current
gap calculation uses weekday names and clock times but not the `week` number.
In particular, two worked days with the same weekday name in different request
weeks are treated by the same-day clock calculation rather than as seven days
apart. Upstream users must not rely on the gap rule for that shape without
separate validation.

## `TOP_UP_RULES`

```python
TOP_UP_RULES = {"part_time": True, "full_time": False}
```

When enabled and contracted hours are supplied, the calculator adds ordinary
top-up hours if total worked hours fall below the contracted fortnight target.
Overtime counts as worked time and does not itself create top-up.

## Manual request overrides

These are request fields, not ruleset fields:

```json
{
  "day": "Sunday",
  "week": 1,
  "start": 9,
  "end": 17,
  "break_duration": 0.5,
  "manual_overtime": false,
  "manual_ordinary": true
}
```

- `manual_overtime: true` hard-codes the logical workday as overtime. It does
  not select a `manual` pay-rate entry: the overtime rate comes from the
  applicable start-day or whole-day public-holiday `overtime_rate_key`, and
  configured two-tier splitting can still apply.
- `manual_ordinary: true` hard-codes it as ordinary and bypasses span, daily,
  period, weekend, and public-holiday OT classification. Ordinary penalties
  can still apply. On a selected public holiday, the configured public-holiday
  ordinary loading can therefore still apply even though public-holiday
  overtime classification is bypassed.
- On a workday with multiple segments, `true` on any segment sets that manual
  classification for the entire logical workday.
- The UI makes the two controls mutually exclusive, but the API model does not
  reject a shift that sets both to `true`. In that invalid combination,
  `manual_ordinary` wins because it is evaluated first. API callers should keep
  the controls mutually exclusive rather than depend on that precedence.

## Calculation order

For each logical workday, the calculator:

1. Groups attendance segments by `week` and `day`, expands applicable minimum
   engagements, validates/merges overlaps as described above, and calculates
   paid attendance after breaks.
2. Applies logical-workday manual ordinary or manual overtime classification.
   Without a manual classification, it applies whole-day public-holiday and
   weekend base classification, then span and daily overtime. The `long_day`
   exception is available only on the single-segment path.
3. Selects the workday's overtime rate key and assesses gap, day-treatment,
   shift-based, time-based, and segment-level public-holiday loading
   eligibility. Gap and public-holiday suppression rules apply at this stage.
4. After all workdays are processed, applies maximum-worked-days overtime and
   then period-hours overtime. Later eligible days are converted first; within
   time-based penalty details, the latest listed eligible hours are removed
   first as ordinary hours become overtime. At finalisation, each time-based
   penalty record also has the workday's already allocated span/daily/manual
   overtime subtracted independently.
5. Finalises every ordinary-only loading against the remaining ordinary hours
   and applies the casual ordinary loading only to ordinary hours without an
   already selected loading.
6. Adds any contracted-hours top-up and calculates workday and period pay.

The result reports ordinary, overtime, top-up, and each penalty component
separately. Penalty pay is additional to base ordinary pay; it is never added
to an overtime hour.

## Unsupported legacy shapes

Flat fields such as `WEEKLY_OVERTIME_CONFIGURATION`, `WEEKEND_RULES`,
`PENALTIES`, and `STANDARD_OVERTIME_RATE` are not part of the live ruleset
contract. A custom configuration that provides only those fields fails
validation because it does not assign the seven required grouped attributes.
Migrate the full class to the grouped contract before saving or calculating
with it.
