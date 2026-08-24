# Award Extractor Methodology

This document explains how the current pipeline works at a business and review-method level.

It is intentionally not the low-level implementation reference.

Use:
- `resources/TECHNICAL_GUIDE.md` for exact LLM inputs and outputs, JSON schemas, and deterministic validation logic;
- `resources/outputs.md` for filenames and output locations.

## Purpose

The project turns award source material into reviewable payroll ruleset interpretation artifacts.

The active rulesets are:
- overtime creation;
- overtime consequence;
- penalties.

It does not try to produce a payroll engine result in one step. Instead, it narrows the source material progressively and leaves an audit trail at each stage.

The active path is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Build one selected ruleset subset, draft rulesets, and review the revised interpretation.
4. Format the reviewed ruleset for reviewer-facing output.
5. Generate implementation-oriented pseudocode.

In code, those are steps `1`, `2.1`, `2.2`, `3.1`, `3.2`, `4.1`, and `5.1`.
Step `6.1` is a separate calculator-questionnaire and calculator-draft stage
that can be run after the reviewed rulesets are available.

## Human review expectations

The pipeline is not intended to make every final payroll interpretation decision
without human oversight. Human review is expected at the following points:

- Step `3.1`: the expert drafts, comparison artifact, and combined ruleset are
  working interpretation outputs. They are evidence for review, not a final
  approved ruleset.
- Step `3.2`: the evaluator identifies issues and the creator decides whether to
  keep, modify, or remove each rule. The evaluator feedback, creator decision
  record, and revised ruleset are all retained so a human reviewer can trace the
  decision from recommendation to final rule.
- Step `4.1`: the formatted guide is a presentation layer for human review. It
  must not replace the reviewed step `3.2` ruleset as the authoritative source.
  Formatting coverage warnings are surfaced for manual review rather than being
  silently treated as resolved.
- Optional step `4.9`: a reviewer may save a manually reviewed ruleset working
  file after step `4.1`. When present, this file becomes the preferred source for
  step `5.1` pseudocode generation.

Human review should confirm, at minimum:

- the rule is supported by the cited award clauses;
- employee scope and work arrangement are correct;
- distinct payroll tests have not been merged incorrectly;
- evaluator recommendations rejected by the creator have a recorded reason;
- any formatting or pseudocode coverage warnings have been considered.

Step `6.1` does not replace this review. It projects the reviewed rules into a
narrow calculator questionnaire and calculator-code format. It is not intended
to reproduce every rule in the reviewed ruleset.

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

From step `2.2` onward, the pipeline is ruleset-aware rather than overtime-only. One run works on one selected ruleset at a time:
- `overtime_creation`
- `overtime_consequence`
- `penalties`

## Prompt construction pattern

The active LLM-backed steps use a layered prompt pattern so shared business framing is reused consistently while the step-specific task stays narrow.

Where a step uses an LLM, the prompt is split into:
- generic prompt instructions used for that kind of payroll configuration task;
- subset-wide instructions reused across all relevant steps for the same subset;
- step-family instructions reused within one step family for that subset context;
- reusable ruleset checks shared by all prompts for the same ruleset;
- step-and-subset-specific instructions for the current step;
- the current step payload, such as shortlisted clauses, a reviewed ruleset, or a rule inventory.

This matters for penalties because the penalties ruleset now runs in parallel with the two overtime rulesets, but should not inherit overtime-only framing. The reusable subset layer carries the shared penalties scope into every relevant downstream prompt.

## Step 1. Fetch and structure the award

Files:
- `src/step_1_1_fetch/fetch_award.py`
- `src/step_1_1_fetch/run.py`
- `src/step_1_2_parse_award/step_1_parse_markdown.py`
- `src/step_1_2_parse_award/step_2_build_tree.py`
- `src/step_1_2_parse_award/step_3_write_outputs.py`
- `src/step_1_2_parse_award/run.py`

This step is deterministic.

Input:
- a Fair Work award URL such as `https://awards.fairwork.gov.au/MA000018.html`

Step 1.1 process:
- fetch the award HTML;
- isolate the `mainContent` section;
- build the structured award tree used by later steps.

Step 1.2 process:
- parse markdown into events;
- build the nested award tree;
- write the raw HTML snapshot and structured award JSON;
- build a section index JSON;
- build a flat heading CSV for human review;
- expose explicit review stubs for L1 clause review and L2 clause review.

The 1.2 code path is intentionally split into three linear files:
- `step_1_parse_markdown.py` for markdown event parsing and table handling;
- `step_2_build_tree.py` for building the nested award structure;
- `step_3_write_outputs.py` for writing raw, processed, and supporting files.

Outputs:
- raw HTML snapshot;
- structured award JSON;
- supporting section index JSON;
- supporting heading CSV.

The main award JSON is the only step-1 artifact required by the active downstream pipeline. The supporting files exist for review and lookup rather than for later pipeline execution.

No model is used here. Every later step depends on this extraction being structurally correct.

## Step 2.1. Payment clause classification

Files:
- `src/step_2_1_classify_payments/run.py`
- `src/prompts/step_2_1_classify_payments.py`

Purpose:
- identify which top-level clauses are relevant to payment or definitional logic;
- classify the direct `L2` clauses that matter for downstream ruleset work.

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

This step narrows the award to the subset that is likely to matter for payment logic. It does not yet attempt to draft any ruleset.

## Step 2.2. Ruleset clause classification

Files:
- `src/step_2_2_classify_overtime_clauses/run.py`
- `src/prompts/step_2_2_classify_overtime_clauses.py`

This step selects one ruleset subset from the step-`2.1` output and writes a structured clause-classification artifact for that ruleset.

For the overtime rulesets:
- the step filters the step-`2.1` output down to clauses tagged `Ordinary Hours & Overtime`;
- it then uses an LLM to classify those shortlisted clauses into overtime-specific roles.

For the penalties ruleset:
- the step filters the step-`2.1` output down to clauses tagged `Penalty` or `Breaks (Between Work Periods)`;
- it then builds the penalties clause-classification artifact deterministically without an LLM call;
- every shortlisted clause is saved as `Penalty Rule`;
- employee cohort and work arrangement are still kept conservative by deriving them from express clause text rather than inventing narrow scope.

The output is a structured clause-role classification artifact.

The scope-tagging design is intentionally conservative:
- the prompt tells the model to use `day-worker` or `shiftworker` only where the clause expressly supports that label;
- deterministic post-validation code normalises unsupported work-arrangement inferences back to `all`.

For overtime creation and overtime consequence, this classification separates:
- clauses that create overtime;
- clauses that describe consequences after overtime already exists;
- related clauses that give context but do not create overtime themselves.

For penalties, the deterministic shortlist intentionally keeps both:
- premium-pay rules such as shift allowances, weekend or public holiday penalties, and time-band penalties;
- break-between-work-period rules, including supporting operational rules with no direct financial entitlement.

The step is validated so the downstream rule drafting step receives a narrow and reviewable source set for the selected ruleset.

## Step 3.1. Ruleset generation

Files:
- `src/step_3_1_generate_ruleset/run.py`
- `src/prompts/step_3_1_generate_ruleset.py`

This step generates the drafted ruleset from the shortlisted step-`2.2` clauses for the selected ruleset.

The active pipeline uses two expert runs and a deterministic comparison/merge pass so that omissions and interpretive differences are visible in reviewable artifacts.

For penalties, the drafting contract keeps these distinctions separate where supported by the source:
- shift-commencement qualification rules;
- shift-end qualification rules;
- actual-hours qualification rules;
- whole-shift outcomes;
- specific-hours outcomes;
- supporting break-gap rules with no direct premium outcome.

The outputs are:
- expert A draft;
- expert B draft;
- comparison summary;
- canonical combined ruleset.

These are reviewable working outputs, not human-approved final interpretations.
The combined ruleset is the input to step `3.2`, where evaluator feedback and
creator decisions are recorded. A reviewer should use the expert drafts and
comparison artifact to understand disagreement or possible omissions, then use
the step `3.2` decision record and revised ruleset as the next review checkpoint.

## Step 3.2. Review and revise the drafted ruleset

Files:
- `src/step_3_2_review_ruleset/run.py`
- `src/prompts/step_3_2_review_ruleset.py`

This step reviews the drafted ruleset using structured evaluator and creator outputs.

The goal is not to silently replace the earlier ruleset. The goal is to make the changes explicit, keep the rule-by-rule record visible, and rebuild the revised artifact from structured decisions.

The evaluator receives only the evidence needed to critique the drafted ruleset:
- the step `3.1` ruleset markdown, including any validation-warning notes already written into that draft;
- the canonical step `3.1` rules JSON artifact for the same draft;
- the full step `2.1` payment classification JSON;
- the full step `2.2` subset clause-classification JSON; and
- a compact reviewer-oriented summary of the generation-ready shortlisted clauses.

The evaluator no longer receives the full reconstructed creator prompt context. That earlier payload repeated prompt scaffolding rather than adding new reviewer evidence.

The creator then receives a narrower revision package:
- the original ruleset system framing reused from step `3.1`;
- the original drafted ruleset markdown;
- the authoritative evaluator review action pack JSON;
- the evaluator summary markdown; and
- focused clause excerpts selected from step `2.1` and step `2.2` based on the evaluator feedback.

The creator does not receive the full step `2.1` payment classification JSON or full step `2.2` subset classification JSON directly in the revision prompt. Instead, the relevant clause excerpts are reconstructed for the creator from those earlier artifacts.

For penalties, the review step should:
- keep valid premium-pay rules;
- keep valid supporting break-gap rules even where they do not create a direct payment outcome;
- remove overtime-only drift unless the clause expressly creates a penalties-domain rule.

The outputs are:
- evaluator feedback markdown and JSON;
- creator response markdown and JSON;
- revised ruleset markdown and JSON.

### Human review checkpoint

Step `3.2` uses the following active sequence:

1. The evaluator reviews the step `3.1` draft and records structured findings.
2. The creator considers those findings and decides which rules to keep, modify,
   or remove.
3. The creator produces the revised ruleset and a decision record.
4. A human reviewer reviews the evaluator findings, the creator's accepted and
   rejected decisions, and the revised ruleset.

The creator's decision is the model-generated implementation decision for this
stage, but it is not a substitute for human oversight. Rejected evaluator
recommendations must remain visible with the creator's reason so that a reviewer
can challenge the decision if necessary.

## Step 4.1. Formatted ruleset guide

Files:
- `src/step_4_1_format_ruleset/run.py`
- `src/prompts/step_4_1_format_ruleset.py`

Purpose:
- turn the revised interpretation artifact into a cleaner human-readable ruleset guide;
- prefer the revised step `3.2` interpretation when an award code is used;
- use `resources/Templates/Template.md` as a formatting and heading reference;
- omit unsupported template headings entirely rather than emitting placeholder text;
- ignore the validation-notes preamble from the source interpretation and format only the actual rules.

This is a presentation step. The template is not source evidence.

### Human review checkpoint

Step `4.1` produces a reviewer-facing formatted guide. A human reviewer is
expected to check that the formatted guide has preserved the operative rules,
thresholds, employee scope, exceptions, and clause references from the reviewed
step `3.2` ruleset. The formatter's coverage warnings are review prompts; they do
not mean that the output has been automatically repaired or approved.

If the formatted guide is edited or corrected by a human, the resulting file is
handled through the optional step `4.9` human-review utility and becomes the
preferred step `5.1` source.

For penalties, the formatter keeps supporting non-financial break-gap rules representable and uses penalties-specific headings instead of overtime headings.

## Step 4.9. Human review ruleset utility

Files:
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

This is part of the active operator flow, but not part of the default automated pipeline sequence.

Purpose:
- allow a reviewer to save a human-reviewed ruleset working file after step `4.1`;
- keep that reviewed working file visible as a canonical artifact in the award folder;
- provide the highest-priority source for step `5.1` when a human-reviewed version exists.

## Step 5.1. Ruleset pseudocode

Files:
- `src/step_5_1_generate_pseudocode/run.py`
- `src/step_5_1_generate_pseudocode/step_3_validate_pseudocode.py`

Purpose:
- generate implementation-oriented pseudocode from the latest available interpretation source for the selected ruleset;
- prefer the step `4.9` human-review ruleset file, then `4.1`, then revised `3.2`, then the earlier reviewed interpretation;
- validate the generated pseudocode deterministically against a rule inventory built from the source interpretation.

This step mixes free-text generation with hard deterministic post-generation checks.

For penalties, the pseudocode is not an ordinary-versus-overtime classifier. It instead produces explicit penalty-oriented outputs such as penalty category, multiplier, fixed add-on, whole-shift application, and supporting break-gap requirements where the reviewed rules support them.

## Step 6.1. Calculator questionnaire and Python draft

Files:
- `src/step_6_1_generate_calculator_yaml/run.py`
- `src/step_6_1_generate_calculator_yaml/core.py`
- `src/prompts/step_6_1_generate_calculator_yaml.py`

Purpose:
- combine the reviewed step `3.2` JSON rulesets for overtime creation, overtime consequence, and penalties;
- answer a fixed calculator questionnaire with evidence fields;
- generate a calculator Python draft from that questionnaire using only the
  seven grouped attributes defined in `resources/ruleset.md`;
- identify fields outside the current analysis and show their explicit defaults
  under `MISSING_FROM_ANALYSIS` in the generated Python.
- present each missing rule with a readable business label, its auditable field
  path, the assumed/default value used, and the reason for that assumption.
- exclude ordinary casual loading from the LLM questionnaire while keeping its
  required output default explicit and reviewable;
- use the employee penalty loading for `casual_rate` when no distinct casual
  penalty rate is stated, without adding ordinary casual loading.
- distinguish `not_applicable` neutral values from genuinely missing analysis,
  and map daily limits to the calculator contract's day-worker/shiftworker
  dimensions with assumptions recorded in the answer evidence.

This is the first calculator-facing output layer. It is a deliberate projection
of the reviewed rulesets into the narrower calculator contract. Its output is not
the complete award interpretation and must not be treated as a replacement for
the reviewed step `3.2` rulesets or any human-reviewed step `4.9` source.
Its prompt, schema, and data shape are expected to change as the calculator
contract becomes clearer.

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

It is also ruleset-aware for the active rulesets, so reviewers can load overtime creation, overtime consequence, or penalties artifacts through the same review flow.

The Streamlit app is part of the working methodology because it is the review surface for generated artifacts.

Its role is:
- discover existing award output sets;
- run the active pipeline or selected steps for an award code;
- compare intermediate and final artifacts side by side;
- expose reviewer-facing screens for payment clauses, payment clause categories, ruleset clause classification, expert drafts, comparison output, combined ruleset, reviewer commentary, the step `4.1` formatted guide, the optional step `4.9` human-review ruleset utility, step `5.1` pseudocode, and step `6.1` calculator artifacts.

## End-to-end interpretation

The easiest way to understand the system is:

1. Step `1` creates a deterministic source record.
2. Step `2.1` narrows the award to payment-relevant material.
3. Step `2.2` builds the selected ruleset clause subset.
4. Step `3.1` drafts the selected ruleset for review.
5. Step `3.2` runs evaluator review, creator decisions, and creator rewrite, while retaining the decision trail for human review.
6. Step `4.1` formats the reviewed ruleset for human-facing review.
7. Optional step `4.9` allows a human-reviewed ruleset working file to be saved when needed.
8. Step `5.1` generates implementation-oriented pseudocode from the best available reviewed artifact.
9. Optional/separately selected step `6.1` turns the reviewed rulesets into a narrower calculator questionnaire and Python draft.

So the method is not "one model reads the award and answers."

It is:
- deterministic source extraction;
- structured narrowing;
- structured role classification;
- dual expert drafting;
- deterministic comparison and merge;
- supervised revision;
- optional later formatting and implementation-oriented generation.
