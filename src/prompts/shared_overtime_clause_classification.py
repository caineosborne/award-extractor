"""Shared prompt text for overtime clause classification and interpretation."""

SHARED_OVERTIME_CATEGORIES = """- Ordinary Hours Boundary: defines ordinary hours limits, including ordinary hours per day, week, averaging period, span, spread, roster cycle, or ordinary hours arrangement.
- Overtime Trigger: directly states when hours are overtime or when overtime applies.
- Overtime Consequence: defines overtime rates, payment calculation, time off instead of payment, and additional meal breaks entitlements.  This is not restarting the overtime rules, it is stating what happens after overtime has been classified.  These clauses are only relevant where the hours are already to be determined to be overtime. 
- Related Rule: influences interpretation but does not itself create overtime and is not an overtime consequence.
- Not Relevant: does not materially affect the selected overtime ruleset."""


SHARED_PRIMARY_CLASSIFICATION_RULES = """- Choose `Ordinary Hours Boundary` as the primary classification when the main operative effect of the clause is to define the outer limit of ordinary hours.
- Choose `Overtime Trigger` as the primary classification when the main operative effect of the clause is to say when hours become overtime.
- Choose `Overtime Consequence` as the primary classification when the main operative effect of the clause is to say what payment or entitlement applies after overtime already exists.
- If a clause contains both trigger and consequence content, choose the primary classification based on the dominant payroll question answered by the clause, not merely the order the words appear in.
- Do not select `Not Relevant` when another label clearly applies."""
