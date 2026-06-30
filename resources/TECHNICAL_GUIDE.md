# Award Extractor Technical Guide

This document is the technical reference for the active pipeline.

Use it when you need to know:
- which script owns a stage;
- what goes into each LLM call;
- what comes out of each LLM call;
- which JSON schema is expected;
- which deterministic validations run before an artifact is accepted or written.

For business purpose and review intent, use `resources/METHODOLOGY.md`.

## Scope

Active default pipeline:
- Step `1`
- Step `2`
- Step `3`
- Step `3B`

Maintained later steps:
- Step `4A`
- Step `5B`

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

| Step | Script | LLM? | Primary output |
| --- | --- | --- | --- |
| 1 | `src/script_1_fetch_award.py` | No | Structured award JSON |
| 2 | `src/script_2_classify_payments.py` | Yes | Payment clause classification JSON |
| 3 part 1 | `src/script_3_part1_classify_overtime_clauses.py` | Yes | Overtime clause classification JSON |
| 3 part 2 expert A/B | `src/script_3_part2_generate_overtime_interpretation.py` | Yes | Expert rule-set JSON/MD |
| 3 part 2 comparison | `src/script_3_part2_generate_overtime_interpretation.py` | Yes | Comparison JSON + merged rules |
| 3B evaluator | `src/script_3b_review_overtime_interpretation.py` | Yes | Evaluator feedback JSON/MD |
| 3B creator | `src/script_3b_review_overtime_interpretation.py` | Yes | Creator response JSON/MD |
| 4A | `src/script_4a_summarize_overtime.py` | Yes | Formatted overtime guide MD |
| 5B generation | `src/script_5b_generate_overtime_pseudocode.py` | Yes | Pseudocode MD |
| 5B validation | `src/script_5b_validate_overtime_pseudocode.py` | No | Validation JSON/MD |

## Step 1. Fetch And Structure Award

Owner:
- `src/script_1_fetch_award.py`

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
- award JSON;
- raw HTML snapshot;
- supporting section index JSON;
- supporting heading CSV;
- archive copies.

## Step 2. Payment Clause Classification

Owners:
- `src/script_2_classify_payments.py`
- `src/prompts/payment_clause_classification.py`

### Unit of work

One model call per top-level clause group.

Each group contains:
- one top-level clause;
- its direct `L2` descendants;
- the flattened text of each descendant subtree.

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Prompt input:
- top-level clause reference;
- top-level clause title;
- flattened top-level clause text;
- direct `L2` clause references, titles, and flattened texts.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": ["top_level_clause", "classified_clauses"],
  "properties": {
    "top_level_clause": {
      "type": "object",
      "required": [
        "reference",
        "title",
        "payment_relevant",
        "definition_relevant",
        "requires_l2_classification",
        "reason"
      ]
    },
    "classified_clauses": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["reference", "tags", "reason"]
      }
    }
  }
}
```

Allowed step-2 tags are defined in:
- `src/prompts/payment_clause_classification.py`

### Deterministic checks before accepting a model response

- returned top-level reference must equal the clause group sent;
- returned classified clause references must map to a real direct `L2` clause or to an allowed nested descendant of one direct `L2` clause;
- non-relevant top-level clauses must not also return classified children;
- duplicate direct-`L2` results are merged in a controlled way, with reasons combined;
- title-only top-level clauses can be resolved deterministically without a model call.

### Deterministic post-processing after validation

Step `2` has an explicit overtime-tag repair layer.

Current deterministic repair family:
- named rules in `EXPLICIT_OVERTIME_TRIGGER_RULES`

Effect:
- may add `Ordinary Hours & Overtime`

Typical trigger patterns:
- `overtime will be paid`
- `paid overtime`
- `overtime is payable`
- `paid at overtime rates`
- `without payment of overtime`
- similar explicit wording defined in code

Saved audit fields:
- `deterministic_tag_adjustments`

### Saved artifact ownership

- `classified_clauses[*].tags`: model-generated, Python-validated, may be deterministically repaired
- `classified_clauses[*].reason`: model-generated, may have deterministic repair text appended
- `deterministic_tag_adjustments`: deterministic only

## Step 3 Part 1. Overtime Clause Classification

Owners:
- `src/script_3_part1_classify_overtime_clauses.py`
- `src/prompts/overtime_ruleset.py`

### Deterministic pre-filter

Input artifact:
- step-2 payment classification JSON

Shortlist rule:
- keep clauses tagged `Ordinary Hours & Overtime`

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Prompt input:
- only shortlisted overtime-related clauses;
- each clause passed as markdown section text.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": ["clauses"],
  "properties": {
    "clauses": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "clause_number",
          "classification",
          "classifications",
          "clause_text",
          "explanation",
          "employee_cohort",
          "work_arrangement",
          "other_scope_notes"
        ]
      }
    }
  }
}
```

Allowed classifications:
- `Ordinary Hours Boundary`
- `Overtime Trigger`
- `Overtime Consequence`
- `Related Rule`
- `Not Relevant`

Allowed scope values:
- `employee_cohort`: values from `ALLOWED_EMPLOYEE_COHORTS`
- `work_arrangement`: values from `ALLOWED_WORK_ARRANGEMENTS`

### Deterministic validation

- every returned clause number must have been shortlisted;
- no duplicates;
- every shortlisted clause must be classified;
- primary `classification` must also appear inside `classifications`;
- all classifications must be from the allowed set;
- `explanation` must be non-empty;
- `employee_cohort` must be allowed;
- `work_arrangement` must be allowed.

### Deterministic scope normalisation

`work_arrangement` is treated conservatively after validation:

- keep `day-worker` only where the clause text expressly supports day-worker language;
- keep `shiftworker` only where the clause text expressly supports shiftworker or shiftwork language;
- otherwise save `all`.

This is a hard deterministic narrowing of model output.

### Deterministic filter for downstream generation

Step `3.3` keeps only classifications containing:
- `Ordinary Hours Boundary`
- `Overtime Trigger`

These are the overtime-creation clauses passed into rule generation.

## Step 3 Part 2. Expert Rule Generation

Owners:
- `src/script_3_part2_generate_overtime_interpretation.py`
- `src/prompts/overtime_ruleset.py`

### Expert generation calls

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Count:
- controlled by `expert_run_count`
- active default uses two expert runs via `src/script_3_interpret_overtime.py`

Prompt input:
- source file path;
- filtered overtime-creation clauses from step `3.3`;
- clause numbers;
- classifications;
- scope tags;
- clause text;
- explanation text.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": ["rules"],
  "properties": {
    "rules": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "rule_id",
          "section_heading",
          "employee_scope",
          "employee_cohort",
          "work_arrangement",
          "other_scope_notes",
          "clause_references",
          "rule_markdown",
          "rule_plain_text",
          "source_clause_numbers",
          "source_classifications"
        ]
      }
    }
  }
}
```

### Deterministic validation for each expert run

- `rules` must be an array;
- each rule must pass `validate_rule_list()`;
- `rule_id` must match the allowed pattern in `RULE_ID_ALLOWED_PATTERN`;
- source clause references are checked against known shortlisted clause numbers and discovered clause references;
- malformed source clause references produce warnings;
- rules with no link to known shortlisted source clauses produce warnings;
- scope fields are compared against the underlying clause classifications using `scope_validation_warnings_for_rule()`;
- source classifications outside the creation set produce warnings;
- shortlisted clauses not represented in the output produce warnings.

### Markdown fallback

If expert JSON cannot be parsed:
- markdown fallback parsing is used via `rules_from_markdown_fallback()`
- a warning is written stating that JSON failed and markdown fallback was used

This fallback currently exists in step `3` expert generation, but not in step `3B`.

## Step 3 Part 2. Expert Comparison And Merge

Owner:
- `src/script_3_part2_generate_overtime_interpretation.py`

### LLM call

API:
- OpenAI Responses API

Default model:
- `OVERTIME_INTERPRETATION_COMPARISON_MODEL` or main interpretation model

Prompt input:
- shortlisted source clauses;
- expert A structured rules;
- expert B structured rules.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": [
    "comparison_summary_markdown",
    "accounted_run_a_rule_ids",
    "accounted_run_b_rule_ids",
    "merged_rules",
    "merge_explanations"
  ],
  "properties": {
    "comparison_summary_markdown": {"type": "string"},
    "accounted_run_a_rule_ids": {"type": "array"},
    "accounted_run_b_rule_ids": {"type": "array"},
    "merged_rules": {"type": "array"},
    "merge_explanations": {"type": "array"}
  }
}
```

`merged_rules[*]` uses the same rule-object shape as the expert generation schema.

### Deterministic validation

- comparison output must be valid JSON;
- merged rules must pass `validate_rule_list()`;
- all expert A rule IDs should appear in `accounted_run_a_rule_ids`, else warning;
- all expert B rule IDs should appear in `accounted_run_b_rule_ids`, else warning;
- scope warnings are re-run on merged rules;
- shortlisted clauses missing from the merged ruleset produce warnings.

### Saved step-3 artifacts

- `*_overtime_clause_classification.json`
- `*_expert_a.json` and `.md`
- `*_expert_b.json` and `.md`
- `*_comparison.json`
- `*_overtime_interpretation.json`
- `*_overtime_interpretation.md`

## Step 3B. Evaluator Review

Owners:
- `src/script_3b_review_overtime_interpretation.py`
- `src/prompts/overtime_interpretation_review.py`

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5-mini`

Current evaluator output budget:
- `8000` max output tokens

Prompt input:
- step-3 interpretation markdown;
- step-3 interpretation JSON/rules artifact when available;
- step-2 payment classification JSON;
- step-3 overtime clause-classification JSON;
- reconstructed step-3 creator prompt context;
- evaluator structured-output instructions.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": ["summary_markdown", "rule_reviews", "new_rules"],
  "properties": {
    "summary_markdown": {"type": "string"},
    "rule_reviews": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "recommendation", "rationale"]
      }
    },
    "new_rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "rule_id",
          "section_heading",
          "employee_scope",
          "clause_references",
          "rule_markdown",
          "rule_plain_text",
          "source_clause_numbers",
          "source_classifications"
        ]
      }
    }
  }
}
```

`recommendation` values:
- `keep`
- `modify`
- `remove`

### Deterministic validation

Implemented in `validate_review_feedback_artifact()`:

- `rule_reviews` must be an array;
- every item must be an object;
- every `rule_id` must exist in the original step-3 rules;
- no duplicate `rule_id`;
- `recommendation` must be allowed;
- `rationale` must be non-empty;
- every original `rule_id` must appear exactly once;
- `summary_markdown` must be non-empty;
- `new_rules` must be an array;
- evaluator-proposed `new_rules` must not duplicate original rule IDs;
- evaluator-proposed `new_rules` are validated as full structured rule objects.

### Retry behaviour

- empty response text is retried up to the evaluator repair limit;
- invalid JSON or validation failure is retried with a repair prompt;
- if retries are exhausted, step `3B` fails before creator application.

## Step 3B. Creator Revision

Owners:
- `src/script_3b_review_overtime_interpretation.py`
- `src/prompts/overtime_interpretation_review.py`

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Prompt input:
- original interpretation markdown;
- relevant clause excerpts selected from upstream artifacts;
- original step-3 rules JSON;
- evaluator structured review JSON;
- creator review action pack JSON derived from original rules plus evaluator structured review;
- evaluator markdown feedback, treated as explanatory context rather than the authoritative source of review actions;
- creator structured-output instructions.

Response format:
- strict JSON schema

Schema:

```json
{
  "type": "object",
  "required": [
    "decision_record_markdown",
    "rule_updates",
    "new_rule_reviews"
  ],
  "properties": {
    "decision_record_markdown": {"type": "string"},
    "rule_updates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "decision", "reason", "updated_rule"]
      }
    },
    "new_rule_reviews": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "decision", "reason", "updated_rule"]
      }
    }
  }
}
```

`rule_updates[*].decision` values:
- `keep`
- `modify`
- `remove`

`new_rule_reviews[*].decision` values:
- `accept`
- `modify`
- `reject`

Contract:
- creator must address every original rule;
- creator may only accept, modify, or reject evaluator-proposed `new_rules`;
- creator must not invent standalone creator-only new rules.
- creator should derive operational add/remove/modify decisions from the evaluator structured review JSON and action pack, not from evaluator prose alone.

### Deterministic validation and application

Implemented in `apply_review_decisions()`:

- `rule_updates` must be an array;
- each original rule must have exactly one creator decision;
- no unknown original `rule_id`;
- no duplicate original `rule_id`;
- `decision` must be allowed;
- `reason` must be non-empty;
- removals require evaluator recommendation `remove`;
- `modify` merges `updated_rule` over the original rule and re-validates the merged rule;
- missing `updated_rule` on `modify` preserves original rule rather than silently dropping it;
- evaluator `new_rules` must each receive exactly one creator `new_rule_review`;
- no unknown evaluator-proposed new rule IDs;
- no duplicate evaluator-proposed new rule IDs;
- new-rule decision must be `accept`, `modify`, or `reject`;
- modified evaluator-proposed new rules must preserve the evaluator-proposed `rule_id`;
- final rule IDs must remain unique.

### Post-application deterministic checks

- clause-coverage reductions are surfaced via `clause_coverage_warnings()`;
- revised markdown gets validation warnings prepended via `prepend_validation_warnings()`;
- revised JSON and markdown are written together by `write_rules_artifact()`.

### Prompting note

The current creator prompt deliberately downplays evaluator markdown prose:
- the original rules JSON and evaluator structured review JSON are the authoritative machine contract;
- a derived action-pack JSON is passed to the creator to keep the original-rule decisions and evaluator-proposed `new_rules` visible in one place;
- evaluator markdown is still shown for reviewer-style explanation, but should not be treated as authority for extra add/remove/split/merge actions that are not reflected in the structured JSON.

### Failure behaviour

If creator output cannot be applied safely:
- original step-3 interpretation is preserved as the revised output;
- creator response markdown becomes a manual-review record;
- validation error and raw creator response are saved;
- no silent add/drop occurs.

This is the intended fail-safe behaviour.

## Step 4A. Formatted Overtime Guide

Owners:
- `src/script_4a_summarize_overtime.py`
- `src/prompts/overtime_guide_formatting.py`

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Prompt input:
- selected interpretation markdown;
- `resources/Template.md`.

Response format:
- free-text markdown
- no JSON schema

### Deterministic pre-processing

- resolve award-code input to revised interpretation if present;
- strip validation-notes preamble from the interpretation before prompting;
- require both interpretation markdown and template markdown to exist and be non-empty.

### Deterministic post-processing

- strip wrapping markdown fences from the model response;
- write markdown with archive copy.

No hard semantic validation currently runs in step `4A`.

## Step 5B. Core Overtime Pseudocode Generation

Owners:
- `src/script_5b_generate_overtime_pseudocode.py`
- `src/prompts/core_overtime_pseudocode.py`
- `src/script_5b_validate_overtime_pseudocode.py`

### Source selection

Award-code mode prefers:
1. manual `4B`
2. `4A`
3. revised `3B`
4. original `3`

### LLM call

API:
- OpenAI Responses API

Default model:
- `gpt-5.4-mini`

Prompt input:
- latest selected overtime interpretation markdown;
- deterministic source rule inventory built from structured rules JSON where available;
- otherwise fallback rule inventory from markdown parsing.

Response format:
- free-text markdown pseudocode
- no JSON schema

### Deterministic validation after generation

Implemented in `validate_overtime_pseudocode_against_inventory()` and related helpers:

- parse `##` sections from markdown;
- parse implementation bullets from the `Pseudocode` section;
- extract clause references from pseudocode bullets;
- infer employee scope keywords from pseudocode text;
- match each required source rule against pseudocode rules by clause references first, then keyword overlap;
- fail where source rules have no matching implementation rule;
- fail where scope conflicts with the source rule;
- mark text-overlap-only matches as unresolved;
- generate structured validation report with per-rule results and issues.

### Repair loop

- write initial pseudocode;
- run deterministic validation;
- if failed rules remain and repair attempts remain, send a repair prompt containing:
  - original pseudocode;
  - source inventory;
  - validation report markdown.

Current repair limit:
- `MAX_VALIDATION_REPAIR_ATTEMPTS = 1`

## Documentation Split

Use:
- `resources/METHODOLOGY.md` for business purpose, review intent, and why stages exist;
- `resources/TECHNICAL_GUIDE.md` for schemas, model-call contracts, and deterministic validation behaviour;
- `resources/outputs.md` for artifact filenames and storage conventions.
