# Award Extractor

This project extracts audit-readable payroll interpretation artifacts from Australian modern award data.

## Overtime Pipeline

Use `uv` to run project commands.

1. Classify payment clauses from a processed award JSON file:

```bash
uv run classify-payments data/processed/1_fetch_award/MA000018.json
```

2. Generate the overtime interpretation working document from the classification JSON:

```bash
uv run interpret-overtime data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

This writes:

```text
data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md
```

The interpretation document is a working artifact. It should be structured enough for review and downstream generation, but downstream code should not depend on exact bullet formatting.

3. Generate the reviewer-facing overtime entitlement markdown from the interpretation document:

```bash
uv run summarize-overtime data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md
```

This uses `resources/overtime_example.md` as the default structure and style template. The template is not source evidence; the generated rules should use only the interpretation document for award-specific facts.

This writes:

```text
data/processed/4_overtime_entitlements/MA000018_overtime_entitlements.md
```

4. Generate core overtime pseudocode from the reviewer-facing entitlement markdown:

```bash
uv run generate-overtime-pseudocode data/processed/4_overtime_entitlements/MA000018_overtime_entitlements.md
```

This writes:

```text
data/processed/4_overtime_entitlements/MA000018_core_overtime_pseudocode.md
```

To run the overtime interpretation, entitlement, and pseudocode steps together:

```bash
uv run generate-overtime-clause data/processed/2_payment_clause_identifier/MA000018_payment_classification.json
```

## Tests

Run the test suite with:

```bash
uv run pytest
```
