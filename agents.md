# AGENTS.md

## Project Standards

This project is intended for use in an audit / assurance environment.

Code must be:

* Clear
* Explicit
* Easy to review
* Easy to test
* Easy to explain to a non-developer reviewer

Readability is more important than cleverness or brevity.

## Package Management

Use `uv` for Python dependency management and execution.

Prefer:

```bash
uv run python ...
uv run pytest
uv add <package>
```

Do not introduce alternative package managers unless there is a clear reason.

## Code Style

Write straightforward Python.

Prefer a linear, easy-to-follow style that feels closer to a Jupyter notebook or Alteryx workflow than to a heavily abstracted software-engineering codebase.

When practical:

* Keep the main flow readable from top to bottom.
* Prefer a small number of larger, clearly named steps over many tiny helper functions.
* Group helpers near the top and keep the main execution path simple and sequential.
* Avoid indirection unless it clearly reduces complexity for a reviewer.

Avoid overly defensive programming.

Do not add broad `try/except` blocks unless there is a real expected failure mode and the handling is useful.

Bad:

```python
try:
    result = process(data)
except Exception:
    return None
```

Better:

```python
result = process(data)
```

If errors occur, they should usually fail loudly so they can be found and fixed.

## Clarity Over Brevity

Prefer clear intermediate variables over dense one-liners.

Prefer step-by-step code that can be read in sequence.

If a choice exists between:

* a more abstract reusable design, and
* a more linear design that is easier to follow in one pass

prefer the more linear design unless the abstraction clearly improves reviewability.

Bad:

```python
return [x for x in items if f(x) and g(x)]
```

Better:

```python
valid_items = []

for item in items:
    has_required_structure = f(item)
    is_supported = g(item)

    if has_required_structure and is_supported:
        valid_items.append(item)

return valid_items
```

## Notes and Comments

Notes should explain why something exists, not repeat what the code already says.

Good comments explain:

* Business logic
* Award interpretation decisions
* Assumptions
* Known limitations
* Audit-relevant reasoning

Avoid noisy comments that restate obvious code.

## Auditability

Where business rules are implemented, make the logic traceable.

Code should make it easy to answer:

* What rule is being applied?
* What input caused this result?
* What assumption was made?
* Where would a reviewer check this?

Prefer explicit functions with clear names over generic utility code.

## Testing

Use tests to document expected behaviour.

Each important rule should have at least one test.

Tests should be readable as examples of the business logic.

## Output

Outputs should be clear and explainable.

Avoid returning unexplained magic values.

Prefer structured outputs with meaningful field names.

## General Instruction

Do not optimise prematurely.

Do not make the code clever.

Make it boring, clear, and reliable.

## Business Logic

Business logic should be explicit.

Avoid generic frameworks, abstractions, or helper functions unless they reduce complexity.

Default to code that a reviewer can read top-to-bottom without mentally jumping across many files or many tiny functions.

A reviewer should be able to trace a business rule from:
- Award clause
- Interpretation
- Code
- Test case

without navigating multiple layers of indirection.

## Dependencies

Prefer the Python standard library where practical.

Do not introduce new dependencies without a clear benefit and asking to use it. 

Every dependency increases:
- maintenance burden
- security risk
- audit complexity

## Domain Terminology

Use consistent domain terminology throughout the project.

If my wording is ambiguous or technically inaccurate:

1. Explain the ambiguity briefly.
2. Recommend the preferred project terminology.
3. Use that terminology consistently.
4. Suggest additions to `resources/domain-glossary.md` when recurring concepts are identified.

Do not rename established domain concepts purely for readability.

## Simplicity

Organise code around the business workflow.

Prefer step-based folders and files that make the pipeline easy to follow from start to finish.

More files are acceptable when they clarify the workflow or separate real domain responsibilities.

Avoid abstractions whose main purpose is software-engineering elegance rather than reviewability.

Think like a domain expert building an auditable workflow, not a software engineer demonstrating design patterns.

## Challenge Complexity

If you believe a simpler implementation exists:

- Explain why.
- Suggest the simpler approach.
- Do not preserve complexity purely for engineering elegance.

Optimise for maintainability over extensibility.

## Code Reviews

During reviews:

- Look for unnecessary abstraction.
- Look for duplicated logic.
- Look for dead code.
- Look for opportunities to simplify.
- Verify behaviour before suggesting stylistic improvements.

## Domain First

The award and payroll domain is more important than generic software engineering conventions.

If the domain suggests a different structure than a typical software pattern, prefer the domain.

Use terminology consistently with the project's domain glossary.

## Design Decisions

When proposing a significant design change:

- Explain the trade-offs.
- Explain why the new approach is better.
- Mention any disadvantages.

## Terminology

Do not rename domain concepts for readability.

If a better term exists:

- explain why,
- recommend it,
- then use it consistently.

