# Project Outputs

| Step | Script | Output | Output filename |
| --- | --- | --- | --- |
| 1 | `src/script_1_fetch_award.py` | Raw award HTML from the Fair Work `mainContent` element | `data/processed/1_fetch_award/raw/MAxxxxx.html` |
| 1 | `src/script_1_fetch_award.py` | Nested award JSON by part and clause | `data/processed/1_fetch_award/MAxxxxx.json`; archive: `data/processed/1_fetch_award/archive/MAxxxxx_YYYYMMDD_HHMMSS.json` |
| 1 | `src/script_1b_generate_fetch_supporting_artifacts.py` | Flat section index JSON for clause lookup | `data/processed/1_fetch_award/supporting/MAxxxxx_sections.json`; archive: `data/processed/1_fetch_award/supporting/archive/MAxxxxx_sections_YYYYMMDD_HHMMSS.json` |
| 1 | `src/script_1b_generate_fetch_supporting_artifacts.py` | Heading summary CSV with part, L1, L2, and L3 references | `data/processed/1_fetch_award/supporting/MAxxxxx.csv`; archive: `data/processed/1_fetch_award/supporting/archive/MAxxxxx_YYYYMMDD_HHMMSS.csv` |
| 2 | `src/script_2_classify_payments.py` | Payment and definition clause classification JSON | `data/processed/2_payment_clause_identifier/MAxxxxx_payment_classification.json`; archive: `data/processed/2_payment_clause_identifier/archive/MAxxxxx_payment_classification_YYYYMMDD_HHMMSS.json` |
| 3 part 1 | `src/script_3_part1_classify_overtime_clauses.py` (also run via `src/script_3_interpret_overtime.py`) | Intermediate overtime clause classification JSON | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_clause_classification.json`; archive: `data/processed/3_overtime_interpretations/archive/MAxxxxx_overtime_clause_classification_YYYYMMDD_HHMMSS.json` |
| 3 part 2 | `src/script_3_part2_generate_overtime_interpretation.py` (also run via `src/script_3_interpret_overtime.py`) | Expert A ruleset draft JSON and markdown | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_expert_a.json`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_expert_a.md`; archives in `data/processed/3_overtime_interpretations/archive/` |
| 3 part 2 | `src/script_3_part2_generate_overtime_interpretation.py` (also run via `src/script_3_interpret_overtime.py`) | Expert B ruleset draft JSON and markdown | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_expert_b.json`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_expert_b.md`; archives in `data/processed/3_overtime_interpretations/archive/` |
| 3 part 2 | `src/script_3_part2_generate_overtime_interpretation.py` (also run via `src/script_3_interpret_overtime.py`) | Comparison of expert outputs artifact | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_comparison.json`; archive in `data/processed/3_overtime_interpretations/archive/` |
| 3 part 2 | `src/script_3_part2_generate_overtime_interpretation.py` (also run via `src/script_3_interpret_overtime.py`) | Combined ruleset JSON and markdown working document | `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation.json`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation.md`; archives in `data/processed/3_overtime_interpretations/archive/` |
| 3B | `src/script_3b_review_overtime_interpretation.py` | One-pass evaluator feedback, creator response, and revised interpretation | `data/processed/3_overtime_interpretations/feedback/MAxxxxx_overtime_interpretation_evaluator_feedback.md`; `data/processed/3_overtime_interpretations/feedback/MAxxxxx_overtime_interpretation_creator_response.md`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_revised.md`; archives in each output folder |
| 3B optional | `src/script_3b_agentic_review_workflow.py` via `src/script_3b_agentic_review_overtime_interpretation.py` | Optional multi-cycle creator/evaluator conversation and revised interpretation | `data/processed/3_overtime_interpretations/feedback/MAxxxxx_overtime_interpretation_agentic_review_conversation.md`; `data/processed/3_overtime_interpretations/MAxxxxx_overtime_interpretation_revised.md`; archives in each output folder |
| 4A | `src/script_4a_summarize_overtime.py` | Final formatted ruleset. Award-code input prefers the revised 3B interpretation if present, ignores the validation preamble, and omits unsupported headings. | `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements.md`; archive: `data/processed/4a_overtime_entitlements/archive/MAxxxxx_overtime_entitlements_YYYYMMDD_HHMMSS.md` |
| 4B | `src/script_4b_review_overtime_entitlements.py` | Temporary 4A entitlement accuracy review, updated answer, and final source-blind formatted markdown | `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements_initial_answer.md`; `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements_review_feedback.md`; `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements_updated_answer.md`; `data/processed/4a_overtime_entitlements/MAxxxxx_overtime_entitlements_final.md`; archives in `data/processed/4a_overtime_entitlements/archive/` |
| 5B | `src/script_5b_generate_overtime_pseudocode.py` | Core overtime pseudocode markdown. This step is parked for now. | `data/processed/5b_generate_overtime_pseudocode/MAxxxxx_core_overtime_pseudocode.md`; archive: `data/processed/5b_generate_overtime_pseudocode/archive/MAxxxxx_core_overtime_pseudocode_YYYYMMDD_HHMMSS.md` |

Script 6 final consistency review has been removed from the active codebase. Existing historical outputs under `data/processed/6_final_consistency_review/` have not been deleted.

## Prompt sources

| Step | Prompt source |
| --- | --- |
| 2 | `src/prompts/payment_clause_classification.py` |
| 3 | `src/prompts/overtime_interpretation.py` |
| 3B evaluator | `src/prompts/overtime_interpretation_review.py` |
| 3B creator update | `src/prompts/overtime_interpretation_review.py` |
| 3B agentic review | `src/script_3b_agentic_review_workflow.py` and `src/prompts/agentic_review.py` |
| 4A | `src/prompts/overtime_guide_formatting.py` |
| 4B accuracy evaluator | `accuracy_evaluation_system_prompt()` in `src/script_4b_review_overtime_entitlements.py` |
| 4B creator update | `src/script_4a_summarize_overtime_prompt.py` |
| 4B formatter | `build_formatting_messages()` in `src/script_4b_review_overtime_entitlements.py` |
| 5B | `CORE_OVERTIME_PSEUDOCODE_SYSTEM_PROMPT_TEMPLATE` in `src/script_5b_generate_overtime_pseudocode.py` |
