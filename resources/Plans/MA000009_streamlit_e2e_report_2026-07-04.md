# MA000009 Streamlit End-to-End Report

Date: 2026-07-04

## Changes made after the first run

- Shared pipeline reuse is now explicit in the runner.
  - `2.1` is treated as award-level shared output.
  - overtime `2.2` is treated as one shared artifact for both overtime subsets.
  - penalties `2.2` remains separate and deterministic.
- The canonical overtime `2.2` artifact is now `2_2_OT_clause_classification.json`.
  - The older subset-specific overtime filenames are legacy outputs from the first run and should no longer be treated as the canonical artifact names.
- The prompt layer was updated to bias toward conservative inclusion rather than aggressive exclusion.
  - The prompts now prefer retaining plausible clause-supported rules.
  - They avoid over-merging overlapping rules purely to reduce repetition.
  - They stay generic so they can be reused across awards.
- The Streamlit report below reflects the original UI-based end-to-end run.
  - The CLI subset rerun was started after these changes, but it had not completed when this report section was last updated.
- Step 1.1 can now read a local HTML file path as input.
  - That allowed the suffix rerun to reuse the cached MA000009 HTML without needing live fetch access.

## CLI rerun status

Status: Blocked after step 1

- A new suffix rerun was started for `MA000009_promptcmp` so the prompt changes could be reviewed in a clean output tree.
- Step 1.1 completed successfully and wrote the suffixed award inputs to `data/processed/MA000009_promptcmp`.
- Step 2.1 then failed with `openai.APIConnectionError` because this environment cannot reach the OpenAI API.
- No prompt-change comparison outputs were produced from this rerun, so the quality review still needs a network-enabled run.
- A second retry was started as `MA000009_promptcmp2`.
  - It reached the same point: step 1.1 succeeded, step 2.1 failed with the same OpenAI connection error.
  - This makes the blocker reproducible rather than a one-off failure.

## Run status for each of the 3 configurations

### 1. Overtime creation

Status: Success

- Streamlit launched and accepted `MA000009`.
- Full workflow completed through the Streamlit run control.
- Step status reached `success` with 7 of 7 steps complete.
- Generated outputs included:
  - `2_2_OT_creation_clause_classification.json`
  - `3_1_OT_creation_ruleset.{md,json}`
  - `3_2_OT_creation_revised_ruleset.{md,json}`
  - `4_1_OT_creation_formatted_ruleset.md`
  - `5_1_OT_creation_pseudocode.md`
  - `5_1_OT_creation_pseudocode_validation.{json,md}`

### 2. Overtime consequence

Status: Success

- Full workflow completed through the Streamlit run control.
- Step status reached `success` with 7 of 7 steps complete.
- Generated outputs included:
  - `2_2_OT_consequence_clause_classification.json`
  - `3_1_OT_consequence_ruleset.{md,json}`
  - `3_2_OT_consequence_revised_ruleset.{md,json}`
  - `4_1_OT_consequence_formatted_ruleset.md`
  - `5_1_OT_consequence_pseudocode.md`
  - `5_1_OT_consequence_pseudocode_validation.{json,md}`

### 3. Penalties

Status: Success

- Full workflow completed through the Streamlit run control.
- Step status reached `success` with 7 of 7 steps complete.
- Generated outputs included:
  - `2_2_Penalties_clause_classification.json`
  - `3_1_Penalties_ruleset.{md,json}`
  - `3_2_Penalties_revised_ruleset.{md,json}`
  - `4_1_Penalties_formatted_ruleset.md`
  - `5_1_Penalties_pseudocode.md`
  - `5_1_Penalties_pseudocode_validation.{json,md}`

## Any failures or bugs found, including file/path/UI issues

### Confirmed issues

- The app reruns step `2.2` separately for `Overtime creation` and `Overtime consequence`.
  - Current outputs:
    - `2_2_OT_creation_clause_classification.json`
    - `2_2_OT_consequence_clause_classification.json`
  - This does not match the intended design of one shared overtime `2.2` classification artifact reused by both overtime subsets.

- The app also reruns step `2.1` on each full configuration run.
  - The resulting descendant counts varied across runs:
    - Overtime creation: `137`
    - Overtime consequence: `139`
    - Penalties: `136`
  - That is an auditability concern because a shared upstream classification should not drift between sibling runs.

- Review screens load, but they still show noisy unresolved mapping messages.
  - Confirmed messages in saved-output review screens:
    - `No matching Screen 7 combined rule was found for this row.`
    - `No matching Screen 8 revised rule was found for this row.`
    - repeated `Evaluator recommendation was not implemented in the final ruleset.`
  - The screen is functional, but the feedback is not yet reviewer-clean.

### No blocking failures found

- Streamlit launch worked.
- Background run status and logs worked.
- Saved outputs could be reloaded after generation.
- Comparison and review screens loaded without hard errors in the tested cases.
- No broken buttons, missing-path crashes, or silent hard failures were found in the tested path.

## Output quality observations for each configuration

### 1. Overtime creation

Overall: Partly coherent, but still too noisy.

- The core overtime trigger logic is broadly understandable.
- Part-time, casual, and full-time trigger sections are present.
- The output does distinguish some consequence-only items by labeling them as notes.
- However, several items still feel wrongly included in a trigger-focused artifact:
  - waiting time to be paid by cash or cheque
  - overnight-stay exclusion logic
  - salaries absorption / rostered-days-off compliance note
- The formatted guide collapses too much into `All Employees`, which weakens cohort clarity.
- Rostered day off / accrued day off logic appears in both cohort-specific and broader sections, which increases duplication risk.
- Human readability is acceptable, but the trigger set is not yet clean enough for confident reviewer use.

### 2. Overtime consequence

Overall: Stronger than creation, but still duplicated and sometimes mis-scoped.

- The output captures genuine overtime consequences:
  - overtime rate multipliers
  - minimum payments
  - meal allowance
  - time off instead of payment
  - remote catering overtime consequences
- Overtime triggers and consequences are better separated here than in the creation output.
- There is still duplication:
  - rostered/accrued day off minimum payment appears more than once
  - overnight-stay treatment appears more than once
- Some scope placement is awkward:
  - meal allowance appears under `Part-Time Employees Only` even though the rule text refers to full-time or part-time employees
- One citation/mapping looks suspect:
  - the formatted consequence guide shows the cash/cheque waiting-time rule with `[clause 26.15]`, which appears inconsistent with the revised rule text
- Human readability is good enough to review, but the output still needs cleanup for precision and trust.

### 3. Penalties

Overall: The strongest of the three.

- The formatted guide has a sensible structure:
  - shift-based allowances and penalties
  - time-band/day penalties
  - breaks between work periods
  - supporting conditions
- Penalty rates, public holiday rules, non-cumulative penalties, and additive break penalties are mostly expressed clearly.
- The revised penalties ruleset is materially more precise than the initial draft.
- Remaining issues:
  - step-3 validation notes still show missing earlier draft clause references
  - some supporting conditions are mixed into the main penalties guide in a way that could feel too broad
  - `Excluded award terms` is too abstract without clearly restating the covered employee group
- Human readability is good and this output is the closest to reviewer-ready.

## Recommended improvements

### Prompt improvements

- Tighten the overtime creation prompt so it excludes:
  - consequence-only clauses
  - payment-processing edge cases unless they directly create overtime
  - general compliance or context notes that do not change overtime accrual

- Tighten the overtime consequence prompt so it:
  - removes duplicate consequence formulations
  - preserves employee-scope labels accurately
  - avoids reintroducing trigger logic unless strictly needed as dependency context

- Tighten the penalties prompt so it:
  - separates true penalty rules from supporting implementation notes
  - forces clearer identification of which employee group each rule applies to
  - preserves clause references that are important for public holiday alternatives and Christmas substitution logic

- Improve the review prompts so evaluator and creator outputs:
  - resolve rule-to-rule mapping more reliably
  - explain rejected evaluator proposals with less repetitive noise
  - avoid keeping validation-note prose mixed into business rules unless that is an intentional review artifact

### Streamlit/UI improvements

- Add explicit shared-upstream status in the UI so users can see:
  - whether `2.1` is being reused
  - whether `2.2` is being reused
  - which steps are ruleset-specific versus shared

- Change the run control wording to make the execution scope explicit.
  - Example: `Run shared steps + selected ruleset steps` rather than a generic full run label.

- Suppress or regroup noisy review-screen messages such as:
  - `No matching Screen 7 combined rule was found for this row.`
  - repeated `Evaluator recommendation was not implemented...`

- Add a visible artifact summary panel after a run so users can immediately confirm:
  - files written
  - timestamp
  - ruleset key
  - whether outputs were reused or regenerated

### Pipeline/code improvements

- Make overtime `2.2` shared between `Overtime creation` and `Overtime consequence`.
  - One overtime clause-classification artifact should be reused by both overtime subsets.

- Keep a single penalties `2.2` artifact and avoid unnecessary reruns when the deterministic source has not changed.

- Stop rerunning `2.1` for every configuration unless the user explicitly asks to refresh shared upstream steps.

- Investigate and remove non-determinism in `2.1`.
  - The varying descendant counts across sibling runs are not desirable in an audit workflow.

- Fix rule-to-screen mapping used by the review UI so saved review rows resolve back to combined and revised rules consistently.

- Review clause-reference propagation into formatted outputs.
  - At least one clause citation in the consequence output appears inconsistent with the revised rule text.

### Output structure/YAML-readiness improvements

- Move validation notes out of the main business-rules markdown body.
  - Keep them in a separate reviewer diagnostics section or companion file.

- Enforce a stable output structure by section:
  - cohort
  - trigger or consequence type
  - rule text
  - clause references
  - implementation notes
  - exclusions

- Reduce duplication before formatting.
  - One business rule should appear once, with structured scope fields rather than repeated prose variants.

- Make cohort fields explicit and machine-ready.
  - full-time
  - part-time
  - casual
  - day worker
  - shift worker
  - special circumstance

- Separate:
  - rule
  - supporting condition
  - note
  - exception
  - downstream payroll consequence

- If YAML export is a target, normalize rule identifiers and section names so they are stable across reruns.

## Priority order for fixes before I continue development

### Priority 1

- Stop duplicating `2.2` across overtime subsets.
- Stop rerunning shared upstream steps by default when switching rulesets in Streamlit.
- Stabilize `2.1` so shared classification results do not drift between sibling runs.

### Priority 2

- Clean the overtime creation output so only genuine overtime-creation logic remains.
- Remove duplication and scope errors in overtime consequence output.
- Fix clause-reference/citation mismatches carried into formatted outputs.

### Priority 3

- Improve review-screen rule mapping and reduce noisy unresolved messages.
- Move validation notes out of the main business-rule artifact path.
- Make formatted outputs more structured and YAML-ready.

### Priority 4

- Refine penalties supporting-condition placement and employee-scope clarity.
- Improve post-run UI summaries and reuse visibility for reviewer confidence.
