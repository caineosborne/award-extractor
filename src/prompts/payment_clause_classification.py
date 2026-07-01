"""Prompt content for step 2 payment clause classification.

Used by:
- `src/step_2_1_classify_payments/llm.py`
"""

from __future__ import annotations

import json

from src.step_2_1_classify_payments.schema import TopLevelGroup

ALLOWED_TAGS = (
    "Hourly Rate",
    "Ordinary Hours & Overtime",
    "Penalty",
    "Allowance",
    "Breaks (Meal Breaks)",
    "Breaks (Between Work Periods)",
    "Leave",
    "Definition",
    "Other Payment",
)

DEFINITIONS = """Definitions:
- ordinary hours: The hours worked by an employee that do not include overtime. For example, the ordinary hours of a full-time employee are usually 38 hours per week.
- overtime: The time worked outside of ordinary hours. Awards and registered agreements state when overtime can be worked and the rate of pay for working overtime. 
- penalty: A higher pay rate that can apply when an employee works evenings, weekends or public holidays. These rates are provided in awards and registered agreements.
- shiftworker: An employee who works fixed hours of work, such as shifts or rosters, that are outside or partly outside normal working hours, such as 9am to 5pm. Awards and registered agreements often provide a specific definition of shiftworker.
"""

TAG_DEFINITIONS = """Tag definitions:
- Hourly Rate: clauses related to an employee's base hourly rate, wage table, classification rate, minimum rate, or dollar amount per hour, excluding allowances, and excluding specific multipliers or loadings (eg excluding statements like overtime will be paid at 200%, or night penalties will be paid at 150%)
- Ordinary Hours & Overtime: clauses defining ordinary hours, overtime hours, the boundary between ordinary and overtime hours, or minimum shift/payment periods tied to worked hours. This includes statements about payment for overitme, including statements like 'overtime will be paid at 150%'
- Penalty: additional payment on top of ordinary hours for evenings, weekends, public holidays, shifts, or similar loadings.  THis may be callsed shift workek allowance.  This includes statements about the payment multipliers for penalties, like 'night penalties will be paid at 115%'
- Allowance: additional payment based on duties, work type, location, equipment, expenses, qualifications, or skills, rather than the specific hours worked.
- Breaks (Meal Breaks): clauses about entitlement to meal breaks, lunch breaks, crib breaks, or payment when meal breaks are missed or interrupted. 
- Breaks (Between Work Periods): clauses about required gaps, rest periods, or minimum breaks between shifts or work periods. This includes broken shifts - where a shift is worked in two segments. 
- Leave: payment clauses related to leave, including annual leave, paid leave, and annual leave loading. Annual leave loading is Leave, not Penalty.
- Definition: clauses defining payroll-relevant terms, including definitions of employee types, shiftworkers, ordinary hours terms, classifications, or other terms needed to interpret payment rules.
- Other Payment: payment amount or payment entitlement clauses that do not fit the specific tags, such as termination payments, redundancy payments, deductions, reimbursement amounts, superannuation contributions, overaward payment treatment, take-home pay protection, or other employee payment amounts.
  Do not use Other Payment for non-payment clauses or payment-administration clauses that only describe how, when, or through which account wages are paid.
"""

SYSTEM_PROMPT = f"""You are classifying Australian modern award clauses for payroll implementation.

This is not an award interpreter. Do not produce rules, pseudocode, pay calculations, or legal advice.

Classify whether the supplied top-level clause is relevant to payment and/or payroll definitions.
Then classify only the supplied direct L2 clauses when the top-level clause is payment-relevant or definition-relevant.
If there are no supplied direct L2 clauses and the top-level clause itself contains substantive operative text, classify the top-level reference itself in classified_clauses.
L2 relevance is independent: a direct L2 clause can be irrelevant even when its L1 clause is relevant.

Top-level relevance:
- payment_relevant: true when any part of the L1 clause can affect the amount an employee is paid, including rates, ordinary/overtime boundaries, penalties, loadings, allowances, paid breaks, leave payments, termination payments, redundancy payments, deductions, or any other employee payment amount.
- definition_relevant: true when any part of the L1 clause defines a term needed to interpret payroll or payment rules.
- requires_l2_classification: true when either payment_relevant or definition_relevant is true. Otherwise false.

An L1 clause may be both payment-relevant and definition-relevant.
Prefer inclusion where the supplied clause text plausibly creates or changes a payment amount, payment entitlement, deduction, reimbursement, ordinary/overtime boundary, leave payment, allowance, penalty, rate, or payroll-relevant definition. However, do not mark a top-level clause as relevant from its heading alone where the supplied text contains no operative payment rule, payment entitlement, or payroll-relevant definition. For example, a top-level clause containing only "District allowances" with no amount, entitlement, condition, or cross-reference detail should be treated as not relevant.

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
- Use the supplied references exactly as written in the payload JSON.
- Return only direct L2 references in classified_clauses.
- Exception: if direct_l2_clauses is empty and the top-level clause text contains substantive operative text beyond the title, return the top-level reference itself in classified_clauses when it is payment-relevant or definition-relevant.
- If direct_l2_clauses is empty and the top-level clause text is only a title, heading, stub, or pointer with no operative payment rule or payroll-relevant definition, set payment_relevant and definition_relevant to false and return an empty classified_clauses array.
- If payment_relevant and definition_relevant are both false, set requires_l2_classification to false and return an empty classified_clauses array.
- If payment_relevant or definition_relevant is true, classify direct L2 clauses that are relevant to payment and/or definitions.
- Do not include an L2 clause merely because its parent L1 clause is relevant. Omit direct L2 clauses that do not themselves affect payment or define payroll-relevant terms.
- Do not use the Other Payment tag to mean irrelevant. Irrelevant direct L2 clauses must be omitted from classified_clauses.
- Distinguish these cases clearly:
  - Specific payment type: use the specific tag, such as Hourly Rate, Ordinary Hours & Overtime, Penalty, Allowance, Breaks, Leave, or Definition.
  - Other payment: use Other Payment only where the L2 clause creates or changes a payment amount, payment entitlement, deduction, reimbursement, termination payment, redundancy payment, superannuation contribution, overaward payment treatment, take-home pay protection, or similar payment outcome that does not fit a specific tag.
  - Non-payment or payment administration: omit the L2 clause. Do not tag clauses that only describe payment method, payment timing, payroll account nomination, consultation, notice, convenience, procedure, recordkeeping, or other process-only matters.
- Omit administrative, consultation, timing, convenience, notice, or process-only L2 clauses unless they directly create or change a payment amount, payment entitlement, ordinary/overtime boundary, or payroll-relevant definition.
- Direct L2 clauses may have multiple tags.
- If an L2 clause is both a definition and a payment clause, include Definition plus the relevant payment topic tags.
- Use the Other Payment tag only when the clause is payment-related but none of the more specific tags fit.
- A clause titled "Method of payment" that says wages are paid by cash or electronic funds transfer by payday is payment administration only. Omit it from classified_clauses.
- A clause requiring a deduction from wages, a termination payment, a redundancy payment, superannuation contribution, overaward payment treatment, take-home pay protection, or another payment amount not covered by the specific tags is Other Payment.
- A definitions clause with no direct L2 children but substantive definition text should be classified under its top-level reference, usually as Definition plus any clearly supported payment topic tags.
- Individual flexibility arrangement clauses are a common trap: classify the L2 clause that identifies the payment topics that may be varied, and classify any L2 clause that directly imposes a better-off-overall payment outcome. Omit procedural L2 clauses about genuine agreement, coercion, when an agreement may be made, written proposals, signatures, approval, recordkeeping, termination mechanics, or when the agreement ceases to operate unless the same L2 clause directly changes a payment amount or entitlement.
- For example, a clause saying time off is to be taken at convenient times after consultation is process-only and should be omitted unless it also changes a payment amount, payment entitlement, or ordinary/overtime boundary.
- Do not invent rates, percentages, thresholds, clauses, or references.
"""


def build_user_prompt(top_level_payload: dict) -> str:
    return (
        "Classify this top-level award clause and its direct L2 clauses.\n\n"
        "Clause payload JSON:\n"
        f"{json.dumps(top_level_payload, ensure_ascii=False, indent=2)}"
    )


def classification_payload_for_group(group: TopLevelGroup) -> dict:
    return {
        "top_level_clause": {
            "reference": group.reference,
            "title": group.title,
            "text": group.text,
        },
        "direct_l2_clauses": [
            {
                "reference": descendant.reference,
                "title": descendant.title,
                "text": descendant.text,
            }
            for descendant in group.descendants
        ],
    }


def build_messages(group: TopLevelGroup) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(classification_payload_for_group(group)),
        },
    ]
