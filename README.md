# Award Extractor

This project produces audit-readable overtime interpretation artifacts from Australian modern awards.

Keep this file as the short entry point. The detailed documentation now lives in:

- `resources/METHODOLOGY.md`
- `resources/TECHNICAL_GUIDE.md`
- `resources/outputs.md`

## Current active pipeline

The current default pipeline is:

1. `1` = fetch and structure the award. This combines phases `1.1` and `1.2`.
2. `2.1` = classify payment-relevant clauses.
3. `2.2` = classify overtime-relevant clauses.
4. `3.1` = generate the overtime ruleset.
5. `3.2` = review and revise the ruleset.
6. `4.1` = format the ruleset.
7. `5.1` = generate pseudocode.

The default `award-pipeline` run goes through `3.2`.

Run the active pipeline end to end with:

```bash
uv run award-pipeline MA000018
```

Run later maintained steps with:

```bash
uv run award-pipeline MA000018 4.1
uv run award-pipeline MA000018 5.1
```

## Review app

Run the Streamlit review app with:

```bash
uv run streamlit run review_outputs.py
```

The app lets you inspect and compare intermediate artifacts, review expert outputs, edit the manual ruleset markdown, and inspect the later step `5.1` pseudocode outputs.
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
- step-3 ruleset selector for overtime creation vs overtime consequence

For step `3B`, the review screen shows both:
- the readable evaluator and creator markdown summaries; and
- the structured JSON artifacts, including evaluator rule-by-rule recommendations and proposed new rules.

## Tests

Run the test suite with:

```bash
uv run pytest
```
