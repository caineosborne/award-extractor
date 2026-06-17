# Award extractor history and pipeline

This document records the current extraction pipeline, what each main file does, and the current implementation status.

The project is designed to produce audit-readable artifacts from Australian modern award source material. The intended review trail is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Summarise overtime entitlements in plain English.
4. Convert the entitlement summary into core ordinary/overtime pseudocode.
5. Review the generated artifacts for quality.

## 1. Fetch award

File: `src/fetch_award.py`

Purpose:
- Fetch a Fair Work award HTML page.
- Extract the `mainContent` HTML.
- Convert award headings, clauses, text blocks, bullets, and tables into structured JSON.
- Write a flat heading CSV to support human review of the extracted hierarchy.

Command:

```bash
uv run python src/fetch_award.py https://awards.fairwork.gov.au/MA000018.html
```

Main outputs:
- `data/raw/<award>.html`
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
- `src/payment_clause_classifier.py`
- `src/payment_clause_classifier_prompt.py`

Purpose:
- Read the structured award JSON.
- Send each top-level clause group to the LLM.
- Identify payment-relevant and definition-relevant clauses.
- Tag relevant direct L2 clauses with controlled payment categories.
- Attach the original clause text and model reason to each classified clause.

Command:

```bash
uv run classify-payments data/processed/MA000018.json
```

Main output:
- `data/processed/MA000018_payment_classification.json`
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

## 3. Overtime entitlement summary

Files:
- `src/overtime_entitlement_summary.py`
- `src/Overtime_System_Prompt.py`

Purpose:
- Read the payment classification JSON.
- Filter to clauses tagged `Ordinary Hours & Overtime`.
- Ask the LLM to create a reviewer-facing markdown summary of overtime entitlements.
- Separate overtime triggers from overtime-related payment consequences and other considerations.

Command:

```bash
uv run summarize-overtime data/processed/MA000018_payment_classification.json
```

Main output:
- `data/processed/MA000018_overtime_entitlements.md`

Main functions:
- `load_classification(classification_path)`: loads and validates the classification JSON.
- `filter_overtime_clauses(data)`: keeps only clauses tagged `Ordinary Hours & Overtime`.
- `output_path_for_classification(classification_path)`: derives the markdown output path.
- `build_messages(source_file, overtime_clauses)`: creates the entitlement-summary prompt.
- `summarize_overtime_entitlements(...)`: orchestrates filtering, model call, response extraction, and markdown writing.

Current status:
- Implemented and covered by tests.
- Prompt has been updated for v2 so the model does not invent unsupported top-level overtime categories.
- The prompt now asks for:
  - `Plain-English overtime triggers`
  - `Overtime-related payment consequences`
  - `Other considerations`
  - `Clause interpretation table`
  - `Rule priority`
  - `Assumptions and missing inputs`
- The markdown is intended to be clear enough for both human review and the next LLM step.
- Humans may edit this file; downstream processing should not depend on exact markdown bullet formatting.

## 4. Core overtime pseudocode

Files:
- `src/core_overtime_pseudocode.py`
- `src/Overtime_System_Prompt.py`

Purpose:
- Read the overtime entitlement markdown.
- Ask the LLM to convert it into implementation-oriented pseudocode.
- Focus only on classifying worked hours as `Ordinary_Hours` or `Overtime_Hours`.
- Avoid allowance, dollar, multiplier, and penalty-rate calculations unless they affect hour classification.

Command:

```bash
uv run generate-overtime-pseudocode data/processed/MA000018_overtime_entitlements.md
```

Main output:
- `data/processed/MA000018_core_overtime_pseudocode.md`

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

## 5. Combined overtime artifact generator

File: `src/overtime_clause_generator.py`

Purpose:
- Run the entitlement summary and pseudocode generation steps as one command.
- Useful when regenerating both artifacts from a payment classification JSON.

Command:

```bash
uv run generate-overtime-clause data/processed/MA000018_payment_classification.json
```

Main outputs:
- `data/processed/MA000018_overtime_entitlements.md`
- `data/processed/MA000018_core_overtime_pseudocode.md`

Main functions:
- `generate_overtime_clause_artifacts(...)`: runs `summarize_overtime_entitlements(...)` and then `generate_core_overtime_pseudocode(...)`.
- `output_path_for_classification(...)`: determines the entitlement markdown path.
- `output_path_for_summary(...)`: determines the pseudocode markdown path.

Current status:
- Implemented and covered by tests.
- Uses the same model for both LLM calls unless a model override is supplied.

## 6. Overtime quality reviewer

Files:
- `src/overtime_quality_evaluator.py`
- `overtime_quality_evaluator.py`

Purpose:
- Review the generated overtime artifacts against the payment classification JSON and the generation prompts.
- Identify unsupported rules, invented categories, invented thresholds, missing material rules, or traceability issues.
- Produce a markdown quality review that is readable by an audit or assurance reviewer.

Command:

```bash
uv run python overtime_quality_evaluator.py \
  --classification-path data/processed/MA000018_payment_classification.json \
  --entitlements-path data/processed/MA000018_overtime_entitlements.md \
  --pseudocode-path data/processed/MA000018_core_overtime_pseudocode.md
```

Main output:
- `data/processed/MA000018_overtime_quality_review.md`

Main functions:
- `overtime_quality_evaluator.py`: root-level wrapper that calls `src.overtime_quality_evaluator.main()`.
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
- At the time this file was written, this module and its tests are present in the working tree and should be added to version control if this quality review step is part of the intended pipeline.
- No console script entry has been added yet in `pyproject.toml`; run it with `uv run python overtime_quality_evaluator.py` or `uv run python -m src.overtime_quality_evaluator`.

## Current end-to-end status

Most recent local verification:

```bash
uv run pytest
```

Result:
- 35 tests passed.

Current pipeline commands:

```bash
uv run python src/fetch_award.py https://awards.fairwork.gov.au/MA000018.html
uv run classify-payments data/processed/MA000018.json
uv run summarize-overtime data/processed/MA000018_payment_classification.json
uv run generate-overtime-pseudocode data/processed/MA000018_overtime_entitlements.md
uv run python overtime_quality_evaluator.py \
  --classification-path data/processed/MA000018_payment_classification.json \
  --entitlements-path data/processed/MA000018_overtime_entitlements.md \
  --pseudocode-path data/processed/MA000018_core_overtime_pseudocode.md
```

Current design notes:
- `fetch_award.py` is deterministic.
- `payment_clause_classifier.py`, `overtime_entitlement_summary.py`, `core_overtime_pseudocode.py`, and `overtime_quality_evaluator.py` use LLM calls.
- The entitlement markdown is a human-review artifact and may be manually edited.
- The pseudocode generator now reads the full entitlement markdown rather than relying on exact markdown bullet formatting.
- The quality reviewer is intended as an assurance layer, not as an automatic correction step.
