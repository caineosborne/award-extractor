# Award Extractor Technical Guide

This document is the operator and code-reading guide for the current repository.

It explains:
- how to run each maintained script;
- what file each step produces;
- which source file owns the step;
- how the pieces fit together when reading the code.

For the higher-level system explanation, use `resources/METHODOLOGY.md`.

## What this repository currently contains

The active overtime pipeline is steps `1`, `2`, `3`, and `3B`.

Later maintained steps:
- `4A` formats a reviewer-facing guide.
- `5B` generates implementation-oriented pseudocode and validates it.

Supporting review tooling:
- a Streamlit app for inspecting outputs, comparing artifacts, and manually editing later-stage markdown.

Archived prototypes remain under `src/Archive/` and are not part of the active code path.

## Main directories

- `src/`: active pipeline scripts, prompt modules, and shared helpers.
- `streamlit_review/`: Streamlit review app and artifact-loading helpers.
- `tests/`: regression tests and examples of expected behaviour.
- `resources/`: methodology, templates, plans, and reference notes.
- `data/processed/`: generated artifacts written by the pipeline.

## Main entry points

Repository entry points:
- `award_extractor.py`: thin launcher for `award-pipeline`.
- `review_outputs.py`: thin launcher for the Streamlit review app.

Primary script registrations are in `pyproject.toml` under `[project.scripts]`.

## How to read the code

If you are new to the repository, read in this order:

1. `src/award_pipeline.py`
2. `src/common/active_pipeline_paths.py`
3. `src/common/output_paths.py`
4. `src/script_1_fetch_award.py`
5. `src/script_2_classify_payments.py`
6. `src/script_3_interpret_overtime.py`
7. `src/script_3b_review_overtime_interpretation.py`
8. `src/script_4a_summarize_overtime.py`
9. `src/script_5b_generate_overtime_pseudocode.py`
10. `src/script_5b_validate_overtime_pseudocode.py`
11. `streamlit_review/app.py`
12. `streamlit_review/output_data.py`

That order shows:
- the orchestration layer first;
- the shared path conventions second;
- the business steps in pipeline order;
- the review UI after the batch workflow is clear.

## Shared runtime and path helpers

These files explain how outputs are named and connected:

- `src/award_pipeline.py`
  Reads an award code, builds the standard paths for each active artifact, and runs selected pipeline steps.

- `src/common/active_pipeline_paths.py`
  Holds the path rules that derive one stage's filenames from another stage's filenames. This is the best place to check when you want to know why a file has a given name.

- `src/common/output_paths.py`
  Holds the output category names such as `1_fetch_award`, `3_overtime_interpretations`, and `5b_generate_overtime_pseudocode`. It also owns the timestamped archive-writing helper.

Other commonly reused files:

- `src/common/pipeline_io.py`
- `src/common/pipeline_runtime.py`
- `src/common/llm_io.py`
- `src/common/overtime_rules.py`
- `src/common/rule_inventory.py`

Those provide loading, environment setup, response extraction, rule rendering, and deterministic validation helpers.

## Step 1. Fetch award

Main file:
- `src/script_1_fetch_award.py`

Purpose:
- fetch a Fair Work award page;
- extract the `mainContent` HTML;
- convert it into structured JSON;
- automatically generate reviewer-friendly supporting outputs through a secondary script.

Run:

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
```

Main outputs:
- `data/processed/1_fetch_award/raw/MA000018.html`
- `data/processed/1_fetch_award/MA000018.json`
- `data/processed/1_fetch_award/supporting/MA000018_sections.json`
- `data/processed/1_fetch_award/supporting/MA000018.csv`

Archive behaviour:
- the main JSON gets a timestamped archive copy under `data/processed/1_fetch_award/archive/`
- the supporting files get timestamped archive copies under `data/processed/1_fetch_award/supporting/archive/`

How to read the code:
- start with `extract_award_elements()` to see how relevant HTML paragraphs and tables are identified;
- then `nest_award_elements()` to see how the flat list becomes the nested award tree;
- then `extract_award()` and `write_step_1_outputs()` for the final step-1 flow.

Important split:
- `src/script_1_fetch_award.py` owns the fetch, parse, raw HTML write, main award JSON write, and automatic orchestration.
- `src/script_1b_generate_fetch_supporting_artifacts.py` owns the section-index JSON and heading-summary CSV generation.

You can run the supporting script directly when needed:

```bash
uv run script-1b-generate-fetch-supporting-artifacts data/processed/1_fetch_award/MA000018.json
```

## Step 2. Classify payment clauses

Main files:
- `src/script_2_classify_payments.py`
- `src/prompts/payment_clause_classification.py`

Purpose:
- group the processed award into top-level clause units;
- classify payment-relevant and definition-relevant material;
- tag direct `L2` clauses for downstream work.

Run:

```bash
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
```

Main output:
- `data/processed/2_payment_clause_identifier/MA000018_payment_classification.json`

How to read the code:
- `collect_top_level_groups()` shows the grouping unit sent to the model;
- `build_messages_for_group()` shows how one clause group is turned into a prompt;
- validation helpers near the response-parsing logic show which structured assumptions are enforced before the file is accepted.

What the output is for:
- this is the main narrowing artifact used by step `3`;
- it is also one of the main review sources used by step `3B`.

## Step 3. Generate overtime interpretation

Main files:
- `src/script_3_interpret_overtime.py`
- `src/prompts/overtime_interpretation.py`

Purpose:
- filter step-2 output to overtime-related clauses;
- classify those clauses by overtime role;
- generate two expert interpretations;
- compare and merge them into one canonical interpretation.

Run:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Main outputs:
- `data/processed/3_overtime_interpretations/MA000018_overtime_clause_classification.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_a.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_a.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_b.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_b.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_comparison.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md`

How to read the code:
- read the deterministic filtering helpers first;
- then the overtime clause-classification request and validation logic;
- then the expert generation path;
- then the expert comparison and merge logic;
- then the markdown rendering and warning-prepending logic.

What each artifact means:
- `*_overtime_clause_classification.json`
  The clause-role classification used to decide which clauses can create overtime.

- `*_expert_a.*` and `*_expert_b.*`
  The two independent structured interpretations kept for review and comparison.

- `*_comparison.json`
  The semantic merge record showing how expert A and expert B were reconciled.

- `*_overtime_interpretation.json`
  The canonical machine-readable step-3 rule artifact.

- `*_overtime_interpretation.md`
  The human-readable view of the canonical step-3 rules.

## Step 3B. Review and revise the overtime interpretation

Main files:
- `src/script_3b_review_overtime_interpretation.py`
- `src/prompts/overtime_interpretation_review.py`

Optional alternate review files:
- `src/script_3b_agentic_review_overtime_interpretation.py`
- `src/script_3b_agentic_review_workflow.py`
- `src/prompts/agentic_review.py`

Default run:

```bash
uv run script-3b-review-overtime-interpretation MA000018
```

The script resolves the standard step-2, step-3, and clause-classification paths from the award code. It can also work from explicit paths.

Main outputs:
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_evaluator_feedback.md`
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_evaluator_feedback.json`
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_creator_response.md`
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_creator_response.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.json`

How to read the code:
- `load_review_source_artifacts()` shows exactly which upstream files are required;
- the evaluator prompt builder shows what is reviewed;
- the creator revision logic shows how rule-level decisions are applied;
- the rule-writing helpers show how the revised markdown and JSON are kept aligned.

What each artifact means:
- evaluator feedback files
  The supervisor critique of the step-3 interpretation.

- creator response files
  The creator's rule-by-rule response to that critique.

- revised interpretation files
  The step-3 interpretation after the review pass has been applied.

Optional alternate review run:

```bash
uv run script-3b-agentic-review-overtime-interpretation MA000018
```

Additional output from the optional mode:
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_agentic_review_conversation.md`

## Step 4A. Format a reviewer-facing overtime guide

Main files:
- `src/script_3_interpret_overtime.py`
- `src/script_3_part1_classify_overtime_clauses.py`
- `src/script_3_part2_generate_overtime_interpretation.py`
- `src/script_4a_summarize_overtime.py`
- `src/prompts/overtime_guide_formatting.py`
- `resources/Template.md`

Purpose:
- turn the latest interpretation into a cleaner human-readable guide.

Run:

```bash
uv run script-4a-summarize-overtime MA000018
```

You can also pass a specific interpretation path instead of an award code.

Main output:
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md`

Source selection behaviour:
- if `MA000018_overtime_interpretation_revised.md` exists, `4A` uses that;
- otherwise it falls back to `MA000018_overtime_interpretation.md`.

Formatting behaviour:
- the script strips the saved validation-notes preamble before prompting;
- the formatter should include only source-supported headings;
- unsupported headings should be omitted entirely rather than filled with placeholder text.

How to read the code:
- `resolve_interpretation_path()` explains how the script decides between award-code mode and path mode;
- `output_path_for_interpretation()` explains how the `4a_overtime_entitlements` filename is derived;
- `build_messages()` in the prompt module shows how the interpretation and template are combined.

## Step 5B. Generate and validate core overtime pseudocode

Main files:
- `src/script_5b_generate_overtime_pseudocode.py`
- `src/script_5b_validate_overtime_pseudocode.py`
- `src/prompts/core_overtime_pseudocode.py`

Purpose:
- generate implementation-oriented pseudocode for classifying ordinary hours and overtime hours;
- validate that pseudocode against a deterministic rule inventory derived from the source interpretation.

Run with an award code:

```bash
uv run script-5b-generate-overtime-pseudocode MA000018
```

Run with an explicit source file:

```bash
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

Main outputs:
- `data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md`
- `data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode_validation.json`
- `data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode_validation.md`

Source selection behaviour when an award code is used:
- prefer manual `4B` markdown if present;
- otherwise prefer `4A` markdown;
- otherwise prefer revised `3B`;
- otherwise use original step `3`.

How to read the code:
- `default_overtime_interpretation_path()` explains the source preference order;
- `load_overtime_rules()` shows how the script prefers rule JSON when available and falls back to markdown parsing when it is not;
- `generate_core_overtime_pseudocode()` shows the generate, validate, and repair loop.

## Award pipeline wrapper

Main file:
- `src/award_pipeline.py`

Purpose:
- run the active pipeline end to end;
- or run selected maintained steps while enforcing upstream file requirements.

Default run:

```bash
uv run award-pipeline MA000018
```

Default behaviour:
- runs steps `1`, `2`, `3`, and `3B`

Supported maintained steps in the wrapper:
- `1`
- `2`
- `3`
- `3b`
- `5b`

How to read the code:
- `build_paths()` shows the canonical artifact set for one award code;
- `run_step_1()` through `run_step_5b()` show the wrapper's orchestration responsibilities;
- `require_existing()` shows where upstream dependency checks happen.

## Streamlit review app

Main files:
- `review_outputs.py`
- `streamlit_review/app.py`
- `streamlit_review/output_data.py`

Purpose:
- inspect generated artifacts without opening each file manually;
- compare stages side by side;
- run the pipeline from a review surface;
- support manual editing of later-stage markdown;
- manage archive-backed saved edits.

Run:

```bash
uv run streamlit run review_outputs.py
```

What the app exposes:
- payment clauses
- payment clause categories
- ruleset clause classification
- expert A ruleset draft
- expert B ruleset draft
- comparison of expert outputs
- combined ruleset
- reviewer feedback and commentary
- final formatted ruleset
- manually edited ruleset
- pseudocode

Important code-reading points:
- `render_pipeline_run_controls()` is where sidebar pipeline actions are wired;
- `artifact_paths_for_award()` in `streamlit_review/output_data.py` shows which files the UI expects for a given award code;
- `source_path_for_manual_4b_editor()` and `source_path_for_core_overtime_pseudocode()` explain which upstream artifact the manual editor or pseudocode tooling prefers.

Manual `4B` note:
- there is no active scripted `4B` pipeline step in `src/`;
- the current `4B` concept is a manual Streamlit editing surface that saves `*_overtime_interpretation_4b.md`.

## Tests

Run all tests:

```bash
uv run pytest
```

Useful tests for understanding behaviour:
- `tests/test_fetch_award.py`
- `tests/test_payment_clause_classifier.py`
- `tests/test_overtime_interpretation.py`
- `tests/test_overtime_interpretation_review.py`
- `tests/test_overtime_entitlement_summary.py`
- `tests/test_overtime_pseudocode_validation.py`
- `tests/test_award_pipeline.py`
- `tests/test_streamlit_review_output_data.py`

These are good reading companions because they show expected outputs and boundary cases in a shorter form than the full implementation.

## Archived files

Reference-only code remains under `src/Archive/`.

Important examples:
- `src/Archive/gradio_app.py`
- `src/Archive/award_interpreter.py`
- `src/Archive/award_interpreter_prompt.py`

These are not part of the current maintained pipeline and should not be treated as the source of truth for current behaviour.
