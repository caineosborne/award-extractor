# Award Extractor Methodology

This document explains how the current pipeline works.

It is about system behaviour, not operator instructions. For commands, file-by-file outputs, and code-reading notes, use `resources/TECHNICAL_GUIDE.md`.

## Purpose

The project turns award source material into reviewable overtime interpretation artifacts.

It does not try to produce a payroll engine result in one step. Instead, it narrows the source material progressively and leaves an audit trail at each stage.

The active path is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Generate an overtime interpretation.
4. Review and revise that interpretation.

In code, those are steps `1`, `2`, `3`, and `3B`.

## Design principles

The pipeline separates three kinds of work:

- Deterministic parsing, filtering, path resolution, rendering, and validation.
- Structured LLM generation when a machine-readable artifact is required.
- Review-oriented LLM feedback when a later human or model step needs critique rather than a hard classification.

The governing design choices are:

- deterministic code should do everything it can do reliably;
- LLM outputs should be structured when downstream code depends on them;
- each stage should have a narrow purpose;
- each important stage should leave an artifact that can be reviewed independently;
- later steps should preserve traceability back to earlier source clauses.

## Step 1. Fetch and structure the award

File:
- `src/script_1_fetch_award.py`

This step is deterministic.

Input:
- a Fair Work award URL such as `https://awards.fairwork.gov.au/MA000018.html`

Process:
- fetch the award HTML;
- isolate the `mainContent` section;
- normalise headings, text blocks, bullets, and tables;
- build a nested JSON representation of the award;
- build a section index JSON;
- build a flat heading CSV for human review.

Outputs:
- raw HTML snapshot;
- structured award JSON;
- supporting section index JSON;
- supporting heading CSV;
- timestamped archive copies for the JSON and supporting artifacts.

The main award JSON is the only step-1 artifact required by the active downstream pipeline. The supporting files exist for review and lookup rather than for later pipeline execution.

No model is used here. Every later step depends on this extraction being structurally correct.

## Step 2. Payment clause classification

Files:
- `src/script_2_classify_payments.py`
- `src/prompts/payment_clause_classification.py`

Purpose:
- identify which top-level clauses are relevant to payment or definitional logic;
- classify the direct `L2` clauses that matter for downstream overtime work.

The unit of work is one top-level clause group at a time. This keeps model calls smaller and makes it easier to trace a result back to the source clause group that produced it.

### What the model does

The model receives:
- one top-level clause;
- its direct `L2` descendants.

It returns strict JSON containing:
- the top-level relevance decision;
- the direct `L2` classification results.

### Deterministic behaviour around the model

The code also makes some decisions without a model call. For example, top-level clauses with no substantive direct `L2` children can be marked non-relevant deterministically.

### Validation in Step 2

There are two layers of validation:

1. API-level structured output:
- the model must return schema-conforming JSON.

2. Python-side validation:
- the returned top-level reference must match the clause group that was sent;
- returned clause references must map back to real direct `L2` clauses;
- non-relevant top-level clauses must not also return classified children.

If validation fails, the step fails.

### Why Step 2 exists

This step narrows the award to the subset that is likely to matter for payment logic. It does not yet attempt to explain overtime.

## Step 3. Overtime interpretation generation

File:
- `src/script_3_interpret_overtime.py`
- `src/script_3_part1_classify_overtime_clauses.py`
- `src/script_3_part2_generate_overtime_interpretation.py`

This step has several sub-stages.

Implementation note:
- `src/script_3_interpret_overtime.py` remains the stable public entrypoint.
- It now delegates to two clearer internal scripts:
  - part 1 prepares `*_overtime_clause_classification.json`;
  - part 2 reads that artifact and produces the expert outputs, comparison, and combined ruleset.

### Step 3.1. Filter overtime-related clauses

This is deterministic.

From the step-2 classification artifact, the code selects clauses tagged:
- `Ordinary Hours & Overtime`

This creates the source pool for overtime-specific work.

### Step 3.2. Overtime clause classification

The model now receives only the shortlisted clauses from step `3.1`.

Its job is to classify each clause into one or more of:
- `Ordinary Hours Boundary`
- `Overtime Trigger`
- `Overtime Consequence`
- `Related Rule`
- `Not Relevant`

The output is strict structured JSON.

This classification separates:
- clauses that create overtime;
- clauses that describe consequences after overtime already exists;
- related clauses that give context but do not create overtime themselves.

### Validation in Step 3.2

The code checks:
- every returned clause number was actually sent;
- there are no duplicates;
- every input clause was classified;
- the classifications are from the allowed set;
- the explanation field is present.

If those checks fail, the step fails.

### Step 3.3. Filter to overtime-creation clauses

This is deterministic.

The code keeps only clauses whose classifications contain:
- `Ordinary Hours Boundary`
- or `Overtime Trigger`

Those are treated as the creation-oriented clauses for rule generation.

### Step 3.4. Dual expert generation

The active pipeline uses two independent expert runs rather than one generation pass.

Each expert receives:
- the shortlisted step-`3.3` clauses;
- the same interpretation prompt.

Each expert returns a structured rule set. Each rule includes fields such as:
- `rule_id`
- `section_heading`
- `employee_scope`
- `clause_references`
- `rule_markdown`
- `rule_plain_text`
- `source_clause_numbers`
- `source_classifications`

The purpose of the second run is not to average the answer. It is to expose omissions, over-grouping, or interpretive differences that might be hidden if only one run were stored.

### Expert comparison and merge

After the two expert runs, a comparison model receives:
- the shortlisted source clauses;
- expert A rules;
- expert B rules.

It returns:
- a comparison summary;
- coverage of the expert A rule IDs;
- coverage of the expert B rule IDs;
- a merged structured rule set;
- merge explanations linking merged rules back to expert A and expert B.

The merged result becomes the canonical step-3 interpretation artifact.

### Validation in Step 3.4

Validation here has three layers:

1. each expert run must produce a structurally valid rule list;
2. the comparison output must produce a structurally valid merged rule list;
3. deterministic checks confirm that:
- all expert A rule IDs were accounted for;
- all expert B rule IDs were accounted for;
- shortlisted source clauses are still represented in the merged rules.

Some issues are non-fatal by design. When the artifact is still usable, warnings are written into the JSON and prepended to the markdown instead of stopping the run.

### What Step 3 produces

Conceptually, step `3` produces:
- an overtime clause-classification artifact;
- two expert interpretation variants;
- a comparison artifact explaining the merge;
- one canonical overtime interpretation in JSON and markdown.

## Step 3B. Supervisor review and revision

File:
- `src/script_3b_review_overtime_interpretation.py`

Step `3B` reviews the step-3 interpretation rather than re-extracting from scratch.

It uses:
- the step-2 payment classification JSON;
- the step-3 overtime clause-classification JSON;
- the step-3 interpretation JSON and markdown.

### Evaluator role

The evaluator acts as a supervisor. It identifies:
- clause-classification issues;
- interpretation issues;
- presentation issues;
- traceability issues.

Its preferred machine contract is structured JSON with:
- `summary_markdown`
- `rule_reviews`
- `new_rules`

A human-readable markdown feedback artifact is also written.

### Creator role

The creator receives:
- the original interpretation;
- the evaluator feedback;
- the original step-3 rules JSON.

Its job is to return explicit rule-level decisions. This is important because the revision step is meant to show what changed and why, not silently replace the earlier interpretation.

### Validation in Step 3B

The code validates that:
- every original `rule_id` was explicitly addressed;
- rules are not silently dropped;
- removals are supported by the review record;
- clause-coverage reductions can be surfaced as warnings.

If structured creator output cannot be applied safely, the earlier interpretation is preserved and the workflow records the issue for manual review.

### What Step 3B produces

The main active endpoint of the project is the reviewed interpretation set:
- evaluator feedback markdown and JSON;
- creator response markdown and JSON;
- revised overtime interpretation markdown and JSON.

## Step 4A. Formatted overtime guide

File:
- `src/script_4a_summarize_overtime.py`

This step is retained and maintained, but it is not part of the current default manager-review pipeline.

Purpose:
- turn the interpretation artifact into a cleaner human-readable overtime guide;
- prefer the revised `3B` interpretation when an award code is used;
- use `resources/Template.md` as a formatting and heading reference.
- omit unsupported template headings entirely rather than emitting placeholder text.
- ignore the validation-notes preamble from the source interpretation and format only the actual rules.

This is a presentation step. The template is not source evidence.

## Step 5B. Core overtime pseudocode

Files:
- `src/script_5b_generate_overtime_pseudocode.py`
- `src/script_5b_validate_overtime_pseudocode.py`

This step is also retained and maintained outside the default manager-review path.

Purpose:
- generate implementation-oriented ordinary/overtime pseudocode from the latest available interpretation source;
- prefer manual `4B`, then `4A`, then revised `3B`, then original `3`;
- validate the generated pseudocode deterministically against a rule inventory built from the source interpretation.

This step mixes free-text generation with hard deterministic post-generation checks.

## Streamlit review application

Files:
- `review_outputs.py`
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

The Streamlit app is part of the working methodology because it is the review surface for generated artifacts.

Its role is:
- discover existing award output sets;
- run the active pipeline or selected steps for an award code;
- compare intermediate and final artifacts side by side;
- expose reviewer-facing screens for payment clauses, payment clause categories, ruleset clause classification, expert drafts, comparison output, combined ruleset, reviewer commentary, final formatted ruleset, manual edited ruleset, and pseudocode;
- support a manual `4B` editing workflow by saving edited markdown with archive copies.

This matters because the project does not treat the pipeline as purely batch output. Review, comparison, and manual refinement are part of the current operating method.

## End-to-end interpretation

The easiest way to understand the system is:

1. Step `1` creates a deterministic source record.
2. Step `2` narrows the award to payment-relevant material.
3. Step `3.2` classifies overtime-related clauses by role.
4. Step `3.3` narrows again to overtime-creation clauses.
5. Step `3.4` generates two independent structured interpretations.
6. A comparison pass merges those into one canonical interpretation.
7. Step `3B` critiques and revises that interpretation with explicit rule-level decisions.

So the method is not "one model reads the award and answers."

It is:
- deterministic source extraction;
- structured narrowing;
- structured role classification;
- dual expert generation;
- comparison and merge;
- supervised revision;
- optional later formatting and implementation-oriented generation.
