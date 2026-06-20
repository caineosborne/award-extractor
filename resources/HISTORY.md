# Award extractor history and pipeline

This document records the current extraction pipeline, main files, prompt ownership, and tidy-up status.

The project is designed to produce audit-readable artifacts from Australian modern award source material. The active pipeline is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Generate an overtime interpretation working document.
3B. Run a one-pass supervisor review and creator update of the overtime interpretation.
4A. Summarise overtime entitlements in plain English from the reviewed interpretation where available.
4B. Temporarily review the 4A entitlement output and produce a final human-readable markdown version.
5B. Convert the entitlement summary into core ordinary/overtime pseudocode. This step is parked until the upstream review flow is settled.

Script 6 final consistency review has been removed from the active codebase because that review step is expected to be redesigned before it is used again.

## Current folder structure

- `data/`: source and generated project data.
- `resources/`: documentation, plans, examples, and reference material.
- `review/`: human investigation notebooks and review work.
- `tests/`: automated investigation and regression tests.
- `src/`: active Python implementation, plus `src/Archive/` for old code retained for reference.

Root files are limited to project metadata and entry points:
- `README.md`
- `agents.md`
- `pyproject.toml`
- `uv.lock`
- `award_extractor.py`

## Prompt ownership

| Step | Script | Prompt source |
| --- | --- | --- |
| 2 | `src/script_2_classify_payments.py` | `src/script_2_classify_payments_prompt.py` |
| 3 | `src/script_3_interpret_overtime.py` | `src/script_3_interpret_overtime_prompt.py` |
| 3B evaluator | `src/script_3b_review_overtime_interpretation.py` | `evaluation_system_prompt()` in `src/script_3b_review_overtime_interpretation.py` |
| 3B creator update | `src/script_3b_review_overtime_interpretation.py` | `src/script_3_interpret_overtime_prompt.py` |
| 4A | `src/script_4a_summarize_overtime.py` | `src/script_4a_summarize_overtime_prompt.py` |
| 4B accuracy evaluator | `src/script_4b_review_overtime_entitlements.py` | `accuracy_evaluation_system_prompt()` in `src/script_4b_review_overtime_entitlements.py` |
| 4B creator update | `src/script_4b_review_overtime_entitlements.py` | `src/script_4a_summarize_overtime_prompt.py` |
| 4B formatter | `src/script_4b_review_overtime_entitlements.py` | `build_formatting_messages()` in `src/script_4b_review_overtime_entitlements.py` |
| 5B | `src/script_5b_generate_overtime_pseudocode.py` | `CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE` in `src/script_5b_generate_overtime_pseudocode.py` |

Scripts 3 and 4A no longer share a prompt file. Script 3 owns the working interpretation prompt. Script 4A owns the reviewer-facing entitlement summary prompt.

## 1. Fetch award

File: `src/script_1_fetch_award.py`

Purpose:
- Fetch a Fair Work award HTML page.
- Extract the `mainContent` HTML.
- Convert award headings, clauses, text blocks, bullets, and tables into structured JSON.
- Write a flat heading CSV to support human review of the extracted hierarchy.

Command:

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
```

Main outputs:
- `data/processed/1_fetch_award/raw/<award>.html`
- `data/processed/1_fetch_award/<award>.json`
- `data/processed/1_fetch_award/<award>_sections.json`
- `data/processed/1_fetch_award/<award>.csv`

Status:
- Implemented and covered by tests.
- Deterministic parser; no LLM call.
- Timestamped archive copies are written under `data/processed/1_fetch_award/archive/`.

## 2. Payment clause classifier

Files:
- `src/script_2_classify_payments.py`
- `src/script_2_classify_payments_prompt.py`

Purpose:
- Read structured award JSON.
- Send each top-level clause group to the LLM.
- Identify payment-relevant and definition-relevant clauses.
- Tag relevant direct L2 clauses with controlled payment categories.

Command:

```bash
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
```

Main output:
- `data/processed/2_payment_clause_identifier/MA000018_payment_classification.json`

Status:
- Implemented and covered by tests.
- Uses strict JSON schema.
- Current schema version is `payment-classification-v2`.
- Top-level clauses that contain only a heading and no direct L2 clauses are marked not relevant deterministically instead of being sent to the LLM.

## 3. Overtime interpretation working document

Files:
- `src/script_3_interpret_overtime.py`
- `src/script_3_interpret_overtime_prompt.py`

Purpose:
- Read payment classification JSON.
- Filter to clauses tagged `Ordinary Hours & Overtime`.
- Ask the LLM to create a working interpretation document before reviewer-facing output is generated.

Command:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Main output:
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md`

Status:
- Implemented and covered by tests.
- This is a working artifact, not the final reviewer format.

## 3B. Overtime interpretation supervisor review

File: `src/script_3b_review_overtime_interpretation.py`

Purpose:
- Run a one-pass supervisor review of the script 3 working document.
- Check the Script 3 clause classification and final interpretation against the full Script 2 payment classification JSON.
- Keep the review focused on whether a clause increases overtime entitlement by causing worked time to become overtime.
- Send the feedback back to the creator model once.
- Write feedback, creator decision record, and complete revised interpretation.

Command:

```bash
uv run script-3b-review-overtime-interpretation MA000018
```

Main outputs:
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_evaluator_feedback.md`
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_creator_response.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md`

Status:
- Implemented and covered by tests.
- Evaluator uses OpenRouter by default.
- Creator update uses the script 3 interpretation prompt.
- The process does not loop.

## 4A. Overtime entitlement summary

Files:
- `src/script_4a_summarize_overtime.py`
- `src/script_4a_summarize_overtime_prompt.py`
- `resources/overtime_example.md`

Purpose:
- Read the overtime interpretation working document.
- Prefer the revised 3B interpretation when called with an award code.
- Use `resources/overtime_example.md` as the default structure and style template.
- Create a reviewer-facing markdown summary of overtime entitlements.

Command:

```bash
uv run script-4a-summarize-overtime MA000018
```

Main output:
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md`

Status:
- Implemented and covered by tests.
- The template is not source evidence.
- The generated markdown is intended for human review and downstream pseudocode generation.

## 4B. Overtime entitlement review and final formatting

File: `src/script_4b_review_overtime_entitlements.py`

Purpose:
- Copy the 4A entitlement output as the initial answer.
- Run a source-aware accuracy review against the interpretation document and filtered `Ordinary Hours & Overtime` clauses.
- Send the feedback back to the creator model once to produce an updated entitlement answer.
- Run a source-blind wording and markdown formatting pass over the updated answer.
- Produce a final markdown file for human reading.

Command:

```bash
uv run script-4b-review-overtime-entitlements MA000018
```

Pipeline wrapper command:

```bash
uv run award-pipeline MA000018 4b
```

Main outputs:
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements_initial_answer.md`
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements_review_feedback.md`
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements_updated_answer.md`
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements_final.md`

Status:
- Implemented and covered by tests.
- Temporary review step.
- The accuracy review looks back to source material.
- The final formatting pass uses only the updated markdown and does not look back to source.

## Combined 3 and 4A runner

File: `src/script_4a_generate_overtime_clause.py`

Purpose:
- Run script 3 and script 4A together from one payment classification file.
- Useful for regeneration when the 3B review step is not needed.

Command:

```bash
uv run script-4a-generate-overtime-clause data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Status:
- Implemented and covered by tests.
- For the reviewed workflow, prefer running scripts 3, 3B, and 4A separately.

## 5B. Core overtime pseudocode

File: `src/script_5b_generate_overtime_pseudocode.py`

Purpose:
- Read the overtime entitlement markdown.
- Ask the LLM to convert it into implementation-oriented pseudocode.
- Focus only on classifying worked hours as `Ordinary_Hours` or `Overtime_Hours`.

Command:

```bash
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

Main output:
- `data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md`

Status:
- Implemented and covered by tests.
- Parked while the project focuses on steps 1 through 4A.

## Archived code

`src/Archive/award_interpreter.py` and `src/Archive/award_interpreter_prompt.py` are legacy prototype code. They are not part of the current pipeline.

`src/Archive/gradio_app.py` is the old Gradio prototype. It imports the archived interpreter. `gradio` has been removed from active project dependencies, so this app is retained for reference only.

`src/Archive/script_4a_prompt_Overtime_System_Prompt.py` is the old shared prompt file name. It is retained only to preserve history; active scripts now use step-specific prompt modules.

## Current pipeline commands

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
uv run script-3b-review-overtime-interpretation MA000018
uv run script-4a-summarize-overtime MA000018
uv run script-4b-review-overtime-entitlements MA000018
uv run award-pipeline MA000018 4b
```

Parked step:

```bash
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

## Current design notes

- `script_1_fetch_award.py` is deterministic.
- Scripts 2, 3, 3B, 4A, and 5B use LLM calls.
- The 3B revised interpretation is the preferred input for 4A when present.
- The entitlement markdown is a human-review artifact and may be manually edited.
- Archive folders are retained in both `src/Archive/` and generated data output folders.
- Repeated LLM connection code still exists in script files. It has not been abstracted yet because the current priority is explicit, reviewable business logic. A small client helper may be worthwhile later if repetition becomes a maintenance problem.
