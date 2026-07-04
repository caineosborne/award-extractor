# Outstanding Pieces

This document records the current known gaps that still deserve follow-up in the active pipeline.

## Active items


## Add Penalties

Current in progress

Once completed need to 

2 - Confirm working for streamlit  Rerun for MA000018 via the streamlit interface

2b: This states overtime - is it overtime? 

Action required
Clause 2 was identified as relevant to overtime, but it is not present in the penalties ruleset.
Clause 33.3 was identified as relevant to overtime, but it is not present in the penalties ruleset.

3 - confirm that the user edit (4.9) process is working for user edits 

4 - Confirm that we are only passing clauess classified as Penalties or Break into the model
4 - test for any opporunities to optimise - including all prompts fit to the perscribed format - with common rulesets applied to all codes under the same subset, and every LLM call is split into core instructions and limited specific testing. 
5 - User testing for prompt optimisation - Instruct it to remove Overitme clauses. 
6 - Confirm this will work for PDFs 
7 - Update all documentation 



### Make expert and review count able to be adjusted 


### Final screen and YAML output

Status:
- In progress

What to review:
- the final review screen that will generate the YAML file
- the output shape used by that screen
- the award-first / ruleset-specific path flow that feeds it

Why it matters:
- the final screen needs to stay compatible with the reviewed 4.1 and 5.1 artifacts;
- YAML generation should sit on the same canonical workflow as the rest of the pipeline.

### Streamlit subset selection still only supports one ruleset at a time

Status:
- Open

Area:
- `streamlit_review/app.py`

Current behaviour:
- the Streamlit sidebar exposes one `Step 3 ruleset` selector at a time;
- the selected value controls both:
  - which ruleset-specific pipeline steps run; and
  - which ruleset-specific artifacts the review screens display.

Remaining issue:
- the active CLI supports running multiple ruleset subsets in one invocation;
- the Streamlit UI does not yet expose that capability through a multi-select control.

Why this still matters:
- users can run both creation and consequence flows from the CLI;
- the review UI still requires separate runs and separate screen changes to inspect each branch.

Suggested follow-up:
- replace the single-select ruleset control with a multi-select or checkbox control for:
  - overtime creation;
  - overtime consequence;
  - or both;
- decide separately how the review screens should behave when both are selected, because running both and viewing both are different UI decisions.

### Step 3.2 evaluator occasionally returns empty or truncated structured output in live runs

Status:
- Open

Area:
- `src/step_3_2_review_ruleset/llm.py`
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
- consider increasing retry observability by saving the final failed evaluator raw payload to a dedicated exception artifact rather than only surfacing the exception message.

## Resolved items

These earlier items are no longer outstanding in their original form.

### Step 3 completeness validation gap between 3.2 and 3.4

Status:
- Resolved as warning-based validation

Current state:
- `src/step_3_1_generate_ruleset/run.py` now records warning-level completeness issues when shortlisted overtime-creation clauses from step `2.2` are not represented in:
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
- step `3.4` validates generated rule scope against the clause-classification scope and emits warnings when scope drifts.
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
- the consequence review path now falls back to the shared canonical clause-classification artifact when the consequence-specific file is missing.
- the shared creation-named artifact remains the canonical file for both ruleset branches.

Why it is no longer listed as active:
- the review path now resolves the correct source artifact before the E2E run.

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

1. run the end-to-end creation and consequence smoke test;
2. review the consequence outputs for misplaced creation rules and missing multipliers;
3. review the Streamlit path and final YAML screen;
4. keep the Streamlit review screen aligned with the structured artifact contracts as step `3.2` evolves.
