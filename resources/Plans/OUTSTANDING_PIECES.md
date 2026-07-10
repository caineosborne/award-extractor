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

## Recommended next work

The next phase should focus on making the interpretation contract more precise
before adding significant configurability. The pipeline is now sufficiently
complete to test the full business workflow rather than only individual steps.

### V1 end-to-end evidence pack

Status:
- Open

What to add:
- run one representative award cleanly through step `6.1`;
- include overtime creation, overtime consequence, and penalties in the same review record;
- record all human interventions, reruns, rejected recommendations, and unresolved questions;
- record whether the questionnaire and calculator draft are sufficient for the intended business use.

Why it matters:
- a clean run demonstrates that the workflow is operationally useful, not only unit-test green;
- the evidence pack will identify which improvements are genuinely needed before broader rollout.

### Canonical rule contract

Status:
- Open

What to add:
- define a flexible, repeatable rule record rather than a fixed set of award-specific fields;
- give each rule a stable identifier, rule type, scope, trigger, qualification conditions, measurement period, outcome, precedence, exceptions, source clauses, and review status;
- carry the same rule identity from the reviewed ruleset into pseudocode and calculator outputs;
- preserve a clear distinction between source wording, human interpretation, generated implementation logic, and unresolved issues.

Why it matters:
- the number of rules can change from award to award without weakening the structure;
- reviewers can trace one business rule through every downstream artifact;
- step `6.1` can report which rules are implemented, partially implemented, or outside its scope.

### Payroll-relevant definition register

Status:
- Open

What to add:
- extract and retain payroll-relevant definitions as a dedicated artifact;
- record the defined term, source clause, definition text, normalized interpretation, rules that use it, and any unresolved ambiguity;
- require downstream rules to identify the definitions on which they depend.

Priority examples:
- `day`;
- `ordinary hours`;
- `shiftworker`;
- `rostered hours`;
- `week`, `pay period`, or `roster cycle`;
- `continuous shift` or `work period`.

Why it matters:
- a phrase such as “10 hours in a day” is not operationally precise unless the relevant day or measurement period is identified;
- the system should expose ambiguity for human decision rather than silently selecting a meaning.

### Clause-to-rule lineage and completion tracking

Status:
- Open

Recommendation:
- add a source-clause lineage layer that starts from the classified clause population and follows each relevant clause through every downstream stage;
- treat this as a coverage and traceability contract, not as a requirement for every clause to become a standalone rule.

What to add:
- assign stable source identifiers to the most granular operative clause available, for example `3.2.1(a)(i)`;
- retain the parent hierarchy for each granular clause, including the relationship to `3.2.1`, `3.2`, and the relevant higher-level clause;
- allow one granular clause to map to zero, one, or multiple rulesets and downstream rules;
- record an explicit disposition where a clause is not carried forward, such as:
  - operative rule;
  - supporting context;
  - definition or scope condition;
  - duplicate or superseded text;
  - not relevant to the selected ruleset;
  - unresolved;
  - explicitly excluded with a reason;
- carry the clause identifiers and dispositions through steps `2.2`, `3.1`, `3.2`, `4.1`, `5.1`, and `6.1` where applicable;
- show whether a clause was present in the source, classified, included in a ruleset, retained after review, represented in formatted output, represented in pseudocode, and covered by calculator logic;
- distinguish a parent clause being represented through its child clauses from the parent clause itself being silently omitted.

Suggested record:

```text
Source clause
Parent clause path
Source text
Ruleset relevance
Employee type / work arrangement
Definition dependencies
Disposition at each step
Downstream rule IDs
Explicit exclusion reason
Unresolved question
Human review status
```

Important design constraint:
- the ledger should not require every leaf clause to become a rule;
- it should require every relevant leaf clause to have an explainable treatment;
- a parent-level heading or L2 summary must not be treated as sufficient coverage where an operative rule exists only in a more granular child such as `3.2.1(a)(i)`.

Why it matters:
- the current workflow can validate whether a selected L2 clause appears downstream while still allowing a more granular operative provision to fall through the process;
- leaf-level lineage would make omissions visible even when the model-generated prose is plausible;
- the same mechanism would identify whether employee type, work arrangement, definitions, exceptions, and other scope conditions were retained;
- it provides a common audit spine while allowing each pipeline phase to use its own language and artifact shape.

Implementation questions to resolve:
- whether step `1.2` should emit a canonical clause tree with stable leaf identifiers;
- whether step `2.2` should classify leaf clauses directly or classify L2 groups while returning leaf-level dispositions;
- how to represent a rule that combines several leaf clauses;
- how to represent a leaf clause that supports a rule but does not independently create an entitlement;
- how to validate parent/child coverage without double-counting a clause represented by a more granular descendant.

### Pseudocode v2 as an implementation specification

Status:
- Open

What to add:
- make each pseudocode rule identify its inputs, derived values, measurement window, condition, output, priority, exclusions, and source clauses;
- require every reviewed rule to appear in executable pseudocode, implementation notes, or an explicitly justified exclusion;
- add scenario examples for daily, weekly, span-of-hours, roster-cycle, day-worker, shiftworker, weekend, public-holiday, casual, part-time, and exception cases;
- use the scenarios as deterministic acceptance tests where practical.

Why it matters:
- pseudocode becomes a reviewable implementation specification rather than a narrative summary;
- a payroll or implementation reviewer can identify what the rule actually does without reconstructing the interpretation from prose.

### Client-specific implementation field mapping

Status:
- Open

Recommendation:
- add a human-editable implementation input configuration between steps `4.1` and `5.1`;
- keep the award interpretation expressed in stable semantic terms while allowing the implementation field names and availability to vary by client.

Examples:
- map the semantic field `work_start` to a client field called `start_work`;
- map the semantic field `work_end` to a client field called `finish_time`;
- identify that the client does not currently provide a reliable `shiftworker_status` field;
- identify whether roster start and finish times are available, derived, or unavailable.

What to add:
- a field mapping artifact with stable semantic field name, client field name, data type, source system, availability status, derivation rule, and reviewer notes;
- explicit availability statuses such as `available`, `derivable`, `missing`, `uncertain`, and `not applicable`;
- a human review surface for editing field names and confirming the meaning of client fields;
- a clear distinction between a renamed field and a genuinely different or insufficient data point;
- injection of the approved field mapping into step `5.1` pseudocode generation and later calculator generation;
- pseudocode that names missing inputs as required operational inputs and explains which rules cannot be applied without them.

Important design constraint:
- client field names should be aliases for stable semantic concepts, not replacements for the concepts themselves;
- a mapping such as `start_work` -> `work_start` is safe only after the reviewer confirms that both fields have the same meaning, timing basis, and granularity;
- if the client does not know who is a shiftworker, the system should not infer that status from a vague field or silently treat everyone as a day worker.

Expected output when information is missing:

```text
Missing input: shiftworker_status
Affected rules: OT-CONSEQUENCE-004, PENALTY-002
Current treatment: cannot determine whether the shiftworker-specific rule applies
Required action: obtain a reliable employee classification or agree a documented fallback
Pseudocode treatment: branch explicitly on shiftworker_status and mark the result for review when unavailable
```

Why it matters:
- the same reviewed ruleset may need to be implemented against different client data models;
- this creates a controlled hand-off from award interpretation to implementation design;
- missing client data becomes a visible business requirement rather than an implicit model assumption;
- reviewers can distinguish an award ambiguity from a client data deficiency.

### Step 6.1 calculator contract and coverage status

Status:
- Open

What to review:
- confirm whether step `6.1` is a review aid, a configuration generator, a test calculator, or a payroll-engine prototype;
- define the intended calculator inputs and outputs from representative scenarios;
- add explicit coverage fields for implemented, partially implemented, not implemented, and manual-decision rules;
- keep generated Python clearly labelled as a draft unless it has passed the relevant rule and scenario tests.

Why it matters:
- the current calculator output is a projection of the reviewed rules, not a complete reproduction of every rule;
- explicit coverage prevents a structured output from appearing more complete than it is.

### “Talk to an Award” reviewer assistant

Status:
- Proposed

Recommendation:
- pursue this as a reviewer-facing question-and-answer assistant, not as an authoritative payroll decision-maker.

Useful first-release questions:
- “What does this award say about overtime on Sunday?”
- “Which clauses support the ordinary-hours boundary?”
- “What does ‘day’ mean in the clauses used by this rule?”
- “Which rules apply to casual shiftworkers?”
- “Show me the unresolved interpretation questions.”
- “Compare the reviewed rule with the source clauses.”

Minimum behaviour:
- answer only from the selected award and its saved artifacts;
- cite the relevant clause references and link back to the source text;
- distinguish source wording, generated interpretation, human-edited content, and inference;
- say when the award is silent or ambiguous;
- show the relevant rule IDs, definitions, and review status;
- never silently change a ruleset or calculator configuration through chat.

Recommended implementation order:
1. build retrieval over the structured award, definition register, reviewed rules, pseudocode, and validation artifacts;
2. support cited answers and “show evidence” responses;
3. add comparison and unresolved-question views;
4. only later consider controlled actions such as creating a review note or proposing an edit.

Why it could be valuable:
- it would make the project useful between pipeline runs, when a reviewer wants to investigate a clause or interpretation quickly;
- it could expose gaps in definitions and rule coverage through real user questions;
- it provides a natural human interface without requiring the user to navigate every intermediate artifact.

Main risks:
- a confident but unsupported answer would be more dangerous than no answer;
- retrieval must preserve award version and clause context;
- the assistant must not blur the distinction between “what the award says” and “how this project interpreted it.”

The chatbot should therefore follow the canonical rule and definition work,
but a small read-only prototype could be useful during that work as a way to
test whether the artifacts are understandable to reviewers.

## Current recommendation

The active priority should be:

1. complete the V1 end-to-end evidence pack;
2. define clause-to-rule lineage at granular clause level, alongside the definition register;
3. use that lineage to measure clause completion through every pipeline step;
4. add client-specific implementation field mapping between steps `4.1` and `5.1`;
5. raise pseudocode to an implementation-specification standard with scenario tests;
6. review the step `6.1` contract and add rule-coverage status;
7. prototype a read-only, citation-first “Talk to an Award” reviewer assistant;
8. then implement broader human intervention points, prompt provenance, and configurable expert/reviewer counts.
