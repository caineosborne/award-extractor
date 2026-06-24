"""Prompt helpers for the agentic step 3B review flow.

Used by:
- `src/script_3b_agentic_review_workflow.py`
"""

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
