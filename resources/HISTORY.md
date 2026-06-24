# Award extractor history and pipeline

This document records the current extraction pipeline, main files, prompt ownership, and tidy-up status.

The project is designed to produce audit-readable artifacts from Australian modern award source material. The current manager-review pipeline is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Generate an overtime interpretation working document.
3B. Run a one-pass supervisor review and creator update of the overtime interpretation.

Steps `4A`, `4B`, and `5B` remain in the repository but are currently in flux and are not part of the active manager-review path.

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
| 3.1 filter overtime clauses | `src/script_3_interpret_overtime.py` | No prompt. Deterministic filter for clauses tagged `Ordinary Hours & Overtime`. |
| 3.2 classify overtime clauses | `src/script_3_interpret_overtime.py` | System prompt: `OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT` in `src/script_3_interpret_overtime_prompt.py`. User prompt: `OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT` in the same file. |
| 3.3 filter interpretation clauses | `src/script_3_interpret_overtime.py` | No prompt. Deterministic filter for classifications `Ordinary Hours Boundary` and `Overtime Trigger`. |
| 3.4 generate overtime interpretation | `src/script_3_interpret_overtime.py` | System prompt: `OVERTIME_INTERPRETATION_SYSTEM_PROMPT` in `src/script_3_interpret_overtime_prompt.py`. User prompt: `build_overtime_interpretation_user_prompt()` in the same file. The active pipeline runs this interpretation generation twice and then uses a comparison prompt built inside `src/script_3_interpret_overtime.py` to merge the expert outputs. |
| 3B evaluator | `src/script_3b_review_overtime_interpretation.py` | `evaluation_system_prompt()` in `src/script_3b_shared_prompts.py` |
| 3B creator update | `src/script_3b_review_overtime_interpretation.py` | `src/script_3_interpret_overtime_prompt.py` |
| 3B optional agentic review | `src/script_3b_agentic_review_overtime_interpretation.py` and `src/script_3b_agentic_review_workflow.py` | Creator and evaluator prompts in `src/script_3b_shared_prompts.py` |
| 4A | `src/script_4a_summarize_overtime.py` | `src/script_4a_summarize_overtime_prompt.py` |
| 4B accuracy evaluator | `src/script_4b_review_overtime_entitlements.py` | `accuracy_evaluation_system_prompt()` in `src/script_4b_review_overtime_entitlements.py` |
| 4B creator update | `src/script_4b_review_overtime_entitlements.py` | `src/script_4a_summarize_overtime_prompt.py` |
| 4B formatter | `src/script_4b_review_overtime_entitlements.py` | `build_formatting_messages()` in `src/script_4b_review_overtime_entitlements.py` |
| 5B | `src/script_5b_generate_overtime_pseudocode.py` | `CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE` in `src/script_5b_generate_overtime_pseudocode.py` |

Scripts 3 and 4A no longer share a prompt file. Script 3 owns the working interpretation prompt. Script 4A owns the reviewer-facing entitlement summary prompt.

## LLM output and review contract

The pipeline uses LLMs in two different ways:

- Structured generation, where the model must return strict JSON and the code validates it before use.
- Free-text generation or review, where the model returns markdown or plain text for a human reader or for a later model step.

The main contracts are:

| Step | LLM role | Output form | Structured or free text | Strict pass/fail or feedback |
| --- | --- | --- | --- | --- |
| 2 | Payment clause classifier | JSON artifact written to `*_payment_classification.json` | Structured. Uses a strict JSON schema. | Strict pass/fail. The response must validate before it is accepted. |
| 3.2 | Overtime clause classifier | JSON artifact written to `*_overtime_clause_classification.json` | Structured. Uses a strict JSON schema. | Strict pass/fail. The response must validate before it is accepted. |
| 3.4 | Overtime interpretation generator | Two expert structured rules artifacts, one comparison artifact, and one merged working document | Structured first, then rendered to markdown. Two expert model runs produce structured rule outputs, then a comparison model merges them into the canonical rules artifact and markdown view. | Structured generation with deterministic post-checks. Non-fatal provenance and completeness issues are written into JSON and markdown as validation warnings rather than stopping the run. |
| 3B evaluator | Supervisor review of step 3 | Markdown feedback for the creator, with a companion JSON review artifact when the evaluator supports structured output | Mixed. The human-readable artifact is markdown feedback, but the preferred evaluator contract is structured JSON containing `summary_markdown`, rule-level recommendations, and proposed new rules. | Feedback, not a final gate. The evaluator points out issues and recommendations for the creator. |
| 3B creator update | Revision of step 3 interpretation | Revised markdown plus creator decision record, with a companion structured review-decision artifact when the creator returns valid JSON | Mixed. Preferred contract is structured JSON; human-readable artifacts are markdown. | Strict on machine-readability, but not a binary quality gate. The code tries to validate and apply the creator update; if structured output cannot be applied it falls back to a manual-review record and preserves the earlier rules. |
| Optional 3B agentic later evaluator cycles | Lightweight re-check after creator edits | Small JSON object like `{"status":"pass"|"needs_revision","reason":"..."}` | Structured. JSON only. | Strict pass/fail gate for later feedback cycles. This is the clearest binary reviewer decision in the repo. |
| 4A | Reviewer-facing entitlement summary generator | Markdown summary | Free text markdown. No response schema is enforced. | No hard gate inside 4A itself. It produces user-facing output for later review. |
| 4B accuracy evaluator | Review of the 4A entitlement summary | Markdown feedback | Free text markdown with required headings, but no strict response schema. | Feedback, not a binary gate. It tells the creator what to fix. |
| 4B creator update | Revision of the 4A entitlement summary | Markdown updated answer wrapped in expected tags | Free text markdown. The wrapper tags are parsed, but the content is not schema-driven. | Not a substantive pass/fail gate. It is a one-pass correction step driven by evaluator feedback. |
| 4B formatter | Final wording and formatting pass | Markdown final answer | Free text markdown. | Not a correctness gate. It improves wording and formatting after the source-aware review. |
| 5B | Pseudocode generator | Markdown pseudocode | Free text markdown. | Soft generation followed by hard deterministic validation. The model output itself is free text, but the code checks coverage against a source rule inventory and can request one repair pass. |
| 5B validation | Deterministic validator, not an LLM step | JSON and markdown validation reports | Structured deterministic output. | Strict pass/fail style reporting. Missing rule coverage is recorded explicitly in the validation artifacts. |

For audit purposes, the simplest summary is:

- Steps `2`, `3.2`, and `3.4` are the main strict structured-generation steps.
- Step `3B` is mainly a feedback workflow, although its preferred machine contract is also structured.
- Step `4A` and most of `4B` are markdown generation and markdown review, not schema-enforced reasoning steps.
- Step `5B` generates free-text markdown but is constrained after generation by deterministic validation.

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
- Ask the LLM to classify those clauses into five overtime interpretation categories.
- Filter the LLM clause classification to `Ordinary Hours Boundary` and `Overtime Trigger`.
- Run two independent expert generations over those boundary and trigger clauses.
- Use an LLM comparison pass to merge those expert outputs into one canonical structured rules artifact and one markdown working document before reviewer-facing output is generated.

Prompt use:
- Filtering clauses tagged `Ordinary Hours & Overtime` uses no prompt.
- Clause classification uses `OVERTIME_CLAUSE_CLASSIFICATION_SYSTEM_PROMPT` as the system prompt and `OVERTIME_CLAUSE_CLASSIFICATION_USER_PROMPT` as the user prompt.
- Filtering to `Ordinary Hours Boundary` and `Overtime Trigger` uses no prompt.
- Working interpretation generation uses `OVERTIME_INTERPRETATION_SYSTEM_PROMPT` as the system prompt and `build_overtime_interpretation_user_prompt()` as the user prompt.
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md` is the output of this step, not a prompt source.

Command:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Main output:
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_a.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_a.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_b.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_expert_b.json`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_comparison.json`

Status:
- Implemented and covered by tests.
- Clause classification is strict structured JSON.
- The active pipeline uses a band-of-experts approach for interpretation generation.
- Two expert rule-generation runs are compared and merged into the canonical step-3 rules JSON.
- The markdown working artifact is derived from the canonical merged rules JSON.
- Validation warnings can be written into the JSON and prepended to the markdown instead of failing the run for every non-fatal issue.
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
- Evaluator feedback is primarily reviewer feedback, not a hard accept/reject decision for the whole step.
- Preferred evaluator output is structured JSON with rule-level recommendations, but the saved human-facing artifact is markdown feedback.
- Creator update uses the script 3 interpretation prompt.
- Creator updates are validated for machine readability. If they cannot be applied safely, the earlier interpretation is preserved and a manual-review record is written.
- The process does not loop.

## Optional 3B. Agentic overtime interpretation review

Files:
- `src/script_3b_agentic_review_overtime_interpretation.py`
- `src/script_3b_agentic_review_workflow.py`

Purpose:
- Provide an alternate step `3B` review mode where a creator agent can request evaluator feedback across multiple bounded cycles.
- Capture the creator and evaluator exchange as a markdown conversation artifact.
- Produce a revised interpretation using the same Script 2 and Script 3 source artifacts as the one-pass review.

Command:

```bash
uv run script-3b-agentic-review-overtime-interpretation MA000018
```

Main outputs:
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_agentic_review_conversation.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md`

Status:
- Implemented and covered by tests.
- Optional workflow, not the default manager-review path.
- The first evaluator cycle is substantive feedback.
- Later evaluator cycles are lightweight structured pass/fail checks that return `pass` or `needs_revision`.
- Intended for deeper review loops when the one-pass `3B` output is not sufficient.

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
- Output is free-text markdown rather than schema-enforced JSON.
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
- The evaluator output is markdown feedback for the user or creator, not a strict pass/fail artifact.
- The creator update and formatter are also markdown generation steps rather than schema-enforced structured outputs.
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
uv run award-pipeline MA000018
```

Optional alternate review command:

```bash
uv run script-3b-agentic-review-overtime-interpretation MA000018
```

Later steps currently in flux:

```bash
uv run script-4a-summarize-overtime MA000018
uv run script-4b-review-overtime-entitlements MA000018
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
- Shared active-pipeline helpers now centralise path resolution, runtime setup, and basic artifact loading for steps 1 through 3B while keeping the business logic in the step modules.
