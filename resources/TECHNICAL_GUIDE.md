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

Active rulesets from step `2.2` onward:
- `overtime_creation`
- `overtime_consequence`
- `penalties`

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
- `src/common/overtime_rulesets.py`
- `src/common/rule_inventory.py`
- `src/common/output_naming.py`

## Pipeline Map

| Step | Owner | LLM? | Primary output |
| --- | --- | --- | --- |
| 1 | `src/step_1_1_fetch/run.py`, `src/step_1_2_parse_award/run.py` | No | Structured award JSON |
| 2.1 | `src/step_2_1_classify_payments/run.py` | Yes | Payment clause classification JSON |
| 2.2 | `src/step_2_2_classify_overtime_clauses/run.py` | Yes for overtime rulesets, No for penalties | Ruleset clause classification JSON |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Yes | Expert rule-set JSON/MD and comparison JSON |
| 3.2 | `src/step_3_2_review_ruleset/run.py` | Yes | Evaluator feedback JSON/MD, creator response JSON/MD, revised interpretation JSON/MD |
| 4.1 | `src/step_4_1_format_ruleset/run.py` | Yes | Formatted ruleset guide MD |
| 4.9 | `streamlit_review/app.py`, `streamlit_review/output_data.py` | No | Human-reviewed ruleset MD |
| 5.1 | `src/step_5_1_generate_pseudocode/run.py` | Yes | Pseudocode MD |
| 5.1 validation | `src/step_5_1_generate_pseudocode/verification.py` | No | Validation JSON/MD |

## Prompt Construction Pattern

The active prompt layer is intentionally split so shared ruleset framing can be reused consistently across steps without forcing every prompt into overtime wording.

Where a step uses an LLM, the prompt is built from these layers:
- generic call instructions for the current payroll task type;
- reusable ruleset checks from `src/prompts/overtime_common_prompt_blocks.py`;
- step-specific instructions from the step prompt module;
- the current payload, such as shortlisted clauses, reviewed markdown, or rule inventory text.

In practice:
- step `2.2` uses a generic classifier frame plus a ruleset-specific question block, although the penalties runtime path is deterministic;
- step `3.1` uses generic drafting instructions, reusable ruleset checks, and then ruleset-specific drafting instructions;
- step `3.2` uses a small subset overlay from `src/prompts/step_3_2_prompt_config.py` so review wording stays ruleset-aware;
- step `4.1` uses a shared formatting frame plus ruleset-specific heading and scope instructions;
- step `5.1` uses a shared pseudocode system template plus ruleset-specific goals, constraints, and mode instructions.

This is the main mechanism that keeps penalties prompt content parallel to the overtime rulesets while preventing silent fallback to overtime semantics.

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

The non-overtime tags used downstream by the penalties ruleset remain model-generated:
- `Penalty`
- `Breaks (Between Work Periods)`

## Step 2.2. Ruleset Clause Classification

Owner:
- `src/step_2_2_classify_overtime_clauses/run.py`

Prompt:
- `src/prompts/step_2_2_classify_overtime_clauses.py`

Deterministic pre-filter:
- input artifact is the step-2.1 payment classification JSON;
- shortlist rule depends on the selected ruleset from `src/common/overtime_rulesets.py`.

Ruleset shortlist sources:
- `overtime_creation`: clauses tagged `Ordinary Hours & Overtime`
- `overtime_consequence`: clauses tagged `Ordinary Hours & Overtime`
- `penalties`: clauses tagged `Penalty` or `Breaks (Between Work Periods)`

LLM call for overtime creation and overtime consequence:
- structured JSON response

Required response shape:
- `clauses`

Allowed classifications:
- `Ordinary Hours Boundary`
- `Overtime Trigger`
- `Overtime Consequence`
- `Related Rule`
- `Not Relevant`

Allowed classification for penalties:
- `Penalty Rule`

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
- `overtime_creation`: step `3.1` keeps only classifications containing `Ordinary Hours Boundary` or `Overtime Trigger`
- `overtime_consequence`: step `3.1` keeps only classifications containing `Overtime Consequence`
- `penalties`: step `3.1` keeps all deterministically shortlisted `Penalty Rule` clauses

Penalties-specific deterministic behaviour:
- no LLM call is made;
- every shortlisted clause is written as `Penalty Rule`;
- the explanation states whether the shortlist came from `Penalty`, `Breaks (Between Work Periods)`, or both;
- employee cohort and work arrangement are inferred conservatively from express clause text only.

## Step 3.1. Ruleset Generation

Owner:
- `src/step_3_1_generate_ruleset/run.py`

Prompt:
- `src/prompts/step_3_1_generate_ruleset.py`

Expert generation:
- the active pipeline uses two expert runs;
- each expert receives the shortlisted step-2.2 clauses and the same interpretation prompt;
- each expert returns a structured rule set.

Ruleset-specific drafting notes:
- `overtime_creation` drafts only rules that cause time to become overtime;
- `overtime_consequence` drafts only rules that apply once overtime already exists;
- `penalties` drafts premium-pay and supporting break-gap rules, keeping whole-shift, specific-hours, day-type, and non-financial supporting rules separate where supported.

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

Prompt overlay:
- subset-specific review wording comes from `src/prompts/step_3_2_prompt_config.py`
- the overlay sets the review question and additional scope notes for the selected ruleset

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
- revised ruleset markdown and JSON

For penalties, the review overlay explicitly:
- keeps supporting break-gap rules in scope even without direct pay;
- removes overtime-only drafting drift unless the clause expressly creates a penalties-domain rule.

## Step 4.1. Formatted Ruleset Guide

Owner:
- `src/step_4_1_format_ruleset/run.py`

Prompt:
- `src/prompts/step_4_1_format_ruleset.py`

Purpose:
- turn the revised interpretation artifact into a cleaner human-readable ruleset guide;
- prefer the revised step `3.2` interpretation when an award code is used;
- use `resources/Templates/Template.md` as a formatting and heading reference;
- omit unsupported template headings entirely rather than emitting placeholder text;
- ignore the validation-notes preamble from the source interpretation and format only the actual rules.

Ruleset-specific formatting:
- `overtime_creation` uses overtime-trigger headings;
- `overtime_consequence` uses overtime-consequence headings;
- `penalties` uses penalties headings including shift-based penalties, time-band/day-based penalties, breaks between work periods, and supporting conditions.

## Step 5.1. Ruleset Pseudocode

Owner:
- `src/step_5_1_generate_pseudocode/run.py`

Prompt:
- `src/prompts/step_5_1_generate_pseudocode.py`

Purpose:
- generate implementation-oriented pseudocode from the latest available interpretation source;
- prefer the step `4.9` human-review ruleset file, then `4.1`, then revised `3.2`, then the earlier reviewed interpretation;
- validate the generated pseudocode deterministically against a rule inventory built from the source interpretation.

Validation files:
- `src/step_5_1_generate_pseudocode/verification.py`

Ruleset-specific mode handling:
- `overtime_creation` classifies ordinary versus overtime hours;
- `overtime_consequence` applies consequence outputs after overtime already exists;
- `penalties` applies explicit penalty outputs and may include supporting break-gap checks or implementation notes without forcing a premium outcome.

## Step 4.9. Human Review Ruleset

Owner:
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

Purpose:
- allow an operator to save a human-reviewed ruleset working file after step `4.1`;
- keep that file in the canonical award folder;
- make that file the first-choice source for step `5.1` when it exists.

Primary artifact:
- `3_2_<ruleset-short-label>_revised_ruleset_manual.md`

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
- support ruleset-specific artifact loading for overtime creation, overtime consequence, and penalties;
- do not expose the parked agentic review conversation as part of the active surface.
