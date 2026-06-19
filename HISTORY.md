# Award extractor history and pipeline

This document records the current extraction pipeline, what each main file does, and the current implementation status.

The project is designed to produce audit-readable artifacts from Australian modern award source material. The intended review trail is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Generate an overtime interpretation working document.
3B. Run a one-pass supervisor review and creator update of the overtime interpretation.
4A. Summarise overtime entitlements in plain English from the reviewed interpretation where available.
5B. Convert the entitlement summary into core ordinary/overtime pseudocode.
6. Review the generated artifacts for quality.

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
- `data/processed/<award>.json`
- `data/processed/<award>_sections.json`
- `data/processed/<award>.csv`

Main functions:
- `fetch(url)`: downloads the award page and parses it with BeautifulSoup.
- `extract_award_elements(main_content)`: extracts meaningful paragraph and table elements from Fair Work HTML classes.
- `nest_award_elements(elements)`: turns the flat extracted elements into a nested award clause tree.
- `extract_award(main_content)`: convenience function that extracts and nests the award structure.
- `build_section_index(award)`: creates a flat clause-reference lookup from the nested JSON.
- `iter_heading_rows(award)`: creates rows for the heading summary CSV.
- `write_outputs(url, main_content, award, raw_dir, processed_dir)`: writes the HTML, JSON, section index, and CSV outputs.

Current status:
- Implemented and covered by tests.
- Uses deterministic parsing logic rather than an LLM.
- Tables are preserved as structured objects where possible.
- Known limitation: the parser depends on Fair Work HTML classes and the `mainContent` element remaining consistent.

## 2. Payment clause classifier

Files:
- `src/script_2_classify_payments.py`
- `src/script_2_classify_payments_prompt.py`

Purpose:
- Read the structured award JSON.
- Send each top-level clause group to the LLM.
- Identify payment-relevant and definition-relevant clauses.
- Tag relevant direct L2 clauses with controlled payment categories.
- Attach the original clause text and model reason to each classified clause.

Command:

```bash
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
```

Main output:
- `data/processed/2_payment_clause_identifier/MA000018_payment_classification.json`
- A timestamped copy is also written, for example `MA000018_payment_classification_YYYYMMDD_HHMMSS.json`.

Main functions:
- `load_award(award_path)`: loads the processed award JSON.
- `iter_top_level_groups(award)`: builds one model request per top-level clause.
- `flatten_clause(reference, node)`: converts a clause subtree into labelled text for the model.
- `collect_descendants(parent_reference, node)`: gathers direct L2 clauses for classification.
- `build_messages(group)`: creates the system and user prompt for one classification request.
- `response_json_schema()`: defines the strict response schema used for the model call.
- `classify_group(group, client, model)`: sends one top-level group to the model and validates the response.
- `validate_group_classification(group, classification)`: checks returned references and attaches source text.
- `classify_award(...)`: orchestrates the full classification run and writes JSON output.

Current status:
- Implemented and covered by tests.
- Uses a strict JSON schema for the LLM response.
- Current schema version is `payment-classification-v2`.
- The classifier only classifies direct L2 clauses under a relevant top-level clause; lower-level clauses are included in the L2 text rather than returned as separate records.

## 3. Overtime interpretation working document

Files:
- `src/script_3_interpret_overtime.py`
- `src/Overtime_System_Prompt.py`

Purpose:
- Read the payment classification JSON.
- Filter to clauses tagged `Ordinary Hours & Overtime`.
- Ask the LLM to create a working interpretation document before reviewer-facing output is generated.
- Separate the legal interpretation questions from the final entitlement summary format.

Command:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Main output:
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md`

Main functions:
- `load_classification(classification_path)`: loads and validates the classification JSON.
- `filter_overtime_clauses(data)`: keeps only clauses tagged `Ordinary Hours & Overtime`.
- `output_path_for_classification(classification_path)`: derives the interpretation markdown output path.
- `build_messages(source_file, overtime_clauses)`: creates the interpretation prompt.
- `generate_overtime_interpretation(...)`: orchestrates filtering, model call, response extraction, and markdown writing.

Current status:
- Implemented and covered by tests.
- The working document uses this required structure:
  - `Relevant Rules`
  - `When does overtime occur?`
  - `What happens when overtime occurs?`
  - `What extra consequences exist?`
  - `What data is required?`
  - `What assumptions are being made?`
- This is a working artifact, not the end-user format.
- Downstream code should not depend on exact bullet formatting.

## 3B. Overtime interpretation supervisor review

File: `src/script_3b_review_overtime_interpretation.py`

Purpose:
- Run a temporary one-pass review step before the later agentic review process.
- Read the script 3 overtime interpretation working document.
- Read the step 2 payment classification JSON, then filter it to clauses tagged `Ordinary Hours & Overtime`.
- Ask an evaluator model for supervisor-style questions and concise issue notes without rewriting the document.
- Send that feedback to the creator model once so it can decide what to accept and write a revised interpretation.

Command:

```bash
uv run script-3b-review-overtime-interpretation MA000018
```

Main outputs:
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_evaluator_feedback.md`
- `data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_creator_response.md`
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md`

Main functions:
- `resolve_interpretation_path(...)`: accepts either an award code or a direct interpretation path.
- `resolve_classification_path(...)`: derives the step 2 classification path from the award code or interpretation filename unless a path is supplied.
- `build_evaluator_messages(...)`: packages the interpretation, filtered clauses, and script 3 system prompt for review.
- `build_creator_messages(...)`: packages the interpretation, filtered clauses, and evaluator feedback for the one-pass update.
- `parse_creator_update(output_text)`: splits the creator decision record from the revised interpretation.
- `review_overtime_interpretation(...)`: orchestrates filtered context, evaluator feedback, creator update, and output writing.

Current status:
- Implemented and covered by tests.
- Uses OpenRouter for the evaluator with model `anthropic/claude-sonnet-4.6`.
- The evaluator receives only the filtered `Ordinary Hours & Overtime` clauses.
- The process is strictly one-way: creator output, evaluator feedback, creator update. It does not loop.
- The CLI prints progress messages while loading inputs, waiting for the evaluator, waiting for the creator update, writing files, and completing.
- The shorthand award-code command derives:
  - `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation.md`
  - `data/processed/2_payment_clause_identifier/MAxxxxx_payment_classification.json`
- When this step is used, downstream step 4A should read the revised interpretation file.

## 4. Overtime entitlement summary

Files:
- `src/script_4a_summarize_overtime.py`
- `src/Overtime_System_Prompt.py`
- `resources/overtime_example.md`

Purpose:
- Read the overtime interpretation working document.
- Read `resources/overtime_example.md` as the default template for structure, formatting, wording, and level of detail.
- Ask the LLM to create a reviewer-facing markdown summary of overtime entitlements.
- Separate overtime triggers from overtime-related payment consequences and other considerations.
- Use the template as a generic plain-English rule generation pattern, without copying its award-specific facts, clause references, rates, assumptions, or rule outcomes.

Command:

```bash
uv run script-4a-summarize-overtime MA000018
```

Main output:
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md`

Main functions:
- `load_overtime_interpretation(interpretation_path)`: loads and validates the interpretation markdown.
- `load_reference_template(template_path)`: loads and validates the markdown template.
- `resolve_interpretation_path(award_or_interpretation_path)`: accepts either an award code or a direct interpretation path.
- `output_path_for_interpretation(interpretation_path)`: derives the markdown output path.
- `output_path_for_classification(classification_path)`: derives the entitlement path before the interpretation file exists.
- `strip_wrapping_markdown_fence(text)`: removes a full response-level markdown code fence before writing.
- `build_messages(source_file, interpretation_markdown, template_file, template_markdown)`: creates the entitlement-summary prompt.
- `summarize_overtime_entitlements(...)`: orchestrates markdown loading, model call, response extraction, and markdown writing.

Current status:
- Implemented and covered by tests.
- Prompt has been updated to use the reference template for the plain-English rule generation stage.
- The prompt now asks for:
  - `Source Rules`
  - `Specific Rule Breakdown`
  - `Overtime Interpretation`
  - `Overtime Entitlements`
  - `Additional consequences of working overtime`
  - `Required Data Inputs`
  - `Required Business Assumptions & Initial Ruleset`
  - `Rule priority`
- The markdown is intended to be clear enough for both human review and the next LLM step.
- When called with an award code, script 4A prefers `MAxxxxx_overtime_interpretation_revised.md` and falls back to `MAxxxxx_overtime_interpretation.md`.
- Revised interpretation inputs still write the canonical entitlement filename `MAxxxxx_overtime_entitlements.md`.
- Wrapping markdown fences returned by the model are stripped before writing the output.
- The rule priority section now uses an explicit allocation workflow: initialise hours as `Unallocated`, apply time-based overtime checks, then daily checks, then weekly or averaging-period checks, and finally move remaining `Unallocated` hours to `Ordinary`.
- Time/span/spread overtime checks should be applied before daily checks, and daily checks before weekly or averaging-period checks. Hours already moved to `Overtime` should not be reclassified by later checks.
- Humans may edit this file; downstream processing should not depend on exact markdown bullet formatting.

## 5. Core overtime pseudocode

Files:
- `src/script_5b_generate_overtime_pseudocode.py`
- `src/Overtime_System_Prompt.py`

Purpose:
- Read the overtime entitlement markdown.
- Ask the LLM to convert it into implementation-oriented pseudocode.
- Focus only on classifying worked hours as `Ordinary_Hours` or `Overtime_Hours`.
- Avoid allowance, dollar, multiplier, and penalty-rate calculations unless they affect hour classification.

Command:

```bash
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

Main output:
- `data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md`

Main functions:
- `load_overtime_summary(summary_path)`: loads and validates the entitlement markdown.
- `output_path_for_summary(summary_path)`: derives the pseudocode output path.
- `build_messages(source_file, overtime_summary_markdown)`: creates the pseudocode prompt.
- `generate_core_overtime_pseudocode(...)`: orchestrates markdown loading, model call, and pseudocode writing.
- `overtime_rule_bullets(markdown)`: legacy helper that extracts exact `- Overtime -` bullets. It remains tested, but the live pseudocode handoff no longer relies on it.

Current status:
- Implemented and covered by tests.
- The live handoff now sends the complete entitlement markdown to the LLM.
- This is intentionally format agnostic because humans may edit the markdown before pseudocode generation.
- The pseudocode prompt tells the model to read the document for meaning, not exact heading or bullet labels.

## 6. Combined overtime interpretation and entitlement generator

File: `src/script_4a_generate_overtime_clause.py`

Purpose:
- Run the overtime interpretation and entitlement summary steps as one command.
- Useful when regenerating overtime artifacts from a payment classification JSON.
- This command does not run the 3B supervisor review step.
- This command does not generate pseudocode.

Command:

```bash
uv run script-4a-generate-overtime-clause data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Main outputs:
- `data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md`
- `data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md`

Main functions:
- `generate_overtime_clause_artifacts(...)`: runs `generate_overtime_interpretation(...)`, then `summarize_overtime_entitlements(...)`.
- `interpretation_path_for_classification(...)`: determines the interpretation markdown path.
- `output_path_for_classification(...)`: determines the entitlement markdown path before the interpretation file exists.

Current status:
- Implemented and covered by tests.
- Uses the same model for both LLM calls unless a model override is supplied.
- For the reviewed workflow, prefer running scripts 3, 3B, and 4A separately so 4A can consume the revised interpretation.

## 7. Overtime quality reviewer

Files:
- `src/script_6_final_consistency_review.py`
- `script_6_final_consistency_review.py`

Purpose:
- Review the generated overtime artifacts against the payment classification JSON and the generation prompts.
- Identify unsupported rules, invented categories, invented thresholds, missing material rules, or traceability issues.
- Produce a markdown quality review that is readable by an audit or assurance reviewer.

Command:

```bash
uv run script-6-final-consistency-review \
  --classification-path data/processed/2_payment_clause_identifier/MA000018_payment_classification.json \
  --entitlements-path data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md \
  --pseudocode-path data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md
```

Main output:
- `data/processed/6_final_consistency_review/MA000018_overtime_quality_review.md`

Main functions:
- `script_6_final_consistency_review.py`: root-level wrapper that calls `src.script_6_final_consistency_review.main()`.
- `load_environment(env_path)`: loads the OpenRouter API key from `.env` or the environment.
- `build_openrouter_client(api_key)`: creates an OpenAI-compatible OpenRouter client.
- `load_text_file(path, description)`: loads and validates markdown inputs.
- `load_classification(path)`: loads and validates the payment classification JSON.
- `core_overtime_pseudocode_prompt()`: renders the current pseudocode system prompt for reviewer context.
- `evaluation_system_prompt()`: defines the quality reviewer role and required markdown structure.
- `build_messages(...)`: packages the classification JSON, generated markdown artifacts, and generation prompts for review.
- `extract_chat_completion_text(response)`: extracts text from an OpenRouter chat completion response.
- `output_path_for_pseudocode(pseudocode_path)`: derives the quality review output path.
- `evaluate_overtime_artifact_quality(...)`: orchestrates the review model call and writes the review markdown.

Current status:
- Implemented and covered by tests.
- Uses OpenRouter by default with model `qwen/qwen3-coder`.
- Requires `OPENROUTER_API_KEY` or `OPEN_ROUTER_API_KEY`.
- Console script entry exists in `pyproject.toml`; run it with `uv run script-6-final-consistency-review`.

## Current end-to-end status

Most recent local verification:

```bash
uv run pytest
```

Result:
- 54 tests passed.

Current pipeline commands:

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
uv run script-3b-review-overtime-interpretation MA000018
uv run script-4a-summarize-overtime MA000018
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
uv run script-6-final-consistency-review \
  --classification-path data/processed/2_payment_clause_identifier/MA000018_payment_classification.json \
  --entitlements-path data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md \
  --pseudocode-path data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md
```

Current design notes:
- `script_1_fetch_award.py` is deterministic.
- `script_2_classify_payments.py`, `script_3_interpret_overtime.py`, `script_3b_review_overtime_interpretation.py`, `script_4a_summarize_overtime.py`, `script_5b_generate_overtime_pseudocode.py`, and `script_6_final_consistency_review.py` use LLM calls.
- The overtime interpretation markdown is a working artifact between classification and reviewer-facing entitlement generation.
- The 3B revised interpretation is the preferred input for 4A when present.
- The entitlement markdown is a human-review artifact and may be manually edited.
- The entitlement rule priority is an implementation allocation method: begin with `Unallocated`, move time/span/spread overtime to `Overtime`, then daily overtime, then weekly or averaging-period overtime, and finally treat remaining unallocated hours as `Ordinary`.
- The pseudocode generator now reads the full entitlement markdown rather than relying on exact markdown bullet formatting.
- The quality reviewer is intended as an assurance layer, not as an automatic correction step.
