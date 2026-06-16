import json


ALLOWED_TAGS = (
    "Hourly Rate",
    "Ordinary Hours & Overtime",
    "Penalty",
    "Allowance",
    "Breaks (Meal Breaks)",
    "Breaks (Between Work Periods)",
    "Leave",
    "Definition",
    "other",
)

DEFINITIONS = """Definitions:
- ordinary hours: The hours worked by an employee that do not include overtime. For example, the ordinary hours of a full-time employee are usually 38 hours per week.
- overtime: The time worked outside of ordinary hours. Awards and registered agreements state when overtime can be worked and the rate of pay for working overtime.
- penalty: A higher pay rate that can apply when an employee works evenings, weekends or public holidays. These rates are provided in awards and registered agreements.
- shiftworker: An employee who works fixed hours of work, such as shifts or rosters, that are outside or partly outside normal working hours, such as 9am to 5pm. Awards and registered agreements often provide a specific definition of shiftworker.
"""

TAG_DEFINITIONS = """Tag definitions:
- Hourly Rate: clauses related to an employee's base hourly rate, wage table, classification rate, minimum rate, or dollar amount per hour, excluding allowances.
- Ordinary Hours & Overtime: clauses defining ordinary hours, overtime hours, the boundary between ordinary and overtime hours, or minimum shift/payment periods tied to worked hours.
- Penalty: additional payment on top of ordinary hours for evenings, weekends, public holidays, shifts, or similar loadings.
- Allowance: additional payment based on duties, work type, location, equipment, expenses, qualifications, or skills, rather than the specific hours worked.
- Breaks (Meal Breaks): clauses about entitlement to meal breaks, lunch breaks, crib breaks, or payment when meal breaks are missed or interrupted.
- Breaks (Between Work Periods): clauses about required gaps, rest periods, or minimum breaks between shifts or work periods.
- Leave: payment clauses related to leave, including annual leave, paid leave, and annual leave loading. Annual leave loading is Leave, not Penalty.
- Definition: clauses defining payroll-relevant terms, including definitions of employee types, shiftworkers, ordinary hours terms, classifications, or other terms needed to interpret payment rules.
- other: payment-relevant clauses that do not fit the specific tags, including termination payments, redundancy payments, deductions, or other employee payment amounts.
"""

SYSTEM_PROMPT = f"""You are classifying Australian modern award clauses for payroll implementation.

This is not an award interpreter. Do not produce rules, pseudocode, pay calculations, or legal advice.

Classify whether the supplied top-level clause is relevant to payment and/or payroll definitions.
Then classify only the supplied direct L2 clauses when the top-level clause is payment-relevant or definition-relevant.

Top-level relevance:
- payment_relevant: true when any part of the L1 clause can affect the amount an employee is paid, including rates, ordinary/overtime boundaries, penalties, loadings, allowances, paid breaks, leave payments, termination payments, redundancy payments, deductions, or any other employee payment amount.
- definition_relevant: true when any part of the L1 clause defines a term needed to interpret payroll or payment rules.
- requires_l2_classification: true when either payment_relevant or definition_relevant is true. Otherwise false.

An L1 clause may be both payment-relevant and definition-relevant.

Allowed tags:
{chr(10).join(f"- {tag}" for tag in ALLOWED_TAGS)}

{DEFINITIONS}

{TAG_DEFINITIONS}

Return only valid JSON matching this shape:
{{
  "top_level_clause": {{
    "reference": "24",
    "title": "Breaks",
    "payment_relevant": true,
    "definition_relevant": false,
    "requires_l2_classification": true,
    "reason": "Short audit reason."
  }},
  "classified_clauses": [
    {{
      "reference": "24.1",
      "tags": ["Breaks (Meal Breaks)"],
      "reason": "Short audit reason."
    }}
  ]
}}

Rules:
- Use only the supplied references.
- Return only direct L2 references in classified_clauses.
- If payment_relevant and definition_relevant are both false, set requires_l2_classification to false and return an empty classified_clauses array.
- If payment_relevant or definition_relevant is true, classify direct L2 clauses that are relevant to payment and/or definitions.
- Direct L2 clauses may have multiple tags.
- If an L2 clause is both a definition and a payment clause, include Definition plus the relevant payment topic tags.
- Use the other tag only when the clause is payment-related but none of the more specific tags fit.
- Do not invent rates, percentages, thresholds, clauses, or references.
"""


def build_user_prompt(top_level_payload: dict) -> str:
    return (
        "Classify this top-level award clause and its direct L2 clauses.\n\n"
        "Clause payload JSON:\n"
        f"{json.dumps(top_level_payload, ensure_ascii=False, indent=2)}"
    )
