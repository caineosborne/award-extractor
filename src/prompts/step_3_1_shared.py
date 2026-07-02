"""Shared prompt fragments for step 3.1 overtime ruleset generation."""

from __future__ import annotations


STEP_3_1_GENERIC_RULESET_LANGUAGE = """Generic interpretation rules:
- The source clauses are evidence. The output ruleset is the operational overtime logic that payroll would implement from that evidence.
- A clause and a ruleset item are not the same thing.
- A single clause may contain multiple distinct operational overtime rules. Extract each one separately when payroll would configure it separately.
- A single operational overtime rule may rely on multiple clauses when those clauses work together to describe one implementable rule.
- Preserve every operative threshold, span, limit, boundary, exception, condition, and qualification supported by the cited clause text.
- Do not collapse multiple operative rules from one clause into one vague summary.
- Do not omit one operative rule from a clause merely because another rule from the same clause is already represented.
- The unit of extraction is one operational overtime rule that a payroll reviewer could read and implement.
""".strip()


STEP_3_1_OVERTIME_TOPIC_LANGUAGE = """Overtime ruleset drafting rules:
- Convert the shortlisted overtime clauses into a reviewable overtime ruleset for payroll implementation.
- Each ruleset item must be clear enough for a payroll reviewer to configure as an operational rule.
- State the operative business rule itself, not just the clause citation.
- Keep clause references visible as supporting evidence, but do not rely on references as a substitute for the rule text.
- Keep the language definitive, concrete, and implementation-oriented.
""".strip()
