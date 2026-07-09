# Outstanding Pieces

This document records the current known gaps that still deserve follow-up in the active pipeline.

## Active items

### Version 1.1 human intervention points

Status:
- Open

What to add:
- allow user intervention at more stages than the current manual ruleset and calculator questionnaire editors;
- make edited artifacts explicit in the source-selection order for later steps;
- preserve clear evidence of which artifact was machine-generated and which artifact was human-edited.

### Version 1.1 prompt review and editing

Status:
- Open

What to add:
- surface the active system and user prompt text in the review app;
- allow a user to save reviewed prompt variants;
- make prompt version or prompt source visible in run outputs.

### Step 6.1 calculator output shape will continue changing

Status:
- Open

What to review:
- the fixed questionnaire fields;
- the generated calculator Python shape;
- the evidence fields carried from reviewed rulesets into calculator answers.

Why it matters:
- step `6.1` is the first calculator-facing contract and is expected to evolve as integration requirements become clearer.

### Make expert and review count configurable

Status:
- Open

What to add:
- allow the operator to choose the step `3.1` expert run count where the workflow supports it;
- allow the operator to choose review/repair attempt counts for LLM-backed review steps;
- keep the default path conservative and audit-friendly.

Why it matters:
- v1 uses a fixed two-expert workflow, which is clear and reviewable;
- later experimentation should not require code edits just to compare model/run-count behaviour.

### Step 3.2 evaluator occasionally returns empty or truncated structured output in live runs

Status:
- Open

Area:
- `src/step_3_2_review_ruleset/step_2_run_reviewer.py`
- `src/step_3_2_review_ruleset/run.py`
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
- step `3.2` is intended to be the main audited review path;
- unstable evaluator transport undermines repeatability even when the deterministic layer handles failures safely.

Suggested follow-up:
- inspect whether the evaluator prompt should be shortened further;
- consider splitting long evaluator summaries from the structured rule-by-rule record if output size remains unstable;
- save the final failed evaluator raw payload to a dedicated exception artifact rather than only surfacing the exception message.

### V1 smoke-test evidence

Status:
- Open

What to add:
- record a clean smoke-test run for at least one representative award through step `6.1`;
- include overtime creation, overtime consequence, and penalties in the same review record;
- note any manual interventions or reruns needed during the smoke test.

Why it matters:
- the code and docs are now v1-shaped;
- a short run record gives a reviewer confidence that the current workflow is not just unit-test green.

## Resolved items

These earlier items are no longer outstanding in their original form.

### Step 3 completeness validation gap

Status:
- Resolved as warning-based validation

Current state:
- `src/step_3_1_generate_ruleset/run.py` now records warning-level completeness issues when shortlisted clauses from step `2.2` are not represented in:
  - the expert rulesets; and
  - the merged comparison ruleset.
- The same warning path is carried into the saved step-3 artifacts and prepended to the markdown working paper.

What changed:
- the merged comparison step still does not hard-fail on every omission;
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
- step `3.1` validates generated rule scope against the clause-classification scope and emits warnings when scope drifts.
- `work_arrangement` is also deterministically normalised back to `all` unless the clause text expressly supports a narrower arrangement.

Why it is no longer listed as active:
- the earlier gap was absence of explicit upstream scope tagging;
- that tagging and downstream comparison now exist.

### Step 3.2 creator over-inferred evaluator-proposed new rules from evaluator prose

Status:
- Resolved as prompt-contract hardening

Current state:
- the direct step `3.2` creator flow now treats evaluator structured JSON as the authoritative operational contract;
- the creator prompt includes a structured review action pack built from:
  - the original step-3 rules JSON; and
  - the evaluator structured review JSON;
- evaluator markdown remains present as explanation, but is no longer intended to authorise extra creator-side adds, removals, merges, or splits.

What changed:
- relevant clause excerpts are now selected from structured evaluator review data first;
- creator instructions explicitly say not to infer extra change actions from evaluator prose unless those actions are reflected in the structured review contract.

Why it is no longer listed as active:
- the earlier issue was that evaluator prose had too much practical authority in the creator prompt;
- the current direct step `3.2` path now gives the structured review JSON priority.

### Step 5.1 prompt tightening

Status:
- Resolved

Current state:
- `src/prompts/step_5_1_generate_pseudocode.py` now separates the shared prompt frame from the creation and consequence subset instructions.
- the prompt is written for a system configuring code, not for a payroll expert.
- the prompt explicitly pushes common overtime rulesets into structured, data-point language.

Why it is no longer listed as active:
- the step 5.1 prompt has already been tightened and validated against the current prompt tests.

### Streamlit and prompt review for 4.1 and 5.1

Status:
- Resolved

Current state:
- the 4.1 template split is in place.
- the subset-specific instructions are injected separately from the shared prompt frame.
- the Streamlit review path matches the reviewed creation and consequence flow.

Why it is no longer listed as active:
- the 4.1 and 5.1 prompt surface now matches the current canonical artifacts.

### Fix consequence clause classification fallback

Status:
- Resolved

Current state:
- the current canonical overtime clause-classification artifact is shared by overtime creation and overtime consequence.
- the old consequence-specific filename fallback has been removed from the active path.

Why it is no longer listed as active:
- the active workflow now uses the canonical filename directly.

### Streamlit subset selection supports selected ruleset runs

Status:
- Resolved

Area:
- `streamlit_review/app.py`
- `streamlit_review/pipeline_runs.py`

Current behaviour:
- the Streamlit sidebar keeps the review ruleset selector separate from the run control;
- the `Step 3 subsets to run` multi-select lets the user run overtime creation, overtime consequence, penalties, or a selected combination;
- the review screens still use a single selected ruleset, which keeps the viewing decision separate from the run selection.

Why this matters:
- the Streamlit UI now matches the CLI's multi-subset run capability;
- users can run selected ruleset branches without changing the review screens at the same time.

### Fix Streamlit duplicate element key issue

Status:
- Resolved

Current state:
- the JSON expander widget key now uses a stable digest instead of Python's process-randomized `hash()`.
- repeated JSON blocks can now render without colliding keys.

Why it is no longer listed as active:
- the duplicate key crash path has been removed from the review UI.

### Streamlit review screen no longer exposed structured review detail during normal successful runs

Status:
- Resolved

Current state:
- the Streamlit review screen now shows both:
  - the readable evaluator and creator markdown summaries; and
  - the structured JSON artifacts behind those summaries.
- evaluator rule-by-rule recommendations and evaluator-proposed new rules are again visible in the review UI.
- creator structured commentary JSON is also visible even when the markdown decision record renders normally.

What changed:
- the evaluator and creator panels no longer return early after rendering markdown;
- the structured JSON expanders and rule-by-rule sections remain available on successful runs.

Why it is no longer listed as active:
- the earlier issue was a UI rendering regression rather than a data-generation problem;
- the structured step `3.2` artifacts are again exposed for review in Streamlit.

### Step 4.1 template split and prompt wiring

Status:
- Resolved

Current state:
- `src/prompts/step_4_1_format_ruleset.py` now injects:
  - a core shared template / structure guide;
  - the loaded template text;
  - subset-specific instructions for creation or consequence.
- `resources/Templates/overtime_consequence_template.md` now provides a lightweight consequence template with the main cohort buckets only.
- the formatter now treats the template as a guide rather than a hard contract.
- step `4.1` still preserves the creation versus consequence split, but no longer forces rare cohort divisions unless the source supports them.

Why it is no longer listed as active:
- the change has been implemented and covered by focused tests;
- the remaining work is now around downstream usage and review, not the `4.1` wiring itself.

### Global prompt framing for common overtime questions

Status:
- Resolved

Current state:
- `src/prompts/overtime_common_prompt_blocks.py` now stores the reusable overtime creation and consequence question blocks.
- creation prompts now explicitly check daily excess hours, span-of-hours rules, and weekly or pay-period thresholds.
- consequence prompts now explicitly check overtime multipliers by employee cohort and other post-overtime consequences such as breaks, meal allowances, TOIL, rest or release entitlements, and minimum payments.

Why it is no longer listed as active:
- the reusable question blocks are now injected into the relevant overtime prompt builders instead of being repeated ad hoc.

### Consequence treatment

Status:
- Resolved

Current state:
- consequence prompts now use the shared consequence question block across classification, generation, review, formatting, and pseudocode steps.
- consequence handling now explicitly prioritises overtime multipliers by cohort and other post-overtime outcomes while avoiding standalone creation-rule commentary.
- the consequence template remains lightweight and focused on the main cohort buckets.

Why it is no longer listed as active:
- the consequence treatment work has been incorporated into the shared prompt blocks and ruleset-specific instructions;
- remaining consequence quality checks should now happen through the next E2E smoke test rather than this planning item.

### Prompt home and reusable configuration surface

Status:
- Resolved

Current state:
- shared prompt text now has a clean home in `src/prompts/overtime_common_prompt_blocks.py`.
- the main overtime prompt builders compose:
  - generic payroll configuration guidance;
  - the relevant reusable ruleset question block;
  - the prompt-specific creation or consequence instructions.
- this keeps the prompt files easier to read today and creates a simpler path toward future user-editable prompt configuration.

Why it is no longer listed as active:
- the prompt layer now has the requested shared configuration surface and a consistent generic-plus-specific layout.

## Current recommendation

The active priority should be:

1. record a clean v1 smoke test through step `6.1` for a representative award;
2. review the step `6.1` questionnaire and Python output shape against calculator needs;
3. implement v1.1 human intervention points across more stages;
4. surface active prompts in the review app and make prompt variants traceable;
5. keep the Streamlit review screens aligned with structured artifact contracts as step `3.2` and step `6.1` evolve.
