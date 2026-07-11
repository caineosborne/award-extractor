"""Tests for PDF-specific Step 2.1 L2 reference reconciliation."""

from src.step_2_1_classify_payments.step_4_validate_classification import (
    resolve_direct_l2_reference,
)


def test_pdf_reference_mapping_keeps_each_full_l2_reference_with_its_own_clause():
    direct_references = {
        "4.1",
        "4.2",
        "4.3",
        "4.4",
        "4.5",
        "4.6",
        "4.7",
        "4.8",
        "4.9",
    }

    assert resolve_direct_l2_reference(
        "4",
        "4.2",
        direct_references,
        prefer_exact_full_references=True,
    ) == "4.2"
    assert resolve_direct_l2_reference(
        "4",
        "4.2.3",
        direct_references,
        prefer_exact_full_references=True,
    ) == "4.2"
    assert resolve_direct_l2_reference(
        "4",
        "4.2.3(a)",
        direct_references,
        prefer_exact_full_references=True,
    ) == "4.2"
    assert resolve_direct_l2_reference(
        "4",
        "4.4",
        direct_references,
        prefer_exact_full_references=True,
    ) == "4.4"
