# Award Extractor

Award Extractor produces reviewable payroll-ruleset interpretation artifacts from Australian modern awards.

The project is an experimental, reviewer-assisted workflow. It is designed to make source clauses, interpretation decisions, validation warnings, and downstream artifacts easier to trace.

## Important limitation

This software does not provide legal advice and does not produce an authoritative payroll determination. Model-generated rulesets, pseudocode, and calculator drafts can be incomplete or incorrect.

Before using an output for payroll configuration or assurance work, a suitably qualified reviewer must check it against the current official award, applicable legislation, and the relevant employment circumstances. The official award source always takes precedence over this project's output.

## Documentation

- [Methodology](METHODOLOGY.md) explains the business workflow, review points, and interpretation boundaries.
- [Technical guide](TECHNICAL_GUIDE.md) explains pipeline ownership, model inputs and outputs, validation, and canonical output filenames.

## Current pipeline

The default pipeline runs these steps:

1. `1` — fetch and structure the award.
2. `2.1` — classify payment-relevant clauses.
3. `2.2` — build the selected ruleset clause subset.
4. `3.1` — generate the selected ruleset.
5. `3.2` — review and revise the ruleset.
6. `4.1` — format the ruleset.
7. `5.1` — generate pseudocode.
8. `6.1` — generate the calculator questionnaire JSON and calculator Python draft.

From step `2.2` onward, the active rulesets are:

- overtime creation;
- overtime consequence; and
- penalties.

## Setup

Requirements:

- Python 3.12 or later;
- [`uv`](https://docs.astral.sh/uv/); and
- an OpenAI API key with access to the models configured in the pipeline.

Install the project dependencies:

```bash
uv sync
```

Set the API key in your shell or in a local `.env` file:

```bash
export OPENAI_API_KEY="your-api-key"
```

The `.env` file is excluded from Git. Model-backed runs use the OpenAI API and may incur usage charges.

## Run the pipeline

Run the complete pipeline through step `6.1`:

```bash
uv run award-pipeline MA000018
```

Run one maintained step:

```bash
uv run award-pipeline MA000018 4.1
uv run award-pipeline MA000018 5.1
uv run award-pipeline MA000018 6.1
```

Run only selected rulesets by using `1` for overtime creation, `2` for overtime consequence, or `3` for penalties:

```bash
uv run award-pipeline MA000018 --subset 1 2
```

## Review application

Run the Streamlit review application:

```bash
uv run streamlit run review_outputs.py
```

The application exposes the source classifications, expert drafts, comparison artifact, structured review decisions, revised rulesets, formatting warnings, pseudocode, and calculator artifacts. It also allows a reviewer to save a manually edited ruleset for later pseudocode generation.

For a local PDF workflow, select **Add new award** in the sidebar. Enter an MA-style award code or upload a PDF without a code. When no code is entered, the PDF filename stem is used as the local output-set name.

## Rule traceability

The `rule-trace` utility checks whether rules from a supplied Python ruleset appear across named pipeline artifacts. Its `present_accurate` result means accurate relative to the supplied ruleset source of truth; it does not independently establish legal correctness against an award.

```bash
uv run rule-trace rules.py \
  --phase "Reviewed=reviewed.md" \
  --phase "Pseudocode=pseudocode.md" \
  --phase "Python Output=calculator.py" \
  --output rule_traceability.md
```

## Tests

```bash
uv run pytest
```

## Licence and reuse

No open-source licence is currently granted for this repository. Public visibility permits review of the source but does not grant permission to copy, modify, distribute, or use it commercially. Contact the repository owner if you want permission to reuse the project.
