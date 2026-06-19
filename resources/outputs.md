# Project Outputs

| Step | Script | Output | Output filename |
| --- | --- | --- | --- |
| 1 | `src/script_1_fetch_award.py` | Raw award HTML from the Fair Work `mainContent` element | `data/processed/1_fetch_award/raw/MAxxxxx.html` |
| 1 | `src/script_1_fetch_award.py` | Nested award JSON by part and clause | `data/processed/1_fetch_award/MAxxxxx.json`; archive: `data/processed/1_fetch_award/archive/MAxxxxx_YYYYMMDD_HHMMSS.json` |
| 1 | `src/script_1_fetch_award.py` | Flat section index JSON for clause lookup | `data/processed/1_fetch_award/MAxxxxx_sections.json`; archive: `data/processed/1_fetch_award/archive/MAxxxxx_sections_YYYYMMDD_HHMMSS.json` |
| 1 | `src/script_1_fetch_award.py` | Heading summary CSV with part, L1, L2, and L3 references | `data/processed/1_fetch_award/MAxxxxx.csv`; archive: `data/processed/1_fetch_award/archive/MAxxxxx_YYYYMMDD_HHMMSS.csv` |
| 2 | `src/script_2_classify_payments.py` | Payment and definition clause classification JSON | `data/processed/2_payment_clause_identifier/MAxxxxx_payment_classification.json`; archive: `data/processed/2_payment_clause_identifier/archive/MAxxxxx_payment_classification_YYYYMMDD_HHMMSS.json` |
| 3 | `src/script_3_interpret_overtime.py` | Overtime interpretation working document | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation.md`; archive: `data/processed/3_overtime_interpretations/archive/MAxxxxx_overtime_interpretation_YYYYMMDD_HHMMSS.md` |
| 3B | `src/script_3b_review_overtime_interpretation.py` | One-pass evaluator feedback, creator response, and revised interpretation | `data/processed/3_overtime_interpretations/feedback/MAxxxxx_overtime_interpretation_evaluator_feedback.md`; `data/processed/3_overtime_interpretations/feedback/MAxxxxx_overtime_interpretation_creator_response.md`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_revised.md`; archives in each output folder |
| 4A | `src/script_4a_summarize_overtime.py` | Reviewer-facing overtime entitlement summary. Award-code input prefers the revised 3B interpretation if present. | `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements.md`; archive: `data/processed/4a_overtime_entitlements/archive/MAxxxxx_overtime_entitlements_YYYYMMDD_HHMMSS.md` |
| 5B | `src/script_5b_generate_overtime_pseudocode.py` | Core overtime pseudocode markdown. This step is parked for now. | `data/processed/5b_generate_overtime_pseudocode/MAxxxxx_core_overtime_pseudocode.md`; archive: `data/processed/5b_generate_overtime_pseudocode/archive/MAxxxxx_core_overtime_pseudocode_YYYYMMDD_HHMMSS.md` |

`src/script_4a_generate_overtime_clause.py` is a combined runner for steps 3 and 4A. It writes the interpretation and entitlement summary outputs listed above.

Script 6 final consistency review has been removed from the active codebase. Existing historical outputs under `data/processed/6_final_consistency_review/` have not been deleted.

## Prompt sources

| Step | Prompt source |
| --- | --- |
| 2 | `src/script_2_classify_payments_prompt.py` |
| 3 | `src/script_3_interpret_overtime_prompt.py` |
| 3B evaluator | `evaluation_system_prompt()` in `src/script_3b_review_overtime_interpretation.py` |
| 3B creator update | `src/script_3_interpret_overtime_prompt.py` |
| 4A | `src/script_4a_summarize_overtime_prompt.py` |
| 5B | `CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE` in `src/script_5b_generate_overtime_pseudocode.py` |
