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



### Build a chat bot

Turn the output into a chatbot, allowing 