# Project Outputs

This inventory reflects the current numbered-step active pipeline.

Historical script-era names are retained only in archived notes and legacy folders.

| Step | Owner | Output | Output filename |
| --- | --- | --- | --- |
| 1 | `src/step_1_1_fetch/run.py`, `src/step_1_2_parse_award/run.py` | Raw award HTML from the Fair Work `mainContent` element | `data/processed/MAxxxxx/raw/1_1_raw.html` |
| 1 | `src/step_1_1_fetch/run.py`, `src/step_1_2_parse_award/run.py` | Structured award JSON by part and clause | `data/processed/MAxxxxx/1_2_award.json`; archive: `data/processed/MAxxxxx/archive/1_2_award_YYYYMMDD_HHMMSS.json` |
| 1 | `src/step_1_2_parse_award/run.py` | Flat section index JSON for clause lookup | `data/processed/MAxxxxx/supporting/1_2_sections.json`; archive: `data/processed/MAxxxxx/supporting/archive/1_2_sections_YYYYMMDD_HHMMSS.json` |
| 1 | `src/step_1_2_parse_award/run.py` | Heading summary CSV with part, L1, L2, and L3 references | `data/processed/MAxxxxx/supporting/1_2_heading_summary.csv`; archive: `data/processed/MAxxxxx/supporting/archive/1_2_heading_summary_YYYYMMDD_HHMMSS.csv` |
| 2.1 | `src/step_2_1_classify_payments/run.py` | Payment and definition clause classification JSON. Explicit overtime-trigger tag repairs may be recorded in `deterministic_tag_adjustments`. | `data/processed/MAxxxxx/2_1_payment_classification.json`; archive: `data/processed/MAxxxxx/archive/2_1_payment_classification_YYYYMMDD_HHMMSS.json` |
| 2.2 | `src/step_2_2_classify_overtime_clauses/run.py` | Overtime clause classification JSON including `employee_cohort`, `work_arrangement`, and `other_scope_notes` | `data/processed/MAxxxxx/2_2_OT_creation_clause_classification.json`; archive: `data/processed/MAxxxxx/archive/2_2_OT_creation_clause_classification_YYYYMMDD_HHMMSS.json` |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Expert A ruleset draft JSON and markdown | `data/processed/MAxxxxx/3_1_OT_creation_ruleset_expert_a.json`; `data/processed/MAxxxxx/3_1_OT_creation_ruleset_expert_a.md`; archives in `data/processed/MAxxxxx/archive/` |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Expert B ruleset draft JSON and markdown | `data/processed/MAxxxxx/3_1_OT_creation_ruleset_expert_b.json`; `data/processed/MAxxxxx/3_1_OT_creation_ruleset_expert_b.md`; archives in `data/processed/MAxxxxx/archive/` |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Comparison of expert outputs artifact | `data/processed/MAxxxxx/3_1_OT_creation_ruleset_comparison.json`; archive in `data/processed/MAxxxxx/archive/` |
| 3.1 | `src/step_3_1_generate_ruleset/run.py` | Combined ruleset JSON and markdown working document | `data/processed/MAxxxxx/3_1_OT_creation_ruleset.json`; `data/processed/MAxxxxx/3_1_OT_creation_ruleset.md`; archives in `data/processed/MAxxxxx/archive/` |
| 3.2 | `src/step_3_2_review_ruleset/run.py` | Evaluator feedback markdown and structured JSON | `data/processed/MAxxxxx/feedback/3_2_OT_creation_review.md`; `data/processed/MAxxxxx/feedback/3_2_OT_creation_review.json` |
| 3.2 | `src/step_3_2_review_ruleset/run.py` | Creator response markdown and structured JSON | `data/processed/MAxxxxx/feedback/3_2_OT_creation_creator_response.md`; `data/processed/MAxxxxx/feedback/3_2_OT_creation_creator_response.json` |
| 3.2 | `src/step_3_2_review_ruleset/run.py` | Revised overtime interpretation markdown and JSON | `data/processed/MAxxxxx/3_2_OT_creation_revised_ruleset.md`; `data/processed/MAxxxxx/3_2_OT_creation_revised_ruleset.json`; archives in `data/processed/MAxxxxx/archive/` |
| 4.1 | `src/step_4_1_format_ruleset/run.py` | Final formatted ruleset | `data/processed/MAxxxxx/4_1_OT_creation_formatted_ruleset.md`; archive: `data/processed/MAxxxxx/archive/4_1_OT_creation_formatted_ruleset_YYYYMMDD_HHMMSS.md` |
| 4.9 | Streamlit human review utility | Manual human-reviewed ruleset working file | `data/processed/MAxxxxx/3_2_OT_creation_revised_ruleset_manual.md` |
| 5.1 | `src/step_5_1_generate_pseudocode/run.py` | Core overtime pseudocode markdown | `data/processed/MAxxxxx/5_1_OT_creation_pseudocode.md`; archive: `data/processed/MAxxxxx/archive/5_1_OT_creation_pseudocode_YYYYMMDD_HHMMSS.md` |
| 5.1 validation | `src/step_5_1_generate_pseudocode/verification.py` | Validation JSON and validation markdown | `data/processed/MAxxxxx/5_1_OT_creation_pseudocode_validation.json`; `data/processed/MAxxxxx/5_1_OT_creation_pseudocode_validation.md` |

## Prompt Sources

| Step | Prompt source |
| --- | --- |
| 2.1 | `src/prompts/step_2_1_classify_payments.py` |
| 2.2 | `src/prompts/step_2_2_classify_overtime_clauses.py` |
| 3.1 | `src/prompts/step_3_1_generate_ruleset.py` |
| 3.2 | `src/prompts/step_3_2_review_ruleset.py` |
| 4.1 | `src/prompts/step_4_1_format_ruleset.py` |
| 5.1 | `src/prompts/step_5_1_generate_pseudocode.py` |

## Notes

- `4.9` is the active human review utility that sits between the formatted ruleset and the step `5.1` pseudocode source selection order.
- The parked agentic review path is no longer part of the active Streamlit surface or the active output inventory.
