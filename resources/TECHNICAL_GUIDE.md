# Award Extractor Technical Guide

This document is the technical reference for the active pipeline.

Use it when you need to know:
- which step folder owns a stage;
- what goes into each LLM call;
- what comes out of each LLM call;
- which JSON schema is expected;
- which deterministic validations run before an artifact is accepted or written.

For business purpose and review intent, use `resources/METHODOLOGY.md`.

## Scope

Active default pipeline:
- Step `1`
- Step `2.1`
- Step `2.2`
- Step `3.1`
- Step `3.2`
- Step `4.1`
- Step `4.9`
- Step `5.1`

Primary orchestrator:
- `src/award_pipeline.py`

Primary shared helpers:
- `src/common/active_pipeline_paths.py`
- `src/common/output_paths.py`
- `src/common/pipeline_io.py`
- `src/common/pipeline_runtime.py`
- `src/common/llm_io.py`
- `src/common/overtime_rules.py`
- `src/common/rule_inventory.py`

## Pipeline Map

| Step | Owner | LLM? | Primary output |
| --- | --- | --- | --- |
| 1 | `src/step_1_1_fetch/run.py`, `src/step_1_2_parse_award/run.py` | No | Structured award JSON |
| 2.1 | `src/step_2_1_classify_payments/run.py` | Yes | Payment clause classification JSON |
| 2.2 | `src/step_2_2_classify_overtime_clauses/run.py` | Yes | Overtime clause classification JSON |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Yes | Expert rule-set JSON/MD and comparison JSON |
| 3.2 | `src/step_3_2_review_ruleset/run.py` | Yes | Evaluator feedback JSON/MD, creator response JSON/MD, revised interpretation JSON/MD |
| 4.1 | `src/step_4_1_format_ruleset/run.py` | Yes | Formatted overtime guide MD |
| 4.9 | `streamlit_review/app.py`, `streamlit_review/output_data.py` | No | Human-reviewed ruleset MD |
| 5.1 | `src/step_5_1_generate_pseudocode/run.py` | Yes | Pseudocode MD |
| 5.1 validation | `src/step_5_1_generate_pseudocode/verification.py` | No | Validation JSON/MD |

## Step 1. Fetch And Structure Award

Owner:
- `src/step_1_1_fetch/run.py`
- `src/step_1_2_parse_award/run.py`

LLM calls:
- none

Deterministic inputs:
- Fair Work award URL

Deterministic processing:
- fetch HTML;
- isolate award `mainContent`;
- normalise headings, bullets, paragraphs, and tables;
- build nested award JSON;
- build supporting section-index and heading-summary outputs.

Deterministic validations:
- source file must be reachable;
- parsed structure must be serialisable to output artifacts.

Primary outputs:
- `1_1_raw.html`
- `1_2_award.json`
- supporting section index JSON
- supporting heading CSV

## Step 2.1. Payment Clause Classification

Owner:
- `src/step_2_1_classify_payments/run.py`

Prompt:
- `src/prompts/step_2_1_classify_payments.py`

Unit of work:
- one model call per top-level clause group.

Each group contains:
- one top-level clause;
- its direct `L2` descendants;
- the flattened text of each descendant subtree.

LLM call:
- structured JSON response

Required response shape:
- `top_level_clause`
- `classified_clauses`

Deterministic checks before accepting a model response:
- returned top-level reference must equal the clause group sent;
- returned classified clause references must map to a real direct `L2` clause or to an allowed nested descendant of one direct `L2` clause;
- non-relevant top-level clauses must not also return classified children;
- duplicate direct-`L2` results are merged in a controlled way, with reasons combined;
- title-only top-level clauses can be resolved deterministically without a model call.

Deterministic post-processing:
- explicit overtime wording may add `Ordinary Hours & Overtime`;
- the repair is written to `deterministic_tag_adjustments`.

## Step 2.2. Overtime Clause Classification

Owner:
- `src/step_2_2_classify_overtime_clauses/run.py`

Prompt:
- `src/prompts/step_2_2_classify_overtime_clauses.py`

Deterministic pre-filter:
- input artifact is the step-2.1 payment classification JSON;
- shortlist rule keeps clauses tagged `Ordinary Hours & Overtime`.

LLM call:
- structured JSON response

Required response shape:
- `clauses`

Allowed classifications:
- `Ordinary Hours Boundary`
- `Overtime Trigger`
- `Overtime Consequence`
- `Related Rule`
- `Not Relevant`

Allowed scope values:
- `employee_cohort`: values from `ALLOWED_EMPLOYEE_COHORTS`
- `work_arrangement`: values from `ALLOWED_WORK_ARRANGEMENTS`

Deterministic validation:
- every returned clause number must have been shortlisted;
- no duplicates;
- every shortlisted clause must be classified;
- primary `classification` must also appear inside `classifications`;
- all classifications must be from the allowed set;
- `explanation` must be non-empty;
- `employee_cohort` must be allowed;
- `work_arrangement` must be allowed.

Deterministic scope normalisation:
- keep `day-worker` only where the clause text expressly supports day-worker language;
- keep `shiftworker` only where the clause text expressly supports shiftworker or shiftwork language;
- otherwise save `all`.

Deterministic filter for downstream generation:
- step `3.1` keeps only classifications containing `Ordinary Hours Boundary` or `Overtime Trigger`.

## Step 3.1. Overtime Ruleset Generation

Owner:
- `src/step_3_1_generate_ruleset/run.py`

Prompt:
- `src/prompts/step_3_1_generate_ruleset.py`

Expert generation:
- the active pipeline uses two expert runs;
- each expert receives the shortlisted step-2.2 clauses and the same interpretation prompt;
- each expert returns a structured rule set.

Deterministic validation:
- each expert run must produce a structurally valid rule list;
- the comparison output must produce a structurally valid merged rule list;
- all expert A rule IDs and expert B rule IDs must be accounted for;
- shortlisted source clauses must still be represented in the merged rules;
- scope warnings are re-run on merged rules.

Saved step-3.1 artifacts:
- expert A markdown and JSON
- expert B markdown and JSON
- comparison JSON
- combined ruleset markdown and JSON

## Step 3.2. Review And Revise Ruleset

Owner:
- `src/step_3_2_review_ruleset/run.py`

Prompt:
- `src/prompts/step_3_2_review_ruleset.py`

LLM call:
- evaluator structured review
- creator structured response

Required evaluator response shape:
- `summary_markdown`
- `rule_reviews`
- `new_rules`

Deterministic validation:
- every original `rule_id` must be explicitly addressed;
- rules must not be silently dropped;
- removals must be supported by the review record;
- additions must not be silently introduced;
- additions are only applied where the tracked evaluator and creator records agree;
- the revised ruleset is rebuilt from structured creator decisions rather than free-text creator prose;
- clause-coverage reductions can be surfaced as warnings.

Saved step-3.2 artifacts:
- evaluator feedback markdown and JSON
- creator response markdown and JSON
- revised overtime interpretation markdown and JSON

## Step 4.1. Formatted Overtime Guide

Owner:
- `src/step_4_1_format_ruleset/run.py`

Prompt:
- `src/prompts/step_4_1_format_ruleset.py`

Purpose:
- turn the revised interpretation artifact into a cleaner human-readable overtime guide;
- prefer the revised step `3.2` interpretation when an award code is used;
- use `resources/Templates/Template.md` as a formatting and heading reference;
- omit unsupported template headings entirely rather than emitting placeholder text;
- ignore the validation-notes preamble from the source interpretation and format only the actual rules.

## Step 5.1. Core Overtime Pseudocode

Owner:
- `src/step_5_1_generate_pseudocode/run.py`

Prompt:
- `src/prompts/step_5_1_generate_pseudocode.py`

Purpose:
- generate implementation-oriented ordinary/overtime pseudocode from the latest available interpretation source;
- prefer the step `4.9` human-review ruleset file, then `4.1`, then revised `3.2`, then the earlier reviewed interpretation;
- validate the generated pseudocode deterministically against a rule inventory built from the source interpretation.

Validation files:
- `src/step_5_1_generate_pseudocode/verification.py`

## Step 4.9. Human Review Ruleset

Owner:
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

Purpose:
- allow an operator to save a human-reviewed ruleset working file after step `4.1`;
- keep that file in the canonical award folder;
- make that file the first-choice source for step `5.1` when it exists.

Primary artifact:
- `3_2_OT_<ruleset>_revised_ruleset_manual.md`

## Streamlit Review Surface

The Streamlit review application is part of the active operational surface.

Current modules:
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`
- `streamlit_review/pipeline_runs.py`

Current behaviour:
- discover existing award output sets from canonical `2_1_payment_classification.json` files;
- run the active pipeline or selected steps for an award code;
- compare intermediate and final artifacts side by side;
- expose reviewer-facing screens for the canonical active outputs only;
- do not expose the parked agentic review conversation as part of the active surface.
