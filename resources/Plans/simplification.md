# Future Simplification Opportunities

This file is intentionally separate from `implemented_simplification.md`.

The major simplification program is complete. The items below are optional future improvements only.

They should be done only where they improve reviewability, operator workflow, or maintenance in a meaningful way.

## Recommendation

There is no remaining must-do simplification item for the active workflow.

If nothing below becomes painful in practice, it is reasonable to stop here.

## Potential improvements

### 1. Streamlit multi-select ruleset run control

Impact: Medium

Why it may be worth doing:

- improves operator flexibility by allowing creation, consequence, or both in one run;
- helps if a third ruleset is added later;
- is a workflow improvement more than a code simplification.

Why it may not be worth doing yet:

- the current single-select behaviour is clear and working;
- this adds UI and test complexity without reducing core pipeline complexity.

Recommendation:

- do this only if operators regularly need to run multiple rulesets together.

### 2. Remove or archive remaining historical compatibility files outside the active path

Impact: Medium

Why it may be worth doing:

- reduces confusion for reviewers who browse the repository;
- makes the active workflow more visually obvious.

Why it may not be worth doing yet:

- some old files still have historical or migration-reference value;
- deletion should be deliberate so useful context is not lost.

Recommendation:

- do this if the old files are causing navigation confusion, otherwise leave them parked.

### 3. Split larger deterministic modules only where the business flow becomes clearer

Impact: Low to Medium

Why it may be worth doing:

- a few step folders may read more clearly with separate `procedural.py` and `verification.py` files;
- this can help an audit reviewer see "what the step does" versus "how the step is checked".

Why it may not be worth doing yet:

- file splitting can create more indirection without real benefit;
- the current structure is already much clearer than before.

Recommendation:

- only split a module when the resulting files are each meaningfully easier to review.

### 4. Add one higher-level regression test for the full active workflow

Impact: High

Why it may be worth doing:

- gives strong confidence that the numbered-step workflow still hangs together end-to-end;
- protects the simplified structure from accidental drift.

Why it may not be worth doing yet:

- end-to-end tests are slower and usually more brittle than focused step tests;
- the current targeted tests already cover a lot of the active behaviour.

Recommendation:

- worthwhile if future changes become more frequent, especially in Streamlit and output-path logic.

### 5. Tighten documentation so only current operator-facing docs are prominent

Impact: Low

Why it may be worth doing:

- makes onboarding easier;
- reduces the chance that someone reads an old design note before a current one.

Why it may not be worth doing yet:

- documentation cleanup can consume time without changing runtime behaviour;
- the core active docs are already much better aligned now.

Recommendation:

- do this only if users are still getting lost between historical and current documents.

### 6. Step-internal linearisation pass

Impact: Medium to High

Why it may be worth doing:

- moves each step closer to the business workflow rather than the current technical `run.py` / `llm.py` / `deterministic.py` shape;
- makes the code easier for a reviewer to read top-to-bottom in one pass;
- reduces helper-hopping inside a step where the logic is really one sequential flow.

Why it may not be worth doing yet:

- this is a readability refactor, not a functional gap;
- done too broadly, it could create churn without enough benefit.

Suggested substeps:

1. Review one step at a time and choose only the steps that still feel jumpy or over-abstracted.
2. Rename internal files around business activities where that is clearer than technical categories.
3. Pull one-use helpers back closer to the main flow when this improves top-to-bottom readability.
4. Keep a simple visible sequence in each step:
   load inputs, prepare data, call model if needed, validate, write outputs.
5. Re-run the existing tests after each step-level refactor rather than attempting a repo-wide rewrite in one pass.

Recommendation:

- do this as a careful follow-on pass only when a specific step feels harder to review than it should be.
