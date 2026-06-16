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
