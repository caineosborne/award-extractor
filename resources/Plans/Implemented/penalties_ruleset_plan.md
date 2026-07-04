# Penalties Ruleset Plan

## Summary

Add `penalties` as a third active ruleset running parallel to:
- `overtime_creation`
- `overtime_consequence`
- `penalties`

This ruleset combines both:
- `Penalty`
- `Breaks (Between Work Periods)`

Steps `1` and `2.1` remain unchanged. Step `2.2` becomes a deterministic shortlist builder for penalties. Steps `3.1`, `3.2`, `4.1`, and `5.1` continue through the normal CLI ruleset flow with penalties-specific prompts and outputs.

Current sequencing note:
- penalties CLI support is being completed before any Streamlit review-surface changes
- Streamlit penalties support is intentionally deferred to `Phase 5`

Terminology note:
- `Phase 1`, `Phase 2`, and `Phase 3` in this document refer to implementation phases of this penalties project.
- `2.2`, `3.1`, `3.2`, `4.1`, and `5.1` refer to pipeline step numbers in the codebase.
- The main completed implementation in this document is `Phase 2`, which changes pipeline step `2.2`.

The current agreed scope includes:
- shift allowances and shift penalties, often limited to shift workers
- penalties based on shift commencement
- penalties that apply to an entire qualifying shift
- penalties that apply only to specific hours worked
- weekend and public holiday penalties
- `Breaks (Between Work Periods)` clauses, including clauses with no direct financial entitlement

## Phase 1

Status:
- Completed

Phase 1 was to write and store the monitored penalties plan and lock the agreed business boundary.

Completed outcomes:
- create a dedicated monitored plan doc
- confirm that `penalties` is a third ruleset running parallel to:
  - `overtime_creation`
  - `overtime_consequence`
- confirm that the penalties subset combines:
  - `Penalty`
  - `Breaks (Between Work Periods)`
- confirm that no-entitlement break-gap clauses should still remain in the penalties subset as supporting operational rules

## Phase 2

Status:
- Completed

Phase 2 is the implementation phase that changes pipeline step `2.2`.

Pipeline step `2.2` for penalties should not call an LLM.

Selection behavior:
- include all clauses tagged `Penalty`
- include all clauses tagged `Breaks (Between Work Periods)`
- keep no-entitlement break-gap clauses in the penalties subset as supporting operational rules

The pipeline step `2.2` artifact is therefore a deterministic combined shortlist, not a final entitlement-only filter.

Recommended artifact defaults:
- `classification="Penalty Rule"`
- `classifications=["Penalty Rule"]`
- `employee_cohort="all"` unless the clause explicitly names a cohort
- `work_arrangement="all"` unless the clause explicitly narrows to day worker or shiftworker
- `other_scope_notes=""`

Deterministic scope tagging should stay conservative:
- explicit text can set `full-time`, `part-time`, `casual`, `permanent`, `shiftworker`, or `day-worker`
- otherwise default to `all`
- final business interpretation remains a later-step responsibility

Phase 2 completed outcomes:
- pipeline step `2.2` can now run for the `penalties` ruleset without an LLM
- pipeline step `2.2` writes a penalties-specific clause-classification artifact
- penalties subset identity and canonical penalties filenames are in place
- deterministic employee cohort and work-arrangement tagging is conservative and explicit-only
- CLI subset `3` now maps to `penalties` for step `2.2` runs

Phase 2 concerns / limitations:
- deterministic employee cohort tagging is intentionally conservative and only works for explicit wording
- deterministic work-arrangement tagging is intentionally conservative and only works for explicit wording such as `shiftworker` or `day worker`
- the penalties subset is now selectable for pipeline step `2.2`, but later phases are not yet penalties-ready end to end

## Phase 3

Status:
- Completed for CLI scope

Phase 3 is the downstream penalties-ruleset CLI work after pipeline step `2.2`.

The reusable penalties prompt should explicitly say:
- penalties includes anything other than overtime that can increase pay for worked hours
- this includes shift allowances, shift penalties, weekend penalties, public holiday penalties, afternoon penalties, evening penalties, night penalties, and similar higher-paid time-based rules
- this also includes break-between-work-period clauses, even where they do not create a direct financial entitlement, because those clauses may still define operational rules relevant to the penalties domain
- some rules qualify by shift commencement
- some rules apply to the whole shift once qualified
- some rules apply only to specific hours worked
- some break-gap rules create premium pay outcomes
- some break-gap rules create no financial entitlement and should be retained as supporting context, not forced into a premium-pay rule

Examples to preserve in the common prompt:
- an afternoon or night shift allowance may depend on when the shift commences
- once a shift qualifies, the allowance may apply to the entire shift
- a table-based penalty may instead apply only to the specific hours worked during a period such as 7.00 pm to midnight, midnight to 7.00 am, Saturday, Sunday, or public holiday
- a break-between-work-period rule may require 10 hours off duty, allow reduction by agreement, and then pay 200% until release if the employee resumes without the required break
- a minimum-break rule with no entitlement should still be captured in the subset as a supporting rule

## Phase 3 Downstream Expectations

Step `3.1` penalties drafting should support both:
- direct premium-pay rules
- supporting break-gap operational rules that do not themselves change pay

The ruleset must preserve the difference between:
- shift-commencement rules
- whole-shift qualification rules
- specific-hours or day-type rules
- break-gap premium rules
- break-gap supporting rules with no financial outcome

Phase 3 completed outcomes:
- penalties now has a dedicated reusable question block and ruleset-aware shared prompt framing
- step `3.1` now has a penalties-specific drafting variant
- step `3.1` merge instructions now preserve:
  - whole-shift versus specific-hours rules
  - shift-commencement versus actual-hours qualification rules
  - supporting break-gap rules without inventing premium outcomes
- step `3.2` now has a penalties-specific review overlay and subset scope notes
- step `4.1` now has a penalties formatter variant with penalties-specific headings
- step `5.1` now has a penalties pseudocode variant with penalties-oriented outputs and required-input guidance
- targeted CLI prompt tests now cover penalties drafting, review config, formatter behavior, and pseudocode mode

Phase 3 remaining concerns / limitations:
- penalties support has been implemented for the CLI prompt and ruleset layers, but has not yet been validated through a full live award run in this phase
- Streamlit penalties selection and artifact loading are intentionally not part of Phase 3 anymore
- some internal naming still uses legacy `overtime` module names even where the prompt behavior is now ruleset-aware

## Phase 4

Status:
- Completed

Phase 4 was used for live CLI hardening after the Phase 3 implementation work.

Phase 4 completed outcomes:
- completed a full live penalties CLI run for `MA000018` through:
  - step `2.2`
  - step `3.1`
  - step `3.2`
  - step `4.1`
  - step `5.1`
- confirmed that penalties artifacts now run end to end through the CLI
- fixed penalties canonical path handling in the deterministic step `4.1` and step `5.1` helpers
- fixed the missing `penalties` branch in the reconstructed step `2.2` prompt context used by step `3.2`
- confirmed that the step `5.1` repair loop also works for penalties outputs

Phase 4 findings:
- the main remaining issue is not missing CLI wiring
- the main remaining issue is content quality within the penalties subset, especially overtime drift in mixed clauses
- `MA000018` showed that the penalties ruleset can still retain overtime-heavy rules that are technically present in mixed clauses but may be broader than the intended penalties subset
- this is now a refinement and scoping-quality issue, not a missing implementation issue for steps `3.1` to `5.1`

Phase 4 notes:
- `MA000120` was intentionally not used as the main validation case because it is lower-value for penalties validation
- the interrupted `MA000120` run had already progressed into the step `3.1` merge stage before being stopped, so no additional local penalties-path failure was identified from that run

## Phase 5

Status:
- Completed

Phase 5 was the deferred review-surface rollout for penalties.

Phase 5 completed outcomes:
- added `penalties` to the Streamlit ruleset selector
- enabled penalties artifact discovery and loading in the Streamlit review surface
- enabled penalties ruleset support in `ruleset_artifact_paths_for_award`
- confirmed penalties manual-ruleset editor source selection works with canonical penalties artifacts
- confirmed penalties pseudocode source selection works with canonical penalties artifacts
- added focused Streamlit tests for penalties selector visibility, penalties artifact paths, and penalties source-path helper behavior

Phase 5 notes:
- Streamlit penalties support is now implemented in code and covered by focused tests
- manual browser/UI smoke testing can still be useful, but it is no longer blocked by missing Streamlit penalties wiring
