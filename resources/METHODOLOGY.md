# Award Extractor Methodology

This document explains how the current pipeline works at a business and review-method level.

It is intentionally not the low-level implementation reference.

Use:
- `resources/TECHNICAL_GUIDE.md` for exact LLM inputs and outputs, JSON schemas, and deterministic validation logic;
- `resources/outputs.md` for filenames and output locations.

## Purpose

The project turns award source material into reviewable overtime interpretation artifacts.

It does not try to produce a payroll engine result in one step. Instead, it narrows the source material progressively and leaves an audit trail at each stage.

The active path is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Classify overtime clauses, draft rulesets, and review the revised interpretation.
4. Format the reviewed ruleset for reviewer-facing output.
5. Generate implementation-oriented pseudocode.

In code, those are steps `1`, `2.1`, `2.2`, `3.1`, `3.2`, `4.1`, and `5.1`.

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

Files:
- `src/step_1_1_fetch/run.py`
- `src/step_1_2_parse_award/run.py`

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

## Step 2.1. Payment clause classification

Files:
- `src/step_2_1_classify_payments/run.py`
- `src/prompts/step_2_1_classify_payments.py`

Purpose:
- identify which top-level clauses are relevant to payment or definitional logic;
- classify the direct `L2` clauses that matter for downstream overtime work.

The unit of work is one top-level clause group at a time. This keeps model calls smaller and makes it easier to trace a result back to the source clause group that produced it.

### What the model does

The model receives:
- one top-level clause;
- its direct `L2` descendants.

It returns a structured classification result containing:
- the top-level relevance decision;
- the direct `L2` classification results.

### Deterministic behaviour around the model

The code also makes some decisions without a model call. For example, top-level clauses with no substantive direct `L2` children can be marked non-relevant deterministically.

The active step-2 flow also includes a deterministic post-classification repair layer for explicit overtime-trigger wording. This exists to catch model misses where a clause clearly creates or references overtime in operative text but the returned tags omit `Ordinary Hours & Overtime`.

These deterministic repair rules are named in code and written back into the clause record so the audit trail shows:
- which tag was added;
- which deterministic rule name caused it; and
- that the change was code-driven rather than model-driven.

In step `2.1`, the intended source of each saved field is:
- `top_level_clauses[*]`: model-generated, then Python-validated.
- `classified_clauses[*].tags`: model-generated, then Python-validated, and may be deterministically repaired.
- `classified_clauses[*].reason`: model-generated, but deterministic repair text may be appended where a tag was added by code.
- `classified_clauses[*].deterministic_tag_adjustments`: code-generated only. This field is present only when a deterministic repair was applied.

At present, the only step-2 tag that may be added deterministically is:
- `Ordinary Hours & Overtime`

All other step-2 tags remain model-generated and Python-validated only:
- `Hourly Rate`
- `Penalty`
- `Allowance`
- `Breaks (Meal Breaks)`
- `Breaks (Between Work Periods)`
- `Leave`
- `Definition`
- `Other Payment`

### Validation in Step 2.1

There are two layers of control:

1. structured output control:
- the model is required to return the expected structured payload;

2. deterministic validation and repair:
- the returned top-level reference must match the clause group that was sent;
- returned clause references must map back to real direct `L2` clauses;
- non-relevant top-level clauses must not also return classified children.

After that validation, deterministic repair rules may still add `Ordinary Hours & Overtime` where the clause text itself clearly supports it. These repairs are intended to make the shortlist safer for downstream overtime work, not to silently broaden unrelated payment clauses.

If validation fails, the step fails.

### Why Step 2.1 exists

This step narrows the award to the subset that is likely to matter for payment logic. It does not yet attempt to explain overtime.

## Step 2.2. Overtime clause classification

Files:
- `src/step_2_2_classify_overtime_clauses/run.py`
- `src/prompts/step_2_2_classify_overtime_clauses.py`

This step is deterministic apart from the model call.

It filters the step-2.1 classification output down to the clauses tagged `Ordinary Hours & Overtime`, then classifies those clauses into overtime-specific roles.

The output is a structured clause-role classification artifact.

The scope-tagging design is intentionally conservative:
- the prompt tells the model to use `day-worker` or `shiftworker` only where the clause expressly supports that label;
- deterministic post-validation code normalises unsupported work-arrangement inferences back to `all`.

This classification separates:
- clauses that create overtime;
- clauses that describe consequences after overtime already exists;
- related clauses that give context but do not create overtime themselves.

The step is validated so the downstream rule drafting step receives a narrow and reviewable source set.

## Step 3.1. Overtime ruleset generation

Files:
- `src/step_3_1_generate_ruleset/run.py`
- `src/prompts/step_3_1_generate_ruleset.py`

This step generates the drafted overtime ruleset from the shortlisted step-2.2 clauses.

The active pipeline uses two expert runs and a deterministic comparison/merge pass so that omissions and interpretive differences are visible in reviewable artifacts.

The outputs are:
- expert A draft;
- expert B draft;
- comparison summary;
- canonical combined ruleset.

## Step 3.2. Review and revise the drafted ruleset

Files:
- `src/step_3_2_review_ruleset/run.py`
- `src/prompts/step_3_2_review_ruleset.py`

This step reviews the drafted ruleset using structured evaluator and creator outputs.

The goal is not to silently replace the earlier ruleset. The goal is to make the changes explicit, keep the rule-by-rule record visible, and rebuild the revised artifact from structured decisions.

The outputs are:
- evaluator feedback markdown and JSON;
- creator response markdown and JSON;
- revised overtime interpretation markdown and JSON.

## Step 4.1. Formatted overtime guide

Files:
- `src/step_4_1_format_ruleset/run.py`
- `src/prompts/step_4_1_format_ruleset.py`

This step is retained and maintained, but it is not part of the current default manager-review pipeline.

Purpose:
- turn the revised interpretation artifact into a cleaner human-readable overtime guide;
- prefer the revised step `3.2` interpretation when an award code is used;
- use `resources/Template.md` as a formatting and heading reference;
- omit unsupported template headings entirely rather than emitting placeholder text;
- ignore the validation-notes preamble from the source interpretation and format only the actual rules.

This is a presentation step. The template is not source evidence.

## Step 5.1. Core overtime pseudocode

Files:
- `src/step_5_1_generate_pseudocode/run.py`
- `src/step_5_1_generate_pseudocode/verification.py`

This step is also retained and maintained outside the default manager-review path.

Purpose:
- generate implementation-oriented ordinary/overtime pseudocode from the latest available interpretation source;
- prefer the step `4.9` human-review ruleset file, then `4.1`, then revised `3.2`, then the earlier reviewed interpretation;
- validate the generated pseudocode deterministically against a rule inventory built from the source interpretation.

This step mixes free-text generation with hard deterministic post-generation checks.

## Technical detail boundary

This methodology document deliberately stops short of:
- reproducing JSON schemas;
- listing every field of every artifact;
- restating exact validator function behaviour line by line.

Those details now live in:
- `resources/TECHNICAL_GUIDE.md`

## Streamlit review application

Files:
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

The Streamlit review application is the main operator surface for:
- reviewing step outputs side by side;
- monitoring long-running pipeline steps;
- inspecting the structured JSON artifacts and their warnings;
- deleting an award output set under the award-first processed-output layout.

The Streamlit app is part of the working methodology because it is the review surface for generated artifacts.

Its role is:
- discover existing award output sets;
- run the active pipeline or selected steps for an award code;
- compare intermediate and final artifacts side by side;
- expose reviewer-facing screens for payment clauses, payment clause categories, ruleset clause classification, expert drafts, comparison output, combined ruleset, reviewer commentary, final formatted ruleset, manual edited ruleset, and pseudocode.

The parked agentic review conversation is no longer part of the active Streamlit surface.

## End-to-end interpretation

The easiest way to understand the system is:

1. Step `1` creates a deterministic source record.
2. Step `2.1` narrows the award to payment-relevant material.
3. Step `2.2` classifies overtime-related clauses by role.
4. Step `3.1` drafts the overtime ruleset.
5. Step `3.2` critiques and revises that draft with explicit rule-level decisions.
6. Step `4.1` formats the reviewed ruleset for reviewer-facing use.
7. Step `5.1` generates implementation-oriented pseudocode from the reviewed artifact.

So the method is not "one model reads the award and answers."

It is:
- deterministic source extraction;
- structured narrowing;
- structured role classification;
- dual expert drafting;
- deterministic comparison and merge;
- supervised revision;
- optional later formatting and implementation-oriented generation.
