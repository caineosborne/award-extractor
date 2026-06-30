# Outstanding Pieces

This document records the current known gaps that still deserve follow-up in the active pipeline.

It has been reviewed against the current codebase after the recent Step `3B` contract, validation, and documentation updates.

## Resolved items

These earlier items are no longer outstanding in their original form.

### Step 3 completeness validation gap between 3.2 and 3.4

Status:
- Resolved as warning-based validation

Current state:
- `src/script_3_part2_generate_overtime_interpretation.py` now records warning-level completeness issues when shortlisted overtime-creation clauses from step `3.2` are not represented in:
  - the expert rulesets; and
  - the merged comparison ruleset.
- The same warning path is carried into the saved step-3 artifacts and prepended to the markdown working paper.

What changed:
- step `3.4` still does not hard-fail on every omission;
- but it no longer leaves the omission silent.

Why it is no longer listed as an active gap:
- the original concern was silent omission;
- current behaviour surfaces that omission deterministically for review.

### Processed output layout should be award-first

Status:
- Resolved

Current state:
- active outputs are now grouped under award-first folders such as:
  - `data/processed/MA000120/`
- feedback and archive artifacts are stored with the relevant award output set.
- Streamlit artifact discovery and path helpers have been updated to use the award-first layout.

### Step 3 cohort and work-arrangement tagging may be needed

Status:
- Resolved

Current state:
- step `3.2` now records:
  - `employee_cohort`
  - `work_arrangement`
  - `other_scope_notes`
- step `3.4` validates generated rule scope against the clause-classification scope and emits warnings when scope drifts.
- `work_arrangement` is also deterministically normalised back to `all` unless the clause text expressly supports a narrower arrangement.

Why it is no longer listed as active:
- the earlier gap was absence of explicit upstream scope tagging;
- that tagging and downstream comparison now exist.

### Step 3B creator over-inferred evaluator-proposed new rules from evaluator prose

Status:
- Resolved as prompt-contract hardening

Current state:
- the direct step `3B` creator flow now treats evaluator structured JSON as the authoritative operational contract;
- the creator prompt includes a structured review action pack built from:
  - the original step-3 rules JSON; and
  - the evaluator structured review JSON;
- evaluator markdown remains present as explanation, but is no longer intended to authorise extra creator-side adds, removals, merges, or splits.

What changed:
- relevant clause excerpts are now selected from structured evaluator review data first;
- creator instructions explicitly say not to infer extra change actions from evaluator prose unless those actions are reflected in the structured review contract.

Why it is no longer listed as active:
- the earlier issue was that evaluator prose had too much practical authority in the creator prompt;
- the current direct `3B` path now gives the structured review JSON priority.

## Active issues

### Step 3B evaluator occasionally returns empty or truncated structured output in live runs

Status:
- Open

Area:
- `src/script_3b_review_overtime_interpretation.py`
- `src/common/llm_io.py`

Current behaviour:
- evaluator calls now retry on:
  - empty response text;
  - invalid structured JSON;
  - deterministic validation failure.
- evaluator output budget was increased to reduce truncation.
- this improved stability materially in live runs.

Remaining issue:
- live runs can still occasionally produce:
  - an empty evaluator response; or
  - malformed/truncated JSON that exhausts the repair loop.

Why this still matters:
- step `3B` is intended to be the main audited review path;
- unstable evaluator transport undermines repeatability even when the deterministic layer handles failures safely.

Suggested follow-up:
- inspect whether the evaluator prompt should be shortened further;
- consider splitting long evaluator summaries from the structured rule-by-rule record if output size remains unstable;
- consider increasing retry observability by saving the final failed evaluator raw payload to a dedicated exception artifact rather than only surfacing the exception message.

## Current recommendation

The active priority should be:

1. finish stabilising live step `3B` evaluator output;
2. rerun representative awards such as `MA000120` to confirm the reviewed interpretation path passes cleanly without manual-review fallback;
3. keep reviewing whether any remaining reviewer-only clarifier rules should stay in `3B` outputs or move to later presentation layers.
