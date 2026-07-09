# Award Extractor

This project produces audit-readable payroll ruleset interpretation artifacts from Australian modern awards.

Keep this file as the short entry point. The detailed documentation now lives in:

- `resources/METHODOLOGY.md`
- `resources/TECHNICAL_GUIDE.md`
- `resources/outputs.md`

## Current active pipeline

The current default pipeline is:

1. `1` = fetch and structure the award. This combines phases `1.1` and `1.2`.
2. `2.1` = classify payment-relevant clauses.
3. `2.2` = build the selected ruleset clause subset.
4. `3.1` = generate the selected ruleset.
5. `3.2` = review and revise the ruleset.
6. `4.1` = format the ruleset.
7. `5.1` = generate pseudocode.
8. `6.1` = generate the calculator questionnaire JSON and calculator Python draft.

From step `2.2` onward, the active rulesets are:
- overtime creation
- overtime consequence
- penalties

The default `award-pipeline` run goes through `5.1`.
Run `6.1` after the reviewed creation, consequence, and penalties rulesets exist.

Run the active pipeline end to end with:

```bash
uv run award-pipeline MA000018
```

Run later maintained steps with:

```bash
uv run award-pipeline MA000018 4.1
uv run award-pipeline MA000018 5.1
uv run award-pipeline MA000018 6.1
```

## Version 1 boundary

Version 1 is a reviewer-assisted extraction workflow. It produces auditable draft
rulesets, pseudocode, and calculator configuration artifacts. It does not claim
fully automated correctness across every modern award.

Expected ongoing iteration:
- prompt wording;
- step `6.1` questionnaire and calculator output shape;
- additional human intervention points;
- user-facing prompt review and editing.

## Review app

Run the Streamlit review app with:

```bash
uv run streamlit run review_outputs.py
```

The app lets you inspect and compare intermediate artifacts, review expert outputs, edit the manual ruleset markdown, inspect the step `5.1` pseudocode outputs, and review/edit the step `6.1` calculator questionnaire and Python draft.
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
- calculator questionnaire
- calculator Python
- step-3 ruleset selector for overtime creation, overtime consequence, and penalties

For step `3.2`, the review screen shows both:
- the readable evaluator and creator markdown summaries; and
- the structured JSON artifacts, including evaluator rule-by-rule recommendations and proposed new rules.

## Tests

Run the test suite with:

```bash
uv run pytest
```
