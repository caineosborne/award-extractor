# Outstanding Pieces

This document records current known gaps, design questions, and follow-up work items in the active overtime pipeline.

## Active issues

### Step 3 completeness validation gap between 3.2 and 3.4

Status:
- Open

Area:
- `src/script_3_interpret_overtime.py`

Current behaviour:
- Step `3.2` writes `*_overtime_clause_classification.json`.
- Step `3.4` validates that each generated overtime rule points back to at least one known shortlisted source clause from the step `3.2` result.
- Step `3.4` does not validate that every shortlisted clause from the `3.2` overtime-creation set is represented somewhere in the final step `3.4` rules JSON.

Why this matters:
- A clause can be present in the validated `3.2` output and still be omitted from the final step `3.4` interpretation without causing the script to fail.
- This means the current step `3.4` validation is traceability validation, but not completeness validation.
- In an audit context, this leaves a gap between "all shortlisted source clauses were considered" and "all shortlisted source clauses are represented or explicitly excluded".

Observed rule:
- Current validation requires:
  - each `3.4` rule to cite a known shortlisted clause;
  - each cited source classification to be allowed;
  - each rule object to be structurally valid.
- Current validation does not require:
  - every shortlisted `Ordinary Hours Boundary` or `Overtime Trigger` clause from `3.2` to appear in the `3.4` rules artifact.

Suggested follow-up:
- Add a deterministic completeness check after `validate_interpretation_rules()`.
- Compare the shortlisted `overtime_creation_clauses` set against the union of `source_clause_numbers` used by the final step `3.4` rules.
- Fail the step, or produce an explicit exception artifact, when a shortlisted clause is not represented.
- If the intended design is to allow exclusion, require an explicit structured exclusion record for each omitted shortlisted clause.

Reviewer question to resolve:
- Should step `3.4` require every shortlisted clause to appear in the final rules JSON, or should it allow omissions when the model gives an explicit structured reason for exclusion?

### Processed output layout should be award-first

Status:
- Open

Area:
- `data/processed/`
- path helpers under `src/common/`
- Streamlit review discovery and artifact loading

Current behaviour:
- Processed outputs are primarily grouped by artifact type and pipeline step.
- `data/processed/3_overtime_interpretations/` mixes multiple awards in one flat directory.
- Active files and archived versions are separated by artifact category rather than by review task.

Why this matters:
- One directory mixes multiple awards, which makes manual review harder.
- Active files and historical versions are separated by artifact type, not by the award being reviewed.
- Reviewing one award requires mentally filtering a long flat file list.
- The current structure is becoming harder to scan as more awards are processed.

Options discussed:

Option 1:
- Keep step-based folders, but group them under an award folder.

Example:

```text
data/processed/
  MA000002/
    1_fetch_award/
    2_payment_clause_identifier/
    3_overtime_interpretations/
    4a_overtime_entitlements/
    5b_generate_overtime_pseudocode/
    6_final_consistency_review/
  MA000018/
    ...
```

Option 2:
- Keep one award folder with the active artifacts together, plus an `archive/` folder inside the award folder.

Example:

```text
data/processed/
  MA000002/
    MA000002_payment_classification.json
    MA000002_overtime_clause_classification.json
    MA000002_overtime_interpretation.md
    MA000002_overtime_interpretation.json
    MA000002_overtime_interpretation_expert_a.md
    ...
    archive/
```

Recommended direction:
- Prefer Option 2.
- It better matches how the outputs are actually reviewed: award by award.
- It would make the Streamlit review flow, manual inspection, and cleanup tasks more straightforward.

Likely implementation impact:
- Update path builders in `src/common/`.
- Update artifact discovery and output loading in the Streamlit review app.
- Update archive-writing helpers so historical files stay grouped with the relevant award.
- Update any scripts or tests that currently assume global step-based output directories.

### Step 3 cohort and work-arrangement tagging may be needed

Status:
- Open

Area:
- `src/script_3_part1_classify_overtime_clauses.py`
- `src/script_3_part2_generate_overtime_interpretation.py`
- Screen 3 in the Streamlit review app

Current behaviour:
- Step `3.2` classifies shortlisted clauses by overtime role only.
- The clause-classification artifact records whether a clause is an `Ordinary Hours Boundary`, `Overtime Trigger`, `Overtime Consequence`, `Related Rule`, or `Not Relevant`.
- It does not explicitly record which employee cohort or work arrangement the clause applies to.
- Step `3.4` therefore still has to infer scope such as:
  - full-time / part-time / casual / all employees;
  - day worker / shiftworker / all arrangements.

Observed issue:
- In `MA000120`, clause `21.3` states:
  - `Ordinary hours may be worked between 6.00 am and 6.30 pm. Where broken shifts are worked the spread of hours can be no greater than 12 hours per day.`
- One expert run incorrectly turned that into a full-time-specific rule even though the clause itself is framed generally.
- Another expert run kept the clause broader, and the merged output preferred the broader reading.

Why this matters:
- The current structure makes it easier for a step `3.4` interpretation pass to import scope from nearby clauses or from a broader mental model of the award.
- This creates a risk that a correct overtime-role classification still leads to an incorrect employee cohort or work-arrangement scope in the final rule output.
- Reviewers currently have to detect that error only after the interpretation stage rather than during clause classification.

Possible follow-up:
- Extend step `3.2` so each shortlisted clause is also tagged for:
  - employee cohort: `full-time`, `part-time`, `casual`, `all employees`, or mixed;
  - work arrangement: `day worker`, `shiftworker`, `all`, or mixed.
- Show those scope tags on Screen 3 in the Streamlit review app so reviewers can inspect them before interpretation generation.
- Feed the scope tags into step `3.4` so the interpretation pass is constrained by explicit upstream scope data rather than inferring it from scratch.

Important design risk:
- Adding cohort or arrangement tags at clause level may create new errors when a clause is reviewed in isolation.
- Some clauses only become correctly scoped when read together with:
  - a separate employment-category clause;
  - a cross-reference;
  - a carve-out clause;
  - a shiftwork override;
  - or a general overtime entitlement clause.
- A clause-level scope tag may therefore over-narrow or over-broaden the clause if the classifier is forced to decide without enough surrounding context.

Reviewer question to resolve:
- Should step `3.2` add explicit cohort and arrangement tagging now, or would that create too much false certainty because clauses are still being assessed one by one rather than in full clause context?

