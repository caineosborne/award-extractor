"""Prompt helpers for the agentic step 3B review flow.

Used by:
- `src/script_3b_agentic_review_workflow.py`
"""

from __future__ import annotations


def build_evaluator_agent_instructions() -> str:
    return (
        "You are a supervisor reviewing an Australian modern award overtime "
        "creation interpretation. Follow the requested output format exactly. "
        "For substantive reviews, provide concise feedback only and do not rewrite "
        "the document. For pass/fail gate checks, return JSON only."
    )


def build_feedback_cycle_input(
    *,
    feedback_cycle: int,
    system_prompt: str,
    user_prompt: str,
) -> str:
    return f"Feedback cycle {feedback_cycle}.\n\n{system_prompt}\n\n{user_prompt}"


def build_agentic_source_context_prompt(
    *,
    interpretation_path: str,
    interpretation_markdown: str,
    interpretation_user_prompt: str,
) -> str:
    return f"""Original Script 3 interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Relevant source clauses for the first pass:

```markdown
{interpretation_user_prompt}
```
"""


def build_agentic_creator_input(source_context: str) -> str:
    return f"""Review and revise the existing Script 3 first draft.

Use the evaluator feedback tool before finalising unless the draft clearly needs no evaluator input.

{source_context}
"""
