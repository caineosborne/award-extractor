# Step Structure Checklist

Use this checklist when shaping new pipeline steps or refactoring existing ones.

## Core Rules

- Write code for review by auditors first, not for software engineers seeking optimisation.
- Prefer a linear, top-to-bottom process that can be read in one pass.
- Keep the main execution path explicit and easy to follow.
- Use helper functions only when they are clearly reused or materially improve readability.
- Name files after the business activity they perform, not just the implementation technique.
- Update the documentation whenever step boundaries or file ownership change.

## File Layout

- Keep one folder per business step where that helps the reviewer follow the workflow.
- Keep `run.py` thin; it should orchestrate, not hide the real logic.
- Put each distinct LLM call in its own file where possible.
- If a step repeats the same expert call multiple times, it is fine to keep those repeated expert calls in one file.
- Keep deterministic parsing, transformation, and writing separate when those are distinct reviewable stages.
- Keep shared helpers in a common file only when they are genuinely used in multiple places.
- Remove stub files if they do not contain real logic or a clearly defined future purpose.

## LLM Call Rule

- One LLM call should usually map to one file.
- A repeated expert pattern may live in one file if it is the same kind of work and the repetition is part of the design.
- Split into multiple files when the prompts, outputs, or review concerns are materially different.

## Good Reasons To Split Files

- The prompt is materially different.
- The output contract is materially different.
- The review burden is materially different.
- The code is easier to follow when the workflow is separated into distinct stages.

## Good Reasons To Keep Things Together

- The helper is only used once.
- Splitting would create more jumping around than clarity.
- The same logic is repeated only a small number of times and is easier to review together.

## Step Flow

Prefer this visible sequence:

1. Load inputs.
2. Prepare or parse data.
3. Call the model if needed.
4. Validate the result.
5. Write outputs.

## Review Standard

- Keep the code boring, explicit, and traceable.
- Make it easy to answer what happened, why it happened, and where the result came from.
- Prefer clarity over abstraction unless abstraction genuinely reduces review burden.
