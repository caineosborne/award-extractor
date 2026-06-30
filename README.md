# Award Extractor

This project produces audit-readable overtime interpretation artifacts from Australian modern awards.

Keep this file as the short entry point. The detailed documentation now lives in:

- `resources/METHODOLOGY.md`
- `resources/TECHNICAL_GUIDE.md`
- `resources/outputs.md`

## Current active pipeline

The current default pipeline is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Generate the overtime interpretation.
4. Review and revise the interpretation.

In code, that is steps `1`, `2`, `3`, and `3B`.

Run the active pipeline end to end with:

```bash
uv run award-pipeline MA000018
```

## Main commands

Fetch an award:

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
```

This writes the main award JSON and also generates the supporting section-index and heading-summary files automatically under `data/processed/1_fetch_award/supporting/`.

Classify payment clauses:

```bash
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
```

Generate the overtime interpretation:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Generate one explicit Phase 1 overtime ruleset:

```bash
uv run script-3-generate-overtime-ruleset data/processed/2_payment_clause_identifier/MA000018_payment_classification.json --ruleset overtime_creation
uv run script-3-generate-overtime-ruleset data/processed/2_payment_clause_identifier/MA000018_payment_classification.json --ruleset overtime_consequence
```

Run the two maintained step-3 sub-parts separately if needed:

```bash
uv run python src/script_3_part1_classify_overtime_clauses.py data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
uv run python src/script_3_part2_generate_overtime_interpretation.py data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

Review and revise the interpretation:

```bash
uv run script-3b-review-overtime-interpretation MA000018
```

Optional later maintained steps:

```bash
uv run script-4a-summarize-overtime MA000018
uv run script-5b-generate-overtime-pseudocode MA000018
```

## Review app

Run the Streamlit review app with:

```bash
uv run streamlit run review_outputs.py
```

The app lets you inspect and compare intermediate artifacts, review expert outputs, edit the manual `4B` markdown, and inspect the later `5B` pseudocode outputs.
The main review screens are now reviewer-facing:
- payment clauses
- payment clause categories
- ruleset clause classification
- expert A and expert B ruleset drafts
- comparison of expert outputs
- combined ruleset
- reviewer feedback and commentary
- final formatted ruleset
- manually edited ruleset
- pseudocode
- step-3 ruleset selector for overtime creation vs overtime consequence

For step `3B`, the review screen shows both:
- the readable evaluator and creator markdown summaries; and
- the structured JSON artifacts, including evaluator rule-by-rule recommendations and proposed new rules.

## Tests

Run the test suite with:

```bash
uv run pytest
```
