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

### Step 1 output reduction

Step `1` should be simplified so the default active run only writes the core artifacts that are still needed downstream:

- raw source extract
  - HTML flow: raw HTML
  - PDF flow: raw markdown
- main parsed award JSON

These are the files we should explicitly preserve:

- `<award>.json`
- the corresponding raw extract under `raw/`

The other step `1` supporting outputs should no longer be written by default if they are not part of the active production workflow.

This includes the current supporting and diagnostic artifacts such as:

- section index JSON
- heading summary CSV
- PDF diagnostics JSON
- PDF excluded sections JSON

If any of these still need to exist for debugging or occasional manual analysis, they should move behind an explicit optional mode rather than remain part of every default run.

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

## Additional simplification suggestions

### 1. Remove legacy prompt compatibility layers

The active prompt model should be:

- one canonical prompt family for overtime clause classification
- one canonical prompt family for overtime ruleset generation, with creation/consequence variants
- one canonical review prompt family
- one canonical formatter prompt family
- one canonical pseudocode prompt family

We should avoid carrying:

- compatibility prompt modules that only proxy to the current prompt builders
- duplicate legacy creation-only prompt text
- multiple prompt entrypoints for the same active step

If an older script still needs to exist, it should call the current prompt builder directly rather than owning a second prompt API.

### 2. Remove legacy helper aliases inside active scripts

There are still several places where the code keeps older helper names for compatibility, even though the active code path already uses the newer ruleset-native implementation.

Examples of what should be reduced over time:

- wrapper helpers like `build_messages` where the active concept is now a ruleset-specific builder
- duplicate helper names such as both `build_clause_classification_messages` and `build_classification_messages`
- duplicate clause-selection helper names like `filter_*` and `select_*` where only one naming style is needed
- legacy compatibility exports kept only so older tests or scripts can import the old name

Recommended direction:

- one public helper name per active concept
- compatibility shims only where an external entrypoint truly still depends on them
- remove alias names once the calling code and tests have moved to the canonical name

### 3. Shrink or remove compatibility entrypoint scripts

Some top-level scripts now exist mainly to preserve older operator habits while delegating to the newer split implementation.

That is acceptable temporarily, but it should not remain a permanent second conceptual workflow.

Recommended direction:

- keep only the public scripts the team actually intends operators to run
- where a script is only a thin wrapper, either:
  - remove it; or
  - document clearly that it is a compatibility shim and keep its body extremely small

In practice this likely means reviewing whether scripts like:

- `src/script_3_interpret_overtime.py`

still need to remain public, or whether the current ruleset-native entrypoints are now sufficient on their own.

### 4. Remove fallback-first downstream behaviour

The current simplification direction should prefer:

- one current artifact path
- one current source selection rule
- one current ruleset-aware downstream flow

We should keep reducing patterns like:

- try legacy file A
- else try legacy file B
- else try current file C

unless the fallback exists to support a genuine short-lived migration.

Recommended direction:

- active downstream steps should read the canonical ruleset-native artifacts only
- migration support, where unavoidable, should sit in a narrow boundary layer
- Streamlit should reflect the current canonical artifact set, not act as a long-term migration engine

### 5. Simplify naming within deterministic helpers

The deterministic helper layer is improving, but it still carries a mix of:

- old overtime-only terminology
- ruleset-native terminology
- wrapper names that exist only because earlier code used them

Recommended direction:

- use `ruleset` consistently when the helper is ruleset-specific
- use `clause_classification`, `revised_ruleset`, `formatted_ruleset`, and `pseudocode` consistently as artifact descriptors
- reduce old names like `interpretation` where the active object is now clearly a ruleset artifact

This should make the code easier to explain in an audit context because the filenames, helper names, and UI labels will describe the same thing.

### 6. Reduce documentation drift from old architecture

The repo documentation still contains references to earlier prompt/script layouts and older architectural concepts.

Recommended direction:

- update docs to describe only the active ruleset-native flow
- mark any retained compatibility script explicitly as compatibility-only
- avoid documenting old internal split history unless it still matters operationally

This should especially apply to:

- technical guide material
- methodology notes
- output inventories
- simplification notes once the related work is completed

### 7. Prefer one canonical data contract per step

Where possible, each step should have:

- one canonical JSON contract
- one canonical markdown artifact
- one canonical validation/report artifact if needed

We should avoid multiple near-equivalent artifacts that represent the same business object in slightly different ways.

The current ruleset split is valid because creation and consequence are genuinely different business objects.
The rest of the duplication should be challenged.

### 8. Keep step scripts boring

The strongest simplification principle for this codebase is:

- prompt text lives in prompt modules
- deterministic naming/path rules live in helper modules
- step scripts orchestrate inputs, outputs, and model calls

Whenever a step script starts growing:

- embedded workflow prose
- duplicate prompt assembly
- repeated path inference
- repeated filename branching
- multiple compatibility code paths

that is a candidate for extraction or deletion.
