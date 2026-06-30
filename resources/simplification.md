# Simplification Plan

## Summary

This note records the agreed simplification direction for the active ruleset pipeline.

The intended active model is now:

- ruleset-native execution
- separate `overtime_creation` and `overtime_consequence` streams
- shared downstream plumbing that stays separate by ruleset all the way through formatting and pseudocode

The old overtime-only flow should no longer remain a first-class active path across the codebase.

The only compatibility behaviour worth keeping is the recent split of overtime into:

- `overtime_creation`
- `overtime_consequence`

Everything else should be simplified toward the current production ruleset model.

## Agreed direction

### 1. Remove legacy overtime-only active behaviour

We should stop carrying legacy overtime-only execution as a first-class path through:

- Streamlit
- background pipeline runs
- output loading
- downstream formatting
- downstream pseudocode generation

Active execution should assume ruleset-native artifacts and ruleset-native sequencing.

If any old command still needs to exist temporarily, it should be a very thin shim only. It should map into the current ruleset-native flow rather than preserving a separate implementation path.

### 2. Keep the creation/consequence split

The overtime split is the important structural change that should remain:

- `overtime_creation` covers when time becomes overtime
- `overtime_consequence` covers the result once time is already overtime

These streams should remain separate through:

- clause classification
- expert A draft
- expert B draft
- comparison
- reviewed ruleset
- formatted ruleset
- pseudocode

There should be no reintroduction of a merged active overtime-only branch in these stages.

### 3. Simplify around ruleset-native context

The active code should build one ruleset-aware context early and pass it through the pipeline.

That context should deterministically provide:

- award code
- ruleset key
- source classification path
- clause-classification artifact paths
- draft and merged ruleset paths
- review artifact paths
- formatted output paths
- pseudocode output paths

This avoids repeated path inference, repeated filename branching, and repeated checks for legacy artifact names.

### 4. Separate deterministic plumbing from LLM work

We should separate the code by responsibility, but not explode the number of top-level scripts.

Recommended split:

- deterministic layer
  - ruleset config
  - artifact path resolution
  - source selection
  - output naming
  - archive handling
  - run sequencing
- LLM layer
  - clause-classification prompts
  - ruleset drafting prompts
  - review prompts
  - formatting prompts
  - pseudocode prompts

The operator-facing scripts can stay in place, but they should mainly:

- load inputs
- resolve deterministic context
- call prompt builders
- write outputs

They should not own duplicated path logic or prompt-like embedded workflow text.

## Main simplification targets

### Script and artifact traceability

We should make it easy for a reviewer to answer:

- which script generated this file
- which pipeline step it belongs to
- which files are intermediate versus review versus downstream outputs

The current codebase already uses step labels in docs and Streamlit, but the processed filenames are not consistently step-aligned.

As part of simplification, active artifacts should adopt a step-aligned naming convention that matches the public script entrypoint rather than older internal helper history.

Recommended direction:

- step `1` outputs start with `step1_`
- step `2` outputs start with `step2_`
- step `3` ruleset-generation outputs start with `step3_`
- step `3B` review outputs start with `step3b_`
- step `4A` formatted outputs start with `step4a_`
- step `5B` pseudocode and validation outputs start with `step5b_`

Example direction for active ruleset-native files:

- `MA000120_step2_payment_classification.json`
- `MA000120_step3_overtime_creation_clause_classification.json`
- `MA000120_step3_overtime_creation_ruleset.md`
- `MA000120_step3b_overtime_creation_ruleset_revised.md`
- `MA000120_step4a_overtime_creation_formatted_ruleset.md`
- `MA000120_step5b_overtime_creation_pseudocode.md`

The important principle is:

- one active step prefix per public script
- one ruleset key where applicable
- one short artifact descriptor

This should replace older mixed naming that reflects historical helper structure more than the current active workflow.

### Public script alignment

If we simplify to current production behaviour, artifact naming should align to the scripts users actually run, not to internal split helpers.

That means:

- if `script_3_generate_overtime_ruleset.py` is the public active step, its outputs should be marked as step `3`
- if `script_3b_review_overtime_interpretation.py` is the public active review step, its outputs should be marked as step `3b`
- downstream outputs should likewise align to `4a` and `5b`

We should avoid naming active outputs around older internal distinctions like “part 1” and “part 2” unless those remain public operator concepts.

### Streamlit

Simplify Streamlit so it only uses the active ruleset-native model for current runs and current artifact review.

This means:

- selected ruleset drives all step `3`, `3B`, `4A`, and `5B` actions
- active review screens read ruleset-native artifacts
- legacy fallback branches are removed from active review surfaces where they are no longer needed

### Pipeline execution

Simplify the active pipeline so one run model exists for current behaviour:

- shared upstream steps where appropriate
- selected ruleset for ruleset-specific downstream steps

Avoid carrying both:

- legacy overtime-only execution
- current ruleset-native execution

as equal active paths.

### Artifact path logic

Reduce repeated filename branching spread across:

- output helpers
- Streamlit output discovery
- step `4A`
- step `5B`
- review helpers

There should be one clear deterministic source of truth for current artifact naming.

## Suggested implementation order

### Phase 1

Remove legacy-first assumptions from active Streamlit and pipeline orchestration while preserving only thin command compatibility where necessary.

### Phase 2

Consolidate ruleset artifact path resolution into one deterministic layer and remove repeated legacy-vs-ruleset branching from downstream steps.

At the same time, define one canonical active filename convention based on:

- award code
- step prefix
- ruleset key where needed
- artifact descriptor

and migrate the active path helpers and docs to that convention.

### Phase 3

Tighten the step scripts so they mainly orchestrate deterministic helpers plus prompt builders, instead of carrying mixed responsibilities.

## Testing expectations

When simplification work starts, tests should be updated to prove:

- active runs use ruleset-native artifacts
- `overtime_creation` and `overtime_consequence` remain separate through downstream outputs
- Streamlit reflects the selected ruleset consistently
- any retained compatibility wrapper maps cleanly into the current ruleset-native path
- old legacy overtime-only logic is no longer the default active path

## Current decision

The current decision is:

- keep the overtime creation/consequence split
- simplify everything else toward the current production ruleset model
- do not preserve broad legacy overtime-only behaviour as an equal active implementation
