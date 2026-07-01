# Simplification Plan

## Goal

This refactor should make the pipeline easy to read top-to-bottom.

The main outcomes are:

- one obvious pipeline entrypoint
- one obvious folder per step
- prompts stored in prompt files, not embedded in long scripts
- deterministic logic separated from LLM calls
- canonical output naming that always includes the step number
- removal of legacy paths, fallback-heavy behaviour, and duplicate helper layers
- overtime clause classification moved into step `2.2` instead of being bundled into ruleset drafting

The target reader is not just a developer. A reviewer should be able to see:

- what step ran
- what file it read
- what file it wrote
- what prompt was used
- what deterministic checks were applied

## Progress status

Current status of the simplification plan:

- Step 1 completed
- Step 2 completed
- Step 3 completed
- Step 4.1 completed
- Step 4.2 completed
- Step 4.5 Completed
- Step 4.6 Completed
- Step 4.7 Completed
- Step 4.8 not started
- Step 4.9 not started
- Step 4.10 not started
- Step 5 not started
- Step 6 not started
- Step 7 not started
- Step 8 not started

What is already done:

- target structure and naming decisions are defined
- shared pipeline context has been introduced
- shared output naming has been introduced
- step 2.2 has been moved into its own self-contained folder
- step 3.1 and step 3.2 are now owned by numbered folders with local prompt wrappers
- several active scripts now use the shared naming layer

What is not done yet:

- reviewing `core.py` usage in completed step folders and moving functions into the clearest owner files
- deleting the old script-era implementation files
- removing the remaining `script_*` dependencies in later phase 4 steps
- removal of automatic archive creation

## Core decisions

### 1. Keep one top-level runner

Step `1` should become the core pipeline runner.

That file should do very little:

- parse arguments
- build the pipeline context
- run selected steps in order
- print where outputs were written

It should not contain:

- prompt text
- detailed file naming logic
- large parsing helpers
- business-rule review logic

### 2. Use step-first structure in `src/`

The repo should be organized around step numbers, not historical script names.

Recommended direction:

- `src/1_run_pipeline.py`
- `src/step_1_1_fetch/`
- `src/step_1_2_parse_award/`
- `src/step_2_1_classify_payments/`
- `src/step_2_2_classify_overtime_clauses/`
- `src/step_3_1_generate_ruleset/`
- `src/step_3_2_review_ruleset/`
- `src/step_4_1_format_ruleset/`
- `src/step_5_1_generate_pseudocode/`
- `src/common/`
- `src/prompts/`

Reason for this shape:

- it keeps the numeric workflow visible
- it still works cleanly with Python imports
- it avoids invalid Python module names like `1.1.py`

Inside each step folder, keep files responsibility-based and boring:

- `run.py`
- `llm.py`
- `deterministic.py`
- `io.py`

Only create the files that are actually needed for that step.

In this project, readability is more important than minimizing file count or chasing software-engineering neatness.

For audit use, it is acceptable to have:

- more files
- more named functions
- more explicit intermediate artifacts

if that makes the workflow easier to read and review.

### 3. Separate LLM work from deterministic work

For each step that uses a model, we should split responsibilities clearly.

LLM files should own:

- prompt assembly
- model request payloads
- response parsing
- response validation that is specific to the model output format

Deterministic files should own:

- path building
- input loading
- data extraction
- regex rules
- output naming
- rule application
- non-LLM validation checks

The step `run.py` file should mainly read like:

1. load input
2. build context
3. run deterministic preparation
4. call LLM helper if needed
5. run deterministic validation
6. write outputs

Within a step, we should also prefer separate named functions for distinct business activities rather than combining them into one large function.

For example, if a step has:

- expert A drafting
- expert B drafting
- merge or comparison

those should be implemented as three separate functions, even if they remain within one step folder.

For later refactoring steps, deterministic work can also be split into two clearer categories:

- `procedural.py` for deterministic artifact creation and transformation
- `verification.py` for deterministic checks, validation, and review logic

This split is most useful where a step has enough complexity that reviewers benefit from seeing:

- what the step did
- how the step was checked

This is a Step 4 structural refinement, not a requirement for the earlier infrastructure work.

### 4. Move repeated helpers into `common/`

`common/` should keep only shared helpers that are truly cross-step and easy to explain.

Good candidates:

- pipeline context construction
- output path construction
- archive writing
- OpenAI environment loading
- JSON/text file loading
- shared response extraction
- shared ruleset key parsing
- shared output naming helpers

Do not move step-specific business logic into `common/` just to make files shorter.

The test for `common/` should be:

- used by more than one step
- same meaning everywhere
- easier to review once shared

### 5. Make prompts first-class files

All prompts should live in prompt modules or prompt text files under `src/prompts/`.

Each active step should have one obvious prompt home.

Recommended prompt layout:

- `src/prompts/2_1_payment_classification.py`
- `src/prompts/2_2_overtime_clause_classification.py`
- `src/prompts/3_1_overtime_ruleset_generation.py`
- `src/prompts/3_2_ruleset_review.py`
- `src/prompts/4_1_ruleset_formatting.py`
- `src/prompts/5_1_pseudocode_generation.py`

Prompt files should contain:

- system prompt text
- user prompt builders
- small prompt-specific formatting helpers

Prompt files should not contain:

- path resolution
- file reading
- output writing
- broad workflow orchestration

### 6. Use canonical output names

Every output written by a step should include the step number in the filename.

That rule should be universal, not optional.

Recommended filename pattern:

`<step>_<ruleset_if_any>_<artifact>.ext`

The award identity should live at the folder level, not be repeated in every filename.

Recommended folder pattern:

`data/processed/<award_code>/`

Examples:

- `1_1_raw.html`
- `1_2_award.json`
- `2_1_payment_classification.json`
- `2_2_OT_creation_clause_classification.json`
- `3_1_OT_creation_ruleset.md`
- `3_2_OT_creation_ruleset_review.md`
- `3_2_OT_creation_ruleset_revised.md`
- `4_1_OT_creation_formatted_ruleset.md`
- `5_1_OT_creation_pseudocode.md`
- `5_1_OT_creation_pseudocode_validation.json`

This gives us immediate traceability:

- the step that wrote the file
- the type of artifact
- which ruleset it belongs to

It also removes redundant filename noise when the file is already inside the award folder.

### 6A. Use short but still readable artifact names

File names should be shorter than the current versions, but they should still be self-explanatory to a reviewer.

Recommended direction:

- abbreviate `overtime` to `OT`
- keep `creation` and `consequence` written in full
- keep artifact descriptors explicit
- avoid filenames that are only numbers

Good examples:

- `2_1_payment_classification.json`
- `2_2_OT_creation_clause_classification.json`
- `3_1_OT_creation_expert_a.md`
- `3_1_OT_creation_expert_b.md`
- `3_1_OT_creation_merged_ruleset.md`
- `3_2_OT_creation_review.md`
- `3_2_OT_creation_revised_ruleset.md`

Avoid:

- `2.1.json`
- `3.1_a.md`
- `final.md`

The goal is:

- short enough to scan quickly
- descriptive enough to stand alone when needed
- consistent enough that a reviewer can predict the next file name

### 7. Remove legacy behaviour instead of preserving it

Phase 7A - review all code to ompatibility layers, fallback paths, and duplicate names.

Remove what is no longer needed in the new format.  


The simplification direction should be:

- keep only the active workflow
- delete legacy artifacts and legacy naming support
- keep compatibility shims only if they are tiny and temporary

Specifically, reduce:

- old overtime-only path inference
- fallback-first downstream file selection
- duplicate helper aliases
- wrapper scripts that exist only to preserve an old concept
- automatic archival behaviour that creates extra timestamped copies by default

### 7B. Remove automatic timestamp archives from the default workflow

Automatic timestamp archive files are not part of the core audit workflow and add noise to the output folders.

Recommended direction:

- do not write timestamped archive copies by default
- keep one canonical current output file for each artifact
- only create extra copies when a user explicitly asks to preserve one

The preferred operator flow is:

- review the current artifact in Streamlit
- choose an explicit `Save copy` action when a snapshot should be retained

This keeps the default output set simpler and easier to review.

It also makes it clearer which files are:

- current working outputs
- intentionally preserved snapshots

### 7C. Streamlit should own explicit snapshot saving

If operators want to keep a point-in-time version of an artifact, Streamlit should provide an explicit control for that.

Recommended direction:

- one `Save copy` action per reviewable output
- user-triggered snapshot naming rather than automatic timestamp spam
- snapshots stored in a clear, reviewable location

The main principle is:

- default pipeline runs should overwrite the canonical active artifact
- saved copies should exist only because a user deliberately kept them

### 8. Align code names, output names, and docs

The same step language should appear in:

- source folders
- script names
- output filenames
- tests
- docs
- Streamlit review UI

If the user sees step `3.2`, the code and output should also say `3.2`.

That alignment is the main simplification benefit.

### 9. Make overtime clause classification a standalone operator step

The current `src/script_3_part1_classify_overtime_clauses.py` does too much inside the ruleset-development stage.

That clause classification work should move into step 2 as its own sub-step.

Recommended direction:

- payment clause classification remains step `2.1`
- overtime clause classification becomes step `2.2`
- ruleset drafting starts at step `3.1`

Why this matters:

- it makes the workflow easier to understand
- it gives a clean checkpoint before ruleset drafting
- it lets the GUI run clause classification separately
- it reduces the amount of hidden work inside the ruleset generation button

The GUI should therefore have its own explicit button for overtime clause classification, separate from ruleset generation.

### 10. Prefer explicit sub-functions for multi-part review steps

Some steps are still conceptually one operator-visible step, but internally they perform several different actions.

In this project, that internal split should stay visible in the code.

Recommended direction:

- one operator-visible step
- separate named functions for each major internal action
- separate intermediate output files where useful

This is especially important for:

- step `3.1` ruleset drafting
- step `3.2` review and revision

For step `3.1`, the preferred structure is:

- `draft_expert_a(...)`
- `draft_expert_b(...)`
- `merge_expert_drafts(...)`

These may live in one step folder, but they should not be collapsed into one large function.

For step `3.2`, the preferred structure is:

- `run_evaluator_review(...)`
- `run_creator_review(...)`
- `recreate_revised_ruleset(...)`

Again, the main principle is explicitness over compactness.

## Proposed target structure

This is the recommended end state for the active pipeline.

```text
src/
  1_run_pipeline.py
  step_1_1_fetch/
    run.py
    deterministic.py
    io.py
  step_1_2_parse_award/
    run.py
    deterministic.py
    io.py
  step_2_1_classify_payments/
    run.py
    llm.py
    deterministic.py
    io.py
  step_2_2_classify_overtime_clauses/
    run.py
    llm.py
    deterministic.py
  step_3_1_generate_ruleset/
    run.py
    llm.py
    deterministic.py
  step_3_2_review_ruleset/
    run.py
    llm.py
    deterministic.py
  step_4_1_format_ruleset/
    run.py
    llm.py
    deterministic.py
  step_5_1_generate_pseudocode/
    run.py
    llm.py
    deterministic.py
  common/
    pipeline_context.py
    output_naming.py
    file_io.py
    llm_io.py
    openai_setup.py
    ruleset_keys.py
  prompts/
    2_1_payment_classification.py
    2_2_overtime_clause_classification.py
    3_1_overtime_ruleset_generation.py
    3_2_ruleset_review.py
    4_1_ruleset_formatting.py
    5_1_pseudocode_generation.py
```

## Implementation plan

This should be done in 8 steps.

### Phase 1. Freeze the target naming scheme - COMPLETED

Decide the canonical step labels and artifact descriptors once.

Deliverables:

- one filename standard for all active outputs
- one folder naming standard for `src/`
- one ruleset naming standard

Notes:

- this should be decided before moving files
- output naming should be treated as the source of truth for downstream logic

### Phase 2. Introduce one shared deterministic pipeline context - COMPLETED

Create one shared context object in `src/common/` that resolves:

- award code
- selected steps
- selected ruleset
- input paths
- output paths
- archive paths

This replaces repeated path inference across scripts.

This context should treat overtime clause classification as a first-class step between payment classification and ruleset drafting.

### Phase 3. Move output naming into one helper module - COMPLETED

Create one deterministic output naming module that every step uses.

That module should build:

- current output file paths
- archive file paths
- related review and validation artifact paths

After this step, no active script should hand-build filenames inline.

This helper should explicitly build separate output paths for:

- step `2.1` payment classification
- step `2.2` overtime clause classification
- step `3.1` ruleset draft
- step `3.2` review and revised ruleset

This phase defines the canonical folder and filename scheme.
Phase 4.8 should apply that scheme consistently across the active step folders once the structural step-folder refactor is complete.
Phase 7 should verify that those step-numbered outputs are now written consistently; it is not the phase that introduces the naming change.

Status:

- completed

### Phase 4. Split step files into `run`, `llm`, and `deterministic` - IN PROGRESS

Refactor the current long scripts so each step has a small number of clear files.

This is the step that contains moving `src/script_3_part1_classify_overtime_clauses.py`
into the step-2 area as standalone step `2.2`.

Once completed, all active runtime logic for the affected steps should run from the numbered step folders rather than from `script_*` locations.

That change should include:

- moving the clause-classification logic into the new step-2 structure
- making it operator-visible as step `2.2`
- separating it from ruleset drafting
- updating Streamlit so it has its own button when the CLI refactor is ready

Priority order:

- Phase 2.2 overtime clause classification
- Phase 3 ruleset review and generation
- Phase 5 pseudocode
- Phase 2.1 classification
- Phase 1 fetch/parse

This order gives the biggest readability gain first.

Implementation note:

- use step-first names that still import cleanly in Python
- preferred folder pattern is `src/step_2_2_classify_overtime_clauses/` rather than `src/2_2_classify_overtime_clauses/`
- keep the step number visible in the folder name even if a small prefix is needed for valid imports
- do not treat `core.py` as the default destination for moved code
- put each moved function in the file that owns its responsibility: orchestration in `run.py`, model calls and model response handling in `llm.py`, deterministic loading/transformation/writing in `deterministic.py`, and prompt construction in `src/prompts/`
- create narrower files such as `verification.py`, `procedural.py`, `schema.py`, or `types.py` when a step has enough code that one deterministic file becomes hard to review
- use `core.py` only for small shared step-local types or constants that are genuinely used by multiple files in that same step folder

Recommended Phase 4 subphases:

#### Phase 4.1. Extract step `2.2` into its own folder and CLI path - COMPLETED

Scope:

- create `src/step_2_2_classify_overtime_clauses/`
- split the current clause-classification work into `run.py`, `llm.py`, and deterministic helpers
- make step `2.2` callable directly from the CLI pipeline
- change active pipeline sequencing so step `3` reads the `2.2` artifact instead of silently creating it
- keep all active step-`2.2` files inside `src/step_2_2_classify_overtime_clauses/`, `src/common/`, or `src/prompts/`
- do not leave active runtime imports for step `2.2` pointing at `script_*` files, ensure all code is encapsualted in these folders

Deliverable:

- operators can run step `2.2` directly from the CLI
- step `3` has a clean deterministic dependency on the step `2.2` output
- all active step-`2.2` logic is owned by the step folder, `common`, or `prompts`

#### Phase 4.2. Split step `3` into generation and review structure - COMPLETED

Scope:

- separate ruleset generation into a dedicated step folder
- separate ruleset review into a dedicated step folder
- make the main internal actions explicit
- keep existing behaviour stable while moving orchestration out of the long scripts
- keep all active step-`3.1` and step-`3.2` files inside their step folders, `src/common/`, or `src/prompts/`
- do not leave active runtime imports for step `3.1` or step `3.2` pointing at `script_*` files

Required visible functions:

- `draft_expert_a(...)`
- `draft_expert_b(...)`
- `merge_expert_drafts(...)`
- `run_evaluator_review(...)`
- `run_creator_review(...)`
- `recreate_revised_ruleset(...)`

Deliverable:

- step `3.1` and step `3.2` are structurally simpler and easier to review top-to-bottom
- the active runtime for step `3.1` and step `3.2` no longer relies on `script_*` modules

Status:

- completed

#### Phase 4.3. Split step `5` pseudocode generation - COMPLETED

Scope:

- create a dedicated step folder for pseudocode generation
- separate prompt assembly, output parsing, and deterministic validation
- keep validation outputs explicit and reviewable
- move active runtime logic out of `src/script_5b_generate_overtime_pseudocode.py`
- move active validation logic out of `src/script_5b_validate_overtime_pseudocode.py`
- keep all active step-`5.1` files inside `src/step_5_1_generate_pseudocode/`, `src/common/`, or `src/prompts/`
- do not leave active runtime imports for step `5.1` pointing at `script_*` files

Function placement:

- `run.py` should own the top-level `generate_core_overtime_pseudocode(...)` flow: resolve inputs, request initial pseudocode, run validation, request repair when needed, and return/write the final result.
- `llm.py` should own model setup, model selection, the initial pseudocode request, repair request, response text extraction, and any model-response validation that is specific to the pseudocode prompt contract.
- `deterministic.py` should own source path selection, ruleset-key inference, loading the reviewed rules artifact, output path resolution, and source inventory construction.
- `verification.py` should own deterministic pseudocode validation, validation report construction, validation artifact path resolution, and writing validation JSON/markdown outputs.
- `src/prompts/5_1_pseudocode_generation.py` or the existing prompt module should own pseudocode prompt text, repair prompt text, and prompt-specific formatting helpers.
- `core.py` should not receive copied script bodies. If needed at all, it should contain only small step-local constants or dataclasses shared across `run.py`, `llm.py`, `deterministic.py`, and `verification.py`.

Deliverable:

- pseudocode generation no longer depends on one long mixed-responsibility script
- reviewers can trace the step from `run.py` into clearly separated model, deterministic, and validation files

Status:

- completed

#### Phase 4.4. Split step `2.1` payment classification COMPLETED

Scope:

- move step `2.1` into its own `run`, `llm`, and deterministic files
- keep business-rule extraction readable and explicit
- move active runtime logic out of `src/script_2_classify_payments.py`
- keep all active step-`2.1` files inside `src/step_2_1_classify_payments/`, `src/common/`, or `src/prompts/`
- do not leave active runtime imports for step `2.1` pointing at `script_*` files

Function placement:

- `run.py` should own the top-level `classify_payments(...)` flow: resolve inputs, classify each group, build the output artifact, and write the result.
- `deterministic.py` should own award JSON loading, top-level clause/group construction, direct reference mapping, output path resolution, deterministic tag rules, title-only/top-level handling that does not call the model, and artifact writing.
- `llm.py` should own model setup, model selection, payment-classification request payloads, model response parsing, model response validation, and the per-group model classification call.
- `src/prompts/2_1_payment_classification.py` or the existing prompt module should own the system prompt, user prompt builder, tag definitions, and prompt-specific formatting helpers.
- `schema.py` or `types.py` should be added if the step needs a clear home for dataclasses, schema version constants, allowed tags, or structured response shapes shared by both deterministic and LLM code.
- `core.py` should not be used as a dumping ground for copied script functions. If it remains, it should contain only small shared step-local definitions that do not clearly belong to deterministic, LLM, prompt, or schema files.

Deliverable:

- payment classification structure matches the newer downstream steps
- the active step `2.1` runtime is readable from `run.py` without importing `src/script_2_classify_payments.py`

Status:

- completed

#### Phase 4.5. Review completed step folders and reduce `core.py` - COMPLETED

Scope:

- review `src/step_2_2_classify_overtime_clauses/`, `src/step_3_1_generate_ruleset/`, and `src/step_3_2_review_ruleset/`
- treat this phase primarily as a structural cleanup for `step_3_1` and `step_3_2`, which still contain large mixed-responsibility `core.py` files
- use the completed `step_2_1` and `step_5_1` layouts as the reference pattern for file ownership and orchestration style
- move functions out of `core.py` where a clearer owner file already exists
- keep behaviour stable while improving the internal file layout
- keep all active files for those steps inside their step folders, `src/common/`, or `src/prompts/`
- do not reintroduce active runtime imports from `script_*` files
- prefer explicit, responsibility-named files over one large shared module, even if that means adding `schema.py` or `verification.py`

Function placement:

- `run.py` should keep only top-level orchestration and visible operator actions.
- `llm.py` should own model setup, model selection, model request payloads, model response extraction, model repair loops, and model-output validation that is specific to the LLM contract.
- `deterministic.py` should own deterministic loading, source selection, output path resolution, artifact construction, artifact writing, and non-model transformations.
- `verification.py` should be added where deterministic validation or consistency checking is substantial enough to obscure the main deterministic flow.
- `schema.py` or `types.py` should be added where dataclasses, schema constants, allowed values, or structured response shapes are shared across multiple files.
- `src/prompts/` should own prompt text and prompt-specific formatting helpers.
- `core.py` should be deleted if it becomes empty. If it remains, it should contain only small step-local constants or types that are genuinely shared by multiple files and do not clearly belong elsewhere.

Implementation intent:

- `step_2_2` is a smaller cleanup target. Only move code out of `core.py` where ownership is obvious. It does not need forced file proliferation if the result would be less readable.
- `step_3_1` and `step_3_2` are the real focus of this phase. The goal is not merely to shrink `core.py`, but to make each step readable top-to-bottom from `run.py` through `llm.py`, `deterministic.py`, and any supporting files.
- prefer the `step_2_1` pattern when shared data structures dominate and the `step_5_1` pattern when deterministic validation deserves its own file
- avoid moving functions into `core.py` just because they are currently hard to place; if needed, introduce `schema.py` or `verification.py` instead
- keep `__init__.py` minimal so file reorganization does not create import cycles

Step 3.1 refactor target:

- `run.py` should remain the readable orchestration entrypoint for the full expert-drafting workflow
- `run.py` should own: expert run count checks, input resolution calls, client/model setup calls, the sequencing of expert A, expert B, optional additional experts, merge handling, warning combination, and final artifact writing calls
- `run.py` should not own: prompt building, model request payload construction, raw model response parsing, expert-comparison parsing, or low-level validation logic
- `llm.py` should own: `load_openai_client(...)`, `selected_models(...)`, `draft_expert_a(...)`, `draft_expert_b(...)`, `draft_additional_expert(...)`, `merge_expert_drafts(...)`, and the lower-level request helpers those visible functions depend on
- `llm.py` should also own the current model-facing helpers that are still buried in `core.py`, including environment loading, request execution, raw response extraction/parsing, and model-specific validation or repair of structured outputs
- `deterministic.py` should own: source artifact loading, path resolution, expert draft output path construction, merged output path construction, warning combination helpers if they are purely deterministic, artifact serialization, and markdown/json writing
- if rule-validation, clause-coverage checks, or source-to-rule consistency checks are large enough to obscure `deterministic.py`, add `verification.py` and move them there
- if rule dataclasses, regex constants, response-shape constants, or shared structured metadata no longer fit cleanly in one file, add `schema.py`
- prompt builders used by the expert drafting and comparison calls should live in `src/prompts/` or `llm.py`, not in `run.py` and not in `core.py`

Step 3.2 refactor target:

- `run.py` already has the right visible surface. Keep `run_evaluator_review(...)`, `run_creator_review(...)`, and `recreate_revised_ruleset(...)` there as operator-visible workflow steps
- `run.py` should continue to own only orchestration: loading inputs, resolving active models/clients, sequencing evaluator then creator, handling status callbacks, and dispatching final writes
- `run.py` should not own prompt assembly details, raw model call mechanics, JSON extraction, creator-response parsing, or deterministic artifact loading/writing details
- `llm.py` should own: `load_client(...)`, model selection helpers, evaluator request loops, creator request loops, response text extraction, creator/evaluator repair attempts, creator response parsing, and model-output validation specific to the review prompt contract
- `deterministic.py` should own: interpretation/classification source loading, ruleset-key inference, output path resolution, feedback/creator/revised artifact writing, and any non-model transformation used by `run_evaluator_review(...)`, `run_creator_review(...)`, or `recreate_revised_ruleset(...)`
- add `verification.py` if deterministic checks around review outputs, coverage warnings, or reconstructed rulesets are large enough to obscure deterministic loading/writing
- add `schema.py` if the step needs a clearer home for review artifact dataclasses, response-shape constants, regex patterns, allowed values, or other shared step-local structured definitions
- prompt-message builders used by the evaluator and creator flows should live in `src/prompts/` or `llm.py`, not in `core.py`

Required visible function ownership:

- In `src/step_3_1_generate_ruleset/llm.py`: `draft_expert_a(...)`, `draft_expert_b(...)`, and `merge_expert_drafts(...)`.
- In `src/step_3_1_generate_ruleset/run.py`: the top-level orchestration that calls those visible expert functions, combines warnings, and writes the final outputs.
- In `src/step_3_2_review_ruleset/run.py`: `run_evaluator_review(...)`, `run_creator_review(...)`, and `recreate_revised_ruleset(...)`.
- In `src/step_3_2_review_ruleset/llm.py`: the lower-level evaluator and creator request loops that those visible review functions call.
- In `src/step_3_2_review_ruleset/deterministic.py`: the source loading and output writing helpers that `run_evaluator_review(...)`, `run_creator_review(...)`, and `recreate_revised_ruleset(...)` depend on.
- None of these six visible functions should live in `core.py`.

Supporting function guidance:

- Prompt-message builders used by `draft_expert_a(...)`, `draft_expert_b(...)`, or `merge_expert_drafts(...)` should live in `src/prompts/` or `llm.py`, not in `run.py`.
- Prompt-message builders used by `run_evaluator_review(...)` or `run_creator_review(...)` should live in `src/prompts/` or `llm.py`, not in `core.py`.
- Path resolution, artifact loading, artifact writing, and deterministic rule/coverage checks used by those visible functions should live in `deterministic.py` or `verification.py`.
- Dataclasses, enums, and step-local schema constants shared across multiple files should move to `types.py` or `schema.py` when they no longer fit cleanly in one owner file.
- When moving code, preserve the current public function names and call signatures unless a signature change is required to achieve the split cleanly.
- Prefer moving existing functions with minimal rewriting over opportunistic redesign. The structural split is the goal of this phase.
- If a helper is only used by one file after the split, keep it in that file rather than creating a new shared module.

Deliverable:

- `step_2_2`, `step_3_1`, and `step_3_2` stay script-free but no longer concentrate copied implementation logic in oversized `core.py` files
- `step_3_1` and `step_3_2` read like the newer `step_2_1` and `step_5_1` folders: `run.py` for orchestration, `llm.py` for model work, `deterministic.py` for non-model processing, and extra files only where they improve reviewability
- reviewers can trace each completed step through responsibility-named files without using `core.py` as a catch-all

#### Phase 4.6. Split step `1` fetch and parse - COMPLETED


Scope:

- review `src/step_1_1_fetch/` and `src/step_1_2_parse_award/`
- keep all active step-`1` files inside their step folders, `src/common/`, or `src/prompts/`
- move any remaining visible orchestration out of `core.py` into `run.py`
- keep fetch-specific network and source-resolution logic in `deterministic.py`
- keep parsing and artifact-writing logic in `deterministic.py` or `llm.py` only where a model call is actually involved
- keep the Fair Work HTML path logic in the step `1.1` area
- keep the PDF path logic in a separate step-`1` file rather than folding it into the HTML file
- do not reintroduce active runtime imports for step `1` pointing at `script_*` files

Deliverable:

- step `1` is represented as a self-contained folder pair with clear responsibility-based files
- reviewers can trace fetch and parse separately without relying on `core.py` as the main home for step logic

Function placement:

- `run.py` should own the top-level fetch or parse orchestration for its step.
- `deterministic.py` should own source-path resolution, input loading, artifact construction, and output writing.
- `llm.py` should only exist where the step actually uses model calls.
- `src/prompts/` should own any step `1` prompt text or formatting helpers.
- `core.py` should only retain small shared step-local types or constants if they are genuinely needed by more than one file.

#### Phase 4.7. Split step `4.1` format ruleset - COMPLETED

Scope:

- review `src/step_4_1_format_ruleset/`
- keep all active step-`4.1` files inside `src/step_4_1_format_ruleset/`, `src/common/`, or `src/prompts/`
- move any remaining visible orchestration out of `core.py` into `run.py`
- keep deterministic path resolution, input loading, and output writing in `deterministic.py`
- keep model-specific formatting calls and response handling in `llm.py`
- do not reintroduce active runtime imports for step `4.1` pointing at `script_*` files

Function placement:

- `run.py` should own `summarize_overtime_entitlements(...)` as the top-level step `4.1` orchestration.
- `llm.py` should own the formatted-ruleset request call, model selection, response extraction, and any prompt-contract validation.
- `deterministic.py` should own interpretation-path resolution, output-path resolution, input loading, and writing the formatted artifact.
- `src/prompts/` should own any step `4.1` prompt text or formatting helpers.
- `core.py` should only retain small shared step-local types or constants if they are genuinely needed by more than one file.

Deliverable:

- step `4.1` is represented as a self-contained folder with clear responsibility-based files
- reviewers can trace the formatting workflow without relying on `core.py` as the main home for step logic

#### Phase 4.8. Apply canonical output folders and filenames after the structural refactor

This phase happens after the Phase 4 step-folder refactor work is complete enough that the active runtime for the relevant steps already lives in numbered step folders.

Scope:

- update the active migrated steps to write outputs using the canonical Phase 3 naming scheme
- make the canonical award-first folder structure the default active write path
- remove remaining active writes that still use legacy folder names or legacy filename shapes
- keep the behavioural content of the artifacts the same while standardising where they are written

Required outcomes:

- active outputs should write to `data/processed/<award_code>/`
- active filenames should include the step number consistently
- downstream step readers should use the canonical current artifact paths rather than legacy fallbacks wherever practical
- Phase 7 tests should then verify this behaviour rather than introducing it

This phase is about active output path adoption.
The later cleanup of timestamp archive behaviour should still happen separately once the structural and naming refactors are stable.

#### Phase 4.9. Simplify output retention

As part of the later cleanup work, remove automatic timestamp archive creation from the default pipeline flow.

Replace it with:

- one canonical active file per artifact
- explicit Streamlit-driven snapshot saving when needed

This should be implemented after the structural refactors and canonical output-path rollout are stable, so we do not mix storage-policy changes into the earlier path and step refactors.

#### Phase 4.10. Update Streamlit in one action after the CLI refactor is stable

Scope:

- add a standalone step `2.1` control
- add a standalone step `2.2` control
- align step labels and button ordering with the CLI pipeline
- remove UI behaviour that still assumes clause classification is bundled into ruleset drafting

Operator rule during subphases 4.1 to 4.9:

- treat the CLI as the primary execution path
- defer Streamlit run-control changes until the structural CLI work and completed-folder cleanup are ready
- for the simpler model pass, complete Step `4.1`, Step `4.2`, and Step `4.5` first, then return for full-model validation and feedback before continuing

Deliverable:

- one coherent Streamlit update after the refactor shape is settled

Recommended execution order:

1. Phase 4.5
2. Phase 4.6
3. Phase 4.7
4. Phase 4.8
5. Phase 4.9
6. Phase 4.10

Step 4 scope rule:

- every active pipeline step file should move into a numbered step folder
- keep `src/common/` as the home for truly shared deterministic helpers
- keep `src/prompts/` as the home for shared and cross-step prompt material
- keep temporary compatibility wrappers only until the new step folders are fully proven, but do not let the active runtime for completed Step 4 subphases depend on `script_*`
- delete the old script-era step files in Step 6 after the refactor is verified end to end

This means the active step coverage should include:

- step `1`, including the PDF intake path
- step `2.1`
- step `2.2`
- step `3.1`
- step `3.2`
- step `4.1`
- step `5.1`

For step `3.1`, the end-state code should make the three internal actions clearly visible:

- `draft_expert_a`
- `draft_expert_b`
- `merge_expert_drafts`

For step `3.2`, the end-state code should make the three internal actions clearly visible:

- `run_evaluator_review`
- `run_creator_review`
- `recreate_revised_ruleset`

As part of Step 4, steps that have substantial deterministic logic should prefer:

- `procedural.py`
- `verification.py`

instead of one combined `deterministic.py`.

Recommended interpretation:

- `procedural.py` handles deterministic file creation, path-driven transformations, and structured non-LLM processing
- `verification.py` handles deterministic validation, consistency checks, and output verification

Smaller steps do not need this split if it would create empty or trivial files.

Status:

- partially completed

Current implementation state:

- active step folders now exist for:
  - `step_1_1_fetch`
  - `step_1_2_parse_award`
  - `step_2_1_classify_payments`
  - `step_2_2_classify_overtime_clauses`
  - `step_3_1_generate_ruleset`
  - `step_3_2_review_ruleset`
  - `step_4_1_format_ruleset`
  - `step_5_1_generate_pseudocode`
- the active runtime and Streamlit entrypoints now route through those step folders
- the active runtime still depends on several `script_*` files for later, not-yet-migrated steps
- the target state for Step `4.3` onward is stricter than the current state: once those subphases are completed, their active runtime should no longer import `script_*` files
- deleting those `script_*` files belongs to Step 6 after the logic has been moved fully into the step folders

Active step numbering now follows:

1. `1.1` fetch
2. `1.2` parse
3. `2.1` payment classification
4. `2.2` overtime clause classification
5. `3.1` ruleset generation
6. `3.2` ruleset review
7. `4.1` ruleset formatting
8. `5.1` pseudocode generation

### Phase 5. Move all active prompts into dedicated prompt files

Review every active step and remove any remaining embedded prompt text or prompt-like workflow prose from scripts.

Each step should have:

- one main prompt module
- one obvious builder entrypoint
- no duplicate prompt APIs for the same active task
- No files should have prompts embedded in the code

All prompts shoudl be in the /prompts/ files

Status:

- not started



### Phase 6. Update tests and Streamlit to the new structure

Tests should prove:

- step-numbered outputs are written consistently
- overtime clause classification can run independently of ruleset drafting
- rulesets stay separated all the way through downstream outputs
- Streamlit reads the canonical active artifacts only
- deterministic and LLM layers interact through stable contracts

Streamlit should stop acting as a migration layer.

This phase is for proving and enforcing the output naming and folder behaviour in tests and UI reads.
It is not the phase where canonical output folders are first introduced.

The Streamlit sidebar should have distinct run controls for:

- step `2.1` payment classification
- step `2.2` overtime clause classification
- step `3.1` ruleset drafting
- step `3.2` ruleset review

Status:

- not started

### Phase 7. Delete legacy wrappers and fallback-heavy path logic

Once the new structure works, remove:

- old script aliases that no longer matter
- legacy overtime-only path branches
- multi-path fallback chains that only exist for old artifacts
- duplicate helper names kept for compatibility

perform an additional scan to ensure all legacy code are removed, and doing another scan of the complexity to identy any areas to simplify. 

This is the step where complexity should drop sharply.

Status:

- not started


### Phase 8. Update docs and remove dead content

After the code is stable:

- update `README.md`
- update technical and methodology notes
- update output inventories
- Archieve old files which are no longer used in the current process
- remove or archive old documentation that describes the retired architecture

At that point, the repository should describe only one active workflow.

Completing the planning and naming decisions in this document counts as finishing Step 1 of the simplification plan.

Status:

- not started

## Immediate priorities from the current codebase

Based on the current repo, the highest-value simplification targets are:

1. Replace mixed path logic in `src/award_pipeline.py`, `src/common/active_pipeline_paths.py`, and downstream steps with one canonical naming layer.
2. Move `src/script_3_part1_classify_overtime_clauses.py` into the step-2 area and expose it as its own operator-visible step.
3. Shrink step `3.1`, step `3.2`, and step `5.1` first because they currently carry the most mixed responsibility and compatibility naming.
4. Keep prompt ownership explicit and continue moving prompt text toward `src/prompts/` only.
5. Move only truly repeated helpers into `src/common/`; do not create a generic abstraction layer.
6. Delete legacy output support aggressively once the new canonical paths are in place.

## Rule for future changes

When a script starts becoming hard to explain, ask three questions:

1. Is this prompt text and should it live in `src/prompts/`?
2. Is this repeated deterministic logic and should it live in `src/common/`?
3. Is this legacy compatibility and should it be deleted instead of preserved?

If we follow that rule consistently, the codebase should stay understandable.
