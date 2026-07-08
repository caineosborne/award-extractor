"""Step 2.2 stage 4: build deterministic penalties classifications."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.common.overtime_clause_classification import (
    OvertimeClauseClassification,
    OvertimeInterpretationError,
    PENALTIES_CLASSIFICATION,
    clause_source_text,
    normalized_employee_cohort_from_clause_text,
    normalized_work_arrangement_from_clause_text,
)


def deterministic_penalties_explanation(source_tags: Sequence[str]) -> str:
    """Explain why a clause was shortlisted for the penalties subset."""
    ordered_tags = [
        tag
        for tag in ("Penalty", "Breaks (Between Work Periods)")
        if tag in source_tags
    ]
    if not ordered_tags:
        return (
            "Included deterministically in the penalties subset based on the "
            "step 2.1 payment classification."
        )

    joined_tags = " and ".join(ordered_tags)
    return (
        "Included deterministically in the penalties subset because step 2.1 tagged "
        f"the clause as {joined_tags}."
    )


def build_deterministic_penalties_classifications(
    shortlisted_clauses: Mapping[str, object],
) -> list[OvertimeClauseClassification]:
    """Build the penalties subset without calling the LLM."""
    classifications: list[OvertimeClauseClassification] = []

    for clause_number in sorted(shortlisted_clauses):
        raw_clause = shortlisted_clauses[clause_number]
        if not isinstance(raw_clause, Mapping):
            continue

        source_text = clause_source_text(raw_clause)
        raw_tags = raw_clause.get("tags", [])
        source_tags = (
            tuple(str(tag) for tag in raw_tags)
            if isinstance(raw_tags, list)
            else ()
        )

        classifications.append(
            OvertimeClauseClassification(
                clause_number=clause_number,
                classification=PENALTIES_CLASSIFICATION,
                clause_text=source_text,
                explanation=deterministic_penalties_explanation(source_tags),
                employee_cohort=normalized_employee_cohort_from_clause_text(source_text),
                work_arrangement=normalized_work_arrangement_from_clause_text(
                    source_text
                ),
                other_scope_notes="",
                classifications=(PENALTIES_CLASSIFICATION,),
            )
        )

    if not classifications:
        raise OvertimeInterpretationError(
            "No penalties-related clauses were found in step 2 output."
        )

    return classifications
