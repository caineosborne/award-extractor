Historical plan note:

This document captures an older refactor idea and is retained for reference only. The active pipeline has since moved to the numbered-step structure described in `resources/METHODOLOGY.md` and `resources/TECHNICAL_GUIDE.md`.

Refactor the overtime entitlement generation into two separate LLM steps.

Current state:
- `src/script_4a_summarize_overtime.py` reads payment classification JSON, filters Ordinary Hours & Overtime clauses, and generates `*_overtime_entitlements.md`.
- `src/script_5b_generate_overtime_pseudocode.py` reads that markdown and generates pseudocode.
- `src/script_4a_generate_overtime_clause.py` runs both steps together.

Required change:
Create an intermediate overtime interpretation document before the final reviewer-facing entitlement markdown.

New flow:
1. Classification JSON
2. Generate overtime interpretation working document
3. Generate reviewer-facing overtime entitlement markdown from the interpretation document
4. Generate core overtime pseudocode from the reviewer-facing markdown

The intermediate interpretation document should answer these questions:

# Overtime Interpretation Working Document

## Relevant Rules

## When does overtime occur?

## What happens when overtime occurs?

## What extra consequences exist?

## What data is required?

## What assumptions are being made?

Implementation requirements:
- Add a new module, probably `src/script_3_interpret_overtime.py`.
- It should read the payment classification JSON.
- It should filter the same Ordinary Hours & Overtime clauses currently used by `script_4a_summarize_overtime.py`.
- It should call the LLM and write `data/processed/<award>_overtime_interpretation.md`.
- Refactor `script_4a_summarize_overtime.py` so it reads the interpretation markdown, not the classification JSON directly.
- Keep the entitlement output path as `data/processed/<award>_overtime_entitlements.md`.
- Update `script_4a_generate_overtime_clause.py` so it runs:
  1. `generate_overtime_interpretation(...)`
  2. `summarize_overtime_entitlements(...)`
  3. `generate_core_overtime_pseudocode(...)`
- Preserve existing CLI commands where practical, but add a new CLI command for the interpretation step if needed.
- Update or add tests.
- Do not introduce defensive over-engineering.
- Keep code clear and audit-readable.
- Use uv commands.
- Run `uv run pytest` and fix failures.

Important design constraint:
The interpretation markdown is a working document. It does not need to be pretty. It should be structured enough for review and downstream generation, but downstream code should not depend on exact bullet formatting.

Update docs/comments if needed so the pipeline is clear.

A sepearte step will come through to move this data into the specific format required for the end user 
