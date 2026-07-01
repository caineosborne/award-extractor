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
- overtime clause classification moved into step 2 instead of being bundled into ruleset drafting

The target reader is not just a developer. A reviewer should be able to see:

- what step ran
- what file it read
- what file it wrote
- what prompt was used
- what deterministic checks were applied

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
- `src/1_1_fetch/`
- `src/1_2_parse_award/`
- `src/2_classify_payments/`
- `src/2_1_classify_overtime_clauses/`
- `src/3_1_generate_ruleset/`
- `src/3_2_review_ruleset/`
- `src/4_1_format_ruleset/`
- `src/5_1_generate_pseudocode/`
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

- `src/prompts/2_payment_classification.py`
- `src/prompts/2_1_overtime_clause_classification.py`
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

`<award_code>_<step>_<ruleset_if_any>_<artifact>.ext`

Examples:

- `MA000120_1_1_raw.html`
- `MA000120_1_2_award.json`
- `MA000120_2_payment_classification.json`
- `MA000120_2_1_overtime_creation_clause_classification.json`
- `MA000120_3_1_overtime_creation_ruleset.md`
- `MA000120_3_2_overtime_creation_ruleset_review.md`
- `MA000120_3_2_overtime_creation_ruleset_revised.md`
- `MA000120_4_1_overtime_creation_formatted_ruleset.md`
- `MA000120_5_1_overtime_creation_pseudocode.md`
- `MA000120_5_1_overtime_creation_pseudocode_validation.json`

This gives us immediate traceability:

- the step that wrote the file
- whether it is LLM or deterministic output
- which ruleset it belongs to

### 7. Remove legacy behaviour instead of preserving it

The current codebase has too many compatibility layers, fallback paths, and duplicate names.

The simplification direction should be:

- keep only the active workflow
- delete legacy artifacts and legacy naming support
- keep compatibility shims only if they are tiny and temporary

Specifically, reduce:

- old overtime-only path inference
- fallback-first downstream file selection
- duplicate helper aliases
- wrapper scripts that exist only to preserve an old concept

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

- payment clause classification remains step `2`
- overtime clause classification becomes step `2.1`
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
  1_1_fetch/
    run.py
    deterministic.py
    io.py
  1_2_parse_award/
    run.py
    deterministic.py
    io.py
  2_classify_payments/
    run.py
    llm.py
    deterministic.py
    io.py
  2_1_classify_overtime_clauses/
    run.py
    llm.py
    deterministic.py
  3_1_generate_ruleset/
    run.py
    llm.py
    deterministic.py
  3_2_review_ruleset/
    run.py
    llm.py
    deterministic.py
  4_1_format_ruleset/
    run.py
    llm.py
    deterministic.py
  5_1_generate_pseudocode/
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
    2_payment_classification.py
    2_1_overtime_clause_classification.py
    3_1_overtime_ruleset_generation.py
    3_2_ruleset_review.py
    4_1_ruleset_formatting.py
    5_1_pseudocode_generation.py
```

## Implementation plan

This should be done in 8 steps.

### Step 1. Freeze the target naming scheme

Decide the canonical step labels and artifact descriptors once.

Deliverables:

- one filename standard for all active outputs
- one folder naming standard for `src/`
- one ruleset naming standard

Notes:

- this should be decided before moving files
- output naming should be treated as the source of truth for downstream logic

### Step 2. Introduce one shared deterministic pipeline context

Create one shared context object in `src/common/` that resolves:

- award code
- selected steps
- selected ruleset
- input paths
- output paths
- archive paths

This replaces repeated path inference across scripts.

This context should treat overtime clause classification as a first-class step between payment classification and ruleset drafting.

### Step 3. Move output naming into one helper module

Create one deterministic output naming module that every step uses.

That module should build:

- current output file paths
- archive file paths
- related review and validation artifact paths

After this step, no active script should hand-build filenames inline.

This helper should explicitly build separate output paths for:

- step `2` payment classification
- step `2.1` overtime clause classification
- step `3.1` ruleset draft
- step `3.2` review and revised ruleset

### Step 4. Split step files into `run`, `llm`, and `deterministic`

Refactor the current long scripts so each step has a small number of clear files.

Priority order:

- step 2.1 overtime clause classification
- step 3 ruleset review and generation
- step 5 pseudocode
- step 2 classification
- step 1 fetch/parse

This order gives the biggest readability gain first.

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

### Step 5. Move all active prompts into dedicated prompt files

Review every active step and remove any remaining embedded prompt text or prompt-like workflow prose from scripts.

Each step should have:

- one main prompt module
- one obvious builder entrypoint
- no duplicate prompt APIs for the same active task

### Step 6. Delete legacy wrappers and fallback-heavy path logic

Once the new structure works, remove:

- old script aliases that no longer matter
- legacy overtime-only path branches
- multi-path fallback chains that only exist for old artifacts
- duplicate helper names kept for compatibility

This is the step where complexity should drop sharply.

### Step 7. Update tests and Streamlit to the new structure

Tests should prove:

- step-numbered outputs are written consistently
- overtime clause classification can run independently of ruleset drafting
- rulesets stay separated all the way through downstream outputs
- Streamlit reads the canonical active artifacts only
- deterministic and LLM layers interact through stable contracts

Streamlit should stop acting as a migration layer.

The Streamlit sidebar should have distinct run controls for:

- step `2` payment classification
- step `2.1` overtime clause classification
- step `3.1` ruleset drafting
- step `3.2` ruleset review

### Step 8. Update docs and remove dead content

After the code is stable:

- update `README.md`
- update technical and methodology notes
- update output inventories
- remove or archive old documentation that describes the retired architecture

At that point, the repository should describe only one active workflow.

Completing the planning and naming decisions in this document counts as finishing Step 1 of the simplification plan.

## Immediate priorities from the current codebase

Based on the current repo, the highest-value simplification targets are:

1. Replace mixed path logic in `src/award_pipeline.py`, `src/common/active_pipeline_paths.py`, and downstream steps with one canonical naming layer.
2. Move `src/script_3_part1_classify_overtime_clauses.py` into the step-2 area and expose it as its own operator-visible step.
3. Shrink step `3`, step `3B`, and step `5B` first because they currently carry the most mixed responsibility and compatibility naming.
4. Keep prompt ownership explicit and continue moving prompt text toward `src/prompts/` only.
5. Move only truly repeated helpers into `src/common/`; do not create a generic abstraction layer.
6. Delete legacy output support aggressively once the new canonical paths are in place.

## Rule for future changes

When a script starts becoming hard to explain, ask three questions:

1. Is this prompt text and should it live in `src/prompts/`?
2. Is this repeated deterministic logic and should it live in `src/common/`?
3. Is this legacy compatibility and should it be deleted instead of preserved?

If we follow that rule consistently, the codebase should stay understandable.
