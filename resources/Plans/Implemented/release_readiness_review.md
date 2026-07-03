# Award Extraction Pipeline Release Readiness Review

Review date: 2026-07-02

Scope:
- `MA000002`
- `MA000018`
- `MA000120`

This review focuses on business-readiness as well as implementation quality.
The question is not only whether the code runs, but whether the outputs are dependable enough for payroll review, calculator integration, and broader modern-award generalisation.

## Executive summary

The refactor has improved structure and the test suite is green, but the pipeline is not yet release-ready for broad award processing without more tightening.

The strongest concern is the gap between the reviewer-facing outputs and the executable contract:
- some step 5 validation artifacts still report unresolved or failed rule coverage;
- the formatted guides repeat some rules across sections;
- the output inventory documentation no longer matches the actual on-disk filenames;
- the prompts still lean toward current-sample award shapes rather than a fully general modern-award workflow.

From a business perspective, that means the pipeline is producing useful drafts, but not yet a consistently trustworthy payroll specification.

## Findings

| Severity | Issue | Why it matters | Example | Recommended fix |
| --- | --- | --- | --- | --- |
| High | Step 5 pseudocode is not a stable calculator contract | The final implementation layer should be the clearest mapping from award rule to system behaviour. When validation still reports missing or unmatched rules, downstream calculator logic cannot rely on the pseudocode as complete. | `data/processed/MA000002/5_1_OT_creation_pseudocode_validation.json` still reports unresolved priority items and failed source-rule coverage for core trigger rules. `data/processed/MA000120/5_1_OT_consequence_pseudocode_validation.json` still has unresolved consequence rules for meal breaks, rest breaks, and rate rules. | Make clause references or stable rule IDs mandatory in every implementation bullet, and tighten validation so it matches exact business rules rather than text similarity. |
| High | Formatted outputs duplicate rules across sections | Payroll reviewers can interpret duplicated bullets as separate obligations, which creates double-counting risk and makes human review slower and less reliable. | In `data/processed/MA000002/4_1_OT_consequence_formatted_ruleset.md`, the same shiftwork rate rule appears in both the main cohort section and the shiftworker section. Similar duplication appears in `data/processed/MA000120/4_1_OT_consequence_formatted_ruleset.md`. | Keep one canonical location per rule and cross-reference it elsewhere instead of re-emitting the same rule text. |
| Medium | The formatter prompt is over-constrained to a fixed heading lattice | The rigid heading structure makes the output look consistent, but it can also force awkward buckets and hide award-specific business structure. That hurts generalisation across the wider modern-award set. | `src/prompts/step_4_1_format_ruleset.py` hardcodes a fixed tree of headings for both creation and consequence rules. `MA000018` ends up with many operationally different items forced into `Shift Workers > Other`. | Move toward a rule-driven heading structure that follows the actual source inventory, with fewer mandatory buckets. |
| Medium | Step 3.1 wording still drives a lot of scope correction churn | If the model is asked to simultaneously infer scope, write rules, and preserve traceability, it tends to produce broad or mis-scoped drafts that require heavy review-layer correction. That is slower and more fragile across awards. | `src/prompts/step_3_1_generate_ruleset.py` asks for cohort coverage, rule separation, and concise business wording in one pass. The resulting validation warnings across all three awards show repeated scope drift between `all`, `full-time`, `part-time`, `casual`, and `day worker` wording. | Split the prompt into clearer phases: scope extraction first, then business rule drafting. |
| Medium | Output inventory docs do not match the real files | This is an operational risk, not just a documentation issue. If the inventory is stale, reviewers and automation will look for the wrong supporting artifacts. | `resources/outputs.md` refers to `1_2_sections.json` and `1_2_heading_summary.csv`, but the actual canonical files are `1_2_award_sections.json` and `1_2_award.csv`. | Update the inventory to match the actual filenames and keep it aligned with the filesystem layout. |
| Low to Medium | Some trigger guides include context-only clauses without clear separation from operative rules | Business reviewers can misread context as an operative overtime trigger if the formatted guide does not distinguish them clearly. | `data/processed/MA000018/4_1_OT_creation_formatted_ruleset.md` includes rostered-days-off and continuity context in the general section, even though those items are supporting context rather than standalone triggers. | Label context explicitly and separate “background for interpretation” from “rule that creates overtime.” |

## Award-specific observations

### MA000002

- The creation guide is reasonably readable, but the step 5 validation shows the final pseudocode still misses broad coverage items such as weekly averages, daily caps, and shiftworker boundaries.
- The consequence guide is the most repetitive of the three samples. The same shiftwork consequence logic appears twice, which increases the risk of double-counting in a manual review.
- This award suggests the current prompt set can draft useful output, but the implementation layer still needs stronger traceability and de-duplication.

### MA000018

- The creation guide is structurally clean, but many operationally different rules are forced into a small number of fixed buckets.
- The pseudocode validation is not broken here, which is encouraging, but the output is still very dependent on the template structure rather than on the award’s own business shape.
- This award shows the best current end-to-end behaviour, but it also demonstrates how much the final presentation is driven by the prompt lattice.

### MA000120

- The creation guide is readable and business-facing, but the step 5 consequence validation still fails to cover several real consequence rules.
- The consequence guide is especially important from a payroll perspective because it mixes rate outcomes, minimum payments, rest-release rules, and TOIL handling. That mix needs stronger separation for calculator integration.
- This award is the clearest signal that the pipeline still needs work on consequence traceability and rule-to-output mapping.

## Prompt quality notes

The prompts are generally explicit, but several places would benefit from sharper business wording:

- `src/prompts/step_3_1_generate_ruleset.py`
  - good: strong emphasis on clause references and conservative drafting;
  - risk: asks the model to do too many jobs at once, which encourages over-broad or mis-scoped rules.

- `src/prompts/step_4_1_format_ruleset.py`
  - good: insists on readable reviewer-facing output;
  - risk: the fixed headings are too prescriptive and do not always match the award’s natural business structure.

- `src/prompts/step_5_1_generate_pseudocode.py`
  - good: requires a clear implementation-oriented contract;
  - risk: the required markdown structure and priority sections do not fully line up with the rule coverage that the validation layer is actually enforcing.

## Architecture notes

What is working well:
- the step separation is clear;
- deterministic path handling is much easier to follow than before;
- the reviewed artifacts are now easier to inspect than the older script-era outputs.

What still feels fragile:
- the pipeline still depends heavily on prompt wording to keep scope and consequence rules apart;
- the final pseudocode layer has not yet fully converged on a stable “calculator contract” shape;
- the fixed formatter structure is simpler to implement, but not yet clearly the best business structure for every award.

## Error-handling and validation notes

The test suite passes, but the artifact-level validations show the real gaps:
- unresolved priority items in the pseudocode validation files;
- failed coverage for several source rules;
- repeated rule text in the formatted guides;
- documentation drift between inventory and filesystem.

That means the code is not silently failing in the narrow technical sense, but the business outputs still have enough ambiguity that I would not treat the current pipeline as fully release-ready for arbitrary modern awards.

## Why Step 3.2 often needs a retry or refresh

This step is designed to retry once when the creator response does not validate.
That means the message you see is often not a crash, but the first pass of a strict schema-and-business-rule check failing.

The main reasons it happens are:
- the creator prompt is large, with roughly `39k` input tokens before the creator reply is even requested;
- the response must satisfy both a strict JSON schema and the downstream `apply_review_decisions(...)` business validation;
- the creator must return a very specific structure: `decision_record_markdown`, `rule_updates`, and `new_rule_reviews`;
- any missing or malformed `updated_rule`, unsupported `rule_id`, or incomplete decision set will fail validation;
- the retry budget is only one correction attempt (`MAX_CREATOR_REPAIR_ATTEMPTS = 1`), so there is not much room for recovery if the first correction is also off.

In business terms, this means Step 3.2 is sensitive to prompt bloat and schema fragility.
If the model slips once, the run often needs a refresh or a second attempt to finish cleanly.
That is acceptable as a recovery mechanism, but it is not yet ideal for a high-volume award-processing workflow.

## Testing gaps

Tests currently prove the pipeline runs, but they do not yet fully protect against:
- duplicate rules appearing in formatted guides;
- missing traceability from final pseudocode back to source clause references;
- stale filename inventories;
- rule-coverage regressions in the validation artifacts;
- overfitted heading structures that work for the current three sample awards but not for a wider award set.

Recommended regression tests:
- assert that formatted guides do not repeat the same rule text in multiple sections unless the duplication is explicitly cross-referential;
- assert that every implementation bullet in step 5 carries a stable source reference that matches the validation contract;
- assert that `resources/outputs.md` matches the actual on-disk canonical filenames;
- add snapshot tests for a representative creation award and consequence award that fail if a required rule becomes unresolved;
- add a test that checks the formatter does not force unrelated rules into `Other` when a clearer supported heading exists.

## Overall assessment

### Biggest remaining risks

1. The final pseudocode layer is still not a clean, complete contract for calculator implementation.
2. The formatted guides are readable, but repeated rules make manual review and downstream mapping harder.
3. The prompts still reflect the current award sample shapes more strongly than I would want for a general modern-award rollout.
4. The output inventory doc is already drifting from the actual filesystem, which is a maintainability risk.

### Top 10 improvements, highest ROI first

1. Make stable source references mandatory in step 5 implementation bullets.
2. Tighten step 5 validation to match exact rule coverage rather than text overlap.
3. Remove duplicated full-text rules from the formatted guides.
4. Relax the formatter into a more rule-driven heading structure.
5. Split step 3.1 drafting into narrower scope and drafting phases.
6. Align `resources/outputs.md` with the real filenames on disk.
7. Add regression tests for pseudocode coverage failures.
8. Add duplicate-rule detection tests for the formatted guides.
9. Separate context-only notes from true overtime triggers more explicitly.
10. Add one snapshot test for a consequence-heavy award and one for a trigger-heavy award.

### What I would fix before processing another 100 awards

- the step 5 traceability and coverage contract;
- the duplicate full-text bullets in the formatted outputs;
- the documentation drift in the output inventory;
- the formatter’s rigid heading structure;
- the most obvious prompt overfitting in step 3.1 and step 4.1.

## Notes for review

This memo is intended to sit alongside manual checks.
It does not change code or outputs.
It should be read together with:
- the generated award artifacts under `data/processed/MA000002/`, `data/processed/MA000018/`, and `data/processed/MA000120/`;
- the prompt definitions in `src/prompts/`;
- the output inventory in `resources/outputs.md`;
- the active pipeline docs in `resources/TECHNICAL_GUIDE.md` and `resources/METHODOLOGY.md`.
