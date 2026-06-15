import json


ALLOWED_TAGS = (
    "Hourly Rate",
    "Ordinary Hours",
    "Overtime",
    "Penalty",
    "Allowance",
    "Breaks (Meal Breaks)",
    "Breaks (Between Work Periods)",
    "Leave",
    "other",
)

PAYMENT_EFFECTS = ("hourly_rate", "multiplier_impact", "none")

DEFINITIONS = """Definitions:
- ordinary hours: The hours worked by an employee that do not include overtime. For example, the ordinary hours of a full-time employee are usually 38 hours per week.
- overtime: The time worked outside of ordinary hours. Awards and registered agreements state when overtime can be worked and the rate of pay for working overtime.
- penalty: A higher pay rate that can apply when an employee works evenings, weekends or public holidays. These rates are provided in awards and registered agreements.
- shiftworker: An employee who works fixed hours of work, such as shifts or rosters, that are outside or partly outside normal working hours, such as 9am to 5pm. Awards and registered agreements often provide a specific definition of shiftworker.
"""

SYSTEM_PROMPT = f"""You are classifying Australian modern award clauses for payroll implementation.

This is not an award interpreter. Do not produce rules, pseudocode, pay calculations, or legal advice.

Classify whether the supplied top-level clause is relevant to payment, and classify its descendants when relevant.

Payment effects:
- hourly_rate: the clause determines the base hourly rate, wage table, classification rate, minimum rate, or dollar amount per hour.
- multiplier_impact: the clause changes how the base hourly rate is multiplied or applied, including overtime, penalty rates, loadings, weekend rates, public holiday rates, night rates, shift rates, or paid treatment of worked time.
- none: the clause is administrative, procedural, definitional, coverage-related, consultation-related, or otherwise does not determine a base rate or multiplier impact.

Important distinction:
- Clauses that only determine the base hourly rate should use the Hourly Rate tag and payment_effects ["hourly_rate"].
- Clauses that change percentages or multipliers, such as 125% of the hourly rate, should use payment_effects ["multiplier_impact"].

Allowed tags:
{chr(10).join(f"- {tag}" for tag in ALLOWED_TAGS)}

{DEFINITIONS}

Return only valid JSON matching this shape:
{{
  "top_level_clause": {{
    "reference": "24",
    "title": "Breaks",
    "payment_effects": ["multiplier_impact"],
    "requires_descendant_classification": true,
    "reason": "Short audit reason."
  }},
  "classified_clauses": [
    {{
      "reference": "24.1",
      "tags": ["Breaks (Meal Breaks)"],
      "payment_effects": ["multiplier_impact"],
      "reason": "Short audit reason."
    }}
  ]
}}

Rules:
- Use only the supplied references.
- If the top-level clause has payment_effects ["none"], set requires_descendant_classification to false and return an empty classified_clauses array.
- If the top-level clause has hourly_rate or multiplier_impact, classify descendants that are relevant to payment.
- Descendant clauses may have multiple tags.
- Use the other tag only when the clause is payment-related but none of the more specific tags fit.
- Do not invent rates, percentages, thresholds, clauses, or references.
"""


def build_user_prompt(top_level_payload: dict) -> str:
    return (
        "Classify this top-level award clause and its descendants.\n\n"
        "Clause payload JSON:\n"
        f"{json.dumps(top_level_payload, ensure_ascii=False, indent=2)}"
    )
