"""Tests for audit coverage of Step 2.1 direct L2 clauses."""

from src.step_2_1_classify_payments.schema import ClauseItem, TopLevelGroup
from src.step_2_1_classify_payments.step_4_validate_classification import (
    validate_group_classification,
)


def test_relevant_l1_group_keeps_unclassified_direct_l2_clause_in_artifact():
    group = TopLevelGroup(
        reference="4",
        title="Hours of work",
        text="4: Hours of work",
        descendants=(
            ClauseItem("4.2", "Spread of hours", "4.2: Spread of hours", {}),
            ClauseItem("4.7", "Swapping shifts", "4.7: Swapping shifts", {}),
        ),
    )
    model_classification = {
        "top_level_clause": {
            "reference": "4",
            "title": "Hours of work",
            "payment_relevant": True,
            "definition_relevant": False,
            "requires_l2_classification": True,
            "reason": "Contains ordinary-hours rules.",
        },
        "classified_clauses": [
            {
                "reference": "4.2",
                "tags": ["Ordinary Hours & Overtime"],
                "reason": "Defines the spread of ordinary hours.",
            }
        ],
    }

    _top_level, classified = validate_group_classification(
        group,
        model_classification,
        prefer_exact_full_references=True,
    )

    assert classified["4.2"]["tags"] == ["Ordinary Hours & Overtime"]
    assert classified["4.7"] == {
        "text": "4.7: Swapping shifts",
        "tags": [],
        "reason": "No payment or definition category was assigned to this direct L2 clause.",
    }
