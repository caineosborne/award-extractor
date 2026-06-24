# Award Extractor Methodology

This note explains, step by step, how the current overtime extraction pipeline works, what each model call does, what each artifact means, and where deterministic logic is used instead of an LLM.

The aim of the pipeline is not to produce a final payroll calculation directly. The aim is to turn award source material into a sequence of structured and reviewable interpretation artifacts that can later support human review, downstream summarisation, and implementation work.

The current active manager-review path is:

1. Fetch and structure the award.
2. Classify payment-relevant clauses.
3. Build the original overtime extraction.
4. Review and revise the overtime extraction.

In code, those are steps `1`, `2`, `3`, and `3B`.

Active prompt content is stored separately under `src/prompts/`. The runtime scripts import prompt content from those modules rather than embedding instruction text directly.

## Design principles

The pipeline uses three different types of processing:

- Deterministic extraction and formatting.
- Structured LLM classification or generation.
- Review-oriented LLM feedback and revision.

The broad design logic is:

- deterministic code should do anything that can be done reliably without judgement;
- LLMs should return structured outputs wherever a machine-readable artifact is required;
- review steps should preserve traceability back to the earlier structured artifacts;
- every important intermediate artifact should be auditable on its own.

This means the pipeline does not ask one model to read the whole award and produce one final answer. Instead, it progressively narrows the source material and converts it into more specific interpretation artifacts.

## Step 1. Fetch and structure the award

File:
- `src/script_1_fetch_award.py`

This step is entirely deterministic.

Input:
- a Fair Work award URL such as `https://awards.fairwork.gov.au/MA000018.html`

Process:
- fetch the HTML;
- locate the `mainContent` section;
- convert the source into structured JSON;
- build a section index JSON;
- build a flat heading CSV for review.

Outputs:
- raw HTML snapshot;
- structured award JSON;
- section index JSON;
- heading CSV.

No model is used here. This step is the foundation for everything later. If the structure is wrong here, every later step will inherit the problem.

## Step 2. Payment clause classification

Files:
- `src/script_2_classify_payments.py`
- `src/prompts/payment_clause_classification.py`

Purpose:
- identify which clauses are relevant to payment or definition logic;
- tag the direct `L2` clauses that matter for downstream interpretation.

The unit of work is a top-level clause group. The script groups the award into top-level clauses and their direct `L2` descendants. Each top-level group is then sent to the model separately.

This matters because it keeps each model call bounded and auditable. A reviewer can later see which source clause group produced which classification result.

### What the model does

The model receives:
- the top-level clause text;
- the direct `L2` clauses underneath it.

It returns strict JSON containing:
- the top-level relevance decision;
- the clause-level classification results for the direct `L2` clauses.

The output is written to:
- `*_payment_classification.json`

### Validation in Step 2

There are two layers of validation:

1. API-level structured output:
- the model is asked to return strict JSON matching a schema.

2. Python-side validation:
- the returned top-level reference must match the clause group that was sent;
- returned clause references must map back to real direct `L2` clauses;
- non-relevant top-level clauses must not also return classified children.

If that validation fails, the step fails.

### Why Step 2 exists

This step is a narrowing step. It does not attempt to explain overtime. It only identifies the subset of the award that is likely to matter for payment logic and therefore for overtime interpretation.

## Step 3. Original overtime extraction

File:
- `src/script_3_interpret_overtime.py`

This stage has several sub-steps.

### Step 3.1. Filter overtime-related clauses

This is deterministic.

From the step-2 payment classification JSON, the code selects clauses tagged:
- `Ordinary Hours & Overtime`

This creates the candidate source pool for the overtime interpretation workflow.

### Step 3.2. Overtime clause classification

The model now receives only the clauses already tagged as ordinary-hours or overtime related.

Its job is to classify each shortlisted clause into one or more of:
- `Ordinary Hours Boundary`
- `Overtime Trigger`
- `Overtime Consequence`
- `Related Rule`
- `Not Relevant`

The output is strict structured JSON:
- `*_overtime_clause_classification.json`

This is still not the final interpretation. It is a classification layer that helps the pipeline distinguish:
- clauses that create overtime,
- clauses that only describe what happens after overtime already exists,
- and clauses that are relevant context but not direct triggers.

### Validation in Step 3.2

Again there are two layers:

1. structured schema validation;
2. code-side validation.

The code checks:
- every returned clause number was actually sent;
- there are no duplicates;
- every input clause was classified;
- the classifications are from the allowed set;
- the explanation is present.

If those checks fail, the step fails.

### Step 3.3. Filter to overtime-creation clauses

This is deterministic.

The code keeps only clauses whose classifications contain:
- `Ordinary Hours Boundary`
- or `Overtime Trigger`

This is the source pool for the interpretation-generation step.

The key logic here is that a clause may contain several labels, but it is still eligible if it contains one of the creation-oriented labels. This matters for mixed clauses such as broken shift or sleepover provisions.

### Step 3.4. Original overtime rule generation

This is now a band-of-experts step.

Instead of running one model pass and trusting that single answer, the active pipeline now runs two independent structured generations:

- expert A
- expert B

Each expert receives the same shortlisted clause pool and the same interpretation prompt.

Each expert returns a structured rule set. Each rule includes:
- `rule_id`
- `section_heading`
- `employee_scope`
- `clause_references`
- `rule_markdown`
- `rule_plain_text`
- `source_clause_numbers`
- `source_classifications`

Each expert output is written separately:
- `*_overtime_interpretation_expert_a.json`
- `*_overtime_interpretation_expert_a.md`
- `*_overtime_interpretation_expert_b.json`
- `*_overtime_interpretation_expert_b.md`

### Why use two expert runs

This step is where model variability is most visible.

Two runs may differ because:
- one splits a clause into multiple rules while the other combines it;
- one captures a daily shift-length boundary and the other misses it;
- one cites `22.1` broadly while the other specifically cites `22.1(c)`;
- one chooses different section headings or rule names.

The second run is not there to create an average answer. It is there to expose variability and reduce the risk that one omission becomes the only stored artifact.

### Expert comparison and merge

After the two expert runs, a comparison model is used to semantically compare and merge them.

The comparison model receives:
- the shortlisted source clauses from step `3.2`;
- expert A structured rules;
- expert B structured rules.

Its job is to return:
- a comparison summary;
- the list of run A rule IDs it accounted for;
- the list of run B rule IDs it accounted for;
- a merged structured ruleset;
- merge explanations that map merged rules back to run A and run B.

This comparison result is written to:
- `*_overtime_interpretation_comparison.json`

The final merged original overtime extraction is then written to the existing canonical path:
- `*_overtime_interpretation.json`
- `*_overtime_interpretation.md`

This preserves GUI compatibility and downstream compatibility while still keeping the expert artifacts visible for audit review.

### Validation in Step 3.4

Validation in step `3.4` now has three layers:

1. each expert run must produce a structurally valid rule list;
2. each merged comparison output must produce a structurally valid merged rule list;
3. the code checks that:
   - all expert A rule IDs were accounted for;
   - all expert B rule IDs were accounted for;
   - shortlisted source clauses are still represented in the merged rules.

Some problems still remain non-fatal by design. When the step finds issues that do not make the artifact unusable, it writes validation warnings into:
- the JSON artifact as `validation_warnings`;
- the markdown artifact as a `# Validation notes` block at the top.

That means the process can continue while still making the problem obvious to the reviewer.

### What Step 3 produces

Conceptually, Step 3 produces the first real interpretation artifact:
- a machine-readable JSON rules artifact;
- a human-readable markdown view of the same rules;
- expert A and expert B variants;
- a semantic comparison artifact explaining how the merged result was built.

## Step 3B. Supervisor review and creator revision

File:
- `src/script_3b_review_overtime_interpretation.py`

Step `3B` reviews the step-3 interpretation rather than re-extracting from scratch.

It uses:
- the step-2 payment classification JSON;
- the step-3 overtime clause classification JSON;
- the step-3 original overtime rules JSON and markdown.

### Evaluator role

The evaluator model acts as a supervisor. Its role is to identify:
- clause-classification issues;
- interpretation issues;
- presentation issues;
- traceability issues.

Its preferred output is structured JSON with:
- `summary_markdown`
- `rule_reviews`
- `new_rules`

That JSON is stored alongside a markdown feedback view.

The evaluator does not directly rewrite the interpretation. It comments on it.

### Creator role

The creator model receives:
- the original interpretation;
- the evaluator feedback;
- the original step-3 rules JSON.

Its job is to return structured decisions:
- one explicit decision for every original `rule_id`;
- optional new rules;
- a markdown decision record.

This is important because the machine contract for `3B` is rule-based. The pipeline validates that:
- every original rule was explicitly addressed;
- rules are not silently dropped;
- a rule cannot be removed unless both evaluator and creator explicitly support removal.

### Clause-drop warnings in 3B

The revised `3B` output also records clause-coverage warnings.

If a clause reference was present in the original step-3 rules and is no longer referenced in the revised step-3B rules, the revised JSON and markdown now carry a warning.

This supports human review by making reductions in clause coverage visible rather than silent.

### Outputs of Step 3B

Step `3B` writes:
- evaluator feedback markdown and JSON;
- creator decision record markdown and JSON;
- revised overtime interpretation markdown and JSON.

At this point the pipeline has:
- the original extraction;
- the supervisor feedback trail;
- the revised extraction.

That is the main active endpoint of the current project.

## Later retained steps

The repo still contains later steps, but they are not part of the current active manager-review path.

### Step 4A

This converts the revised `3B` overtime interpretation into a more polished human-readable overtime guide.

It uses `resources/Template.md` as a structure reference only. The template is not source evidence.

This is markdown generation rather than strict structured rule generation.

There is no longer an active scripted `4B` review chain in the main codepath. Instead, Streamlit provides a manual `4B` editor screen that starts from the generated `4A` markdown and saves a manually edited file when needed.

### Step 5B

This generates payroll-style pseudocode from the reviewed interpretation or the later `4A`/manual `4B` markdown artifact.

Its output is markdown, and the generation step is immediately followed by deterministic validation against a rule inventory. That validation is implemented in `src/script_5b_validate_overtime_pseudocode.py`, which is part of the normal `5B` flow rather than a separate manual process.

## How to read the pipeline end to end

The easiest way to understand the full method is:

1. Step 1 creates a deterministic source record.
2. Step 2 narrows the award to payment-relevant clauses.
3. Step 3 narrows again to overtime-related clauses.
4. Step 3.2 classifies those clauses by overtime role.
5. Step 3.4 creates two independent structured rule extractions.
6. A comparison model merges those expert outputs into one canonical original interpretation.
7. Step 3B critiques that canonical interpretation and revises it with explicit rule-level decisions.

So the calculation logic is not “one model, one answer”.

It is:
- source extraction,
- relevance filtering,
- role classification,
- dual expert rule generation,
- expert comparison and merge,
- supervisory review,
- explicit rule-level revision.

That layered approach is what makes the pipeline relatively auditable. Each stage has a narrower job than the stage before it, and each stage leaves behind an artifact that can be checked independently.
