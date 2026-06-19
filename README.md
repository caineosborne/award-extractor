# Award Extractor

This project extracts audit-readable payroll interpretation artifacts from Australian modern award data.

Detailed pipeline history and output tables are in `resources/HISTORY.md` and `resources/outputs.md`.

## Overtime Pipeline

Use `uv` to run project commands.

1. Fetch the award and write the step 1 outputs:

```bash
uv run script-1-fetch-award https://awards.fairwork.gov.au/MA000018.html
```

2. Classify payment clauses from a processed award JSON file:

```bash
uv run script-2-classify-payments data/processed/1_fetch_award/MA000018.json
```

3. Generate the overtime interpretation working document from the classification JSON:

```bash
uv run script-3-interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

This writes:

```text
data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md
```

The interpretation document is a working artifact. It should be structured enough for review and downstream generation, but downstream code should not depend on exact bullet formatting.

3B. Run a one-pass supervisor review and creator update for the overtime interpretation:

```bash
uv run script-3b-review-overtime-interpretation \
  data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md \
  --classification-path data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

This writes:

```text
data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_evaluator_feedback.md
data/processed/3_overtime_interpretations/feedback/MA000018_overtime_interpretation_creator_response.md
data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md
```

This is a one-way step only: creator output, supervisor feedback, then one creator update. The reviewer receives only the clauses tagged `Ordinary Hours & Overtime`, not the full payment classification JSON.

4A. Generate the reviewer-facing overtime entitlement markdown from the interpretation document:

```bash
uv run script-4a-summarize-overtime MA000018
```

When passed an award code, script 4A uses the revised script 3B interpretation if it exists:

```text
data/processed/3_overtime_interpretations/MA000018_overtime_interpretation_revised.md
```

If the revised file does not exist, it falls back to:

```text
data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md
```

This uses `resources/overtime_example.md` as the default structure and style template. The template is not source evidence; the generated rules should use only the selected interpretation document for award-specific facts.

This writes:

```text
data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

The rule priority section should describe an allocation workflow: start all worked hours as `Unallocated`, apply time-based overtime checks first, daily checks second, weekly or averaging-period checks third, then move any remaining `Unallocated` hours to `Ordinary`.

To run the overtime interpretation and entitlement summary steps together:

```bash
uv run script-4a-generate-overtime-clause data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

## Parked Pseudocode Step

Step 5B is parked while the project focuses on steps 1 through 4A. When it is resumed, generate core overtime pseudocode from the reviewer-facing entitlement markdown:

```bash
uv run script-5b-generate-overtime-pseudocode data/processed/4a_overtime_entitlements/MA000018_overtime_entitlements.md
```

This writes:

```text
data/processed/5b_generate_overtime_pseudocode/MA000018_core_overtime_pseudocode.md
```

The old script 6 final consistency review step has been removed from the active codebase and will be redesigned before use.

## Tests

Run the test suite with:

```bash
uv run pytest
```
