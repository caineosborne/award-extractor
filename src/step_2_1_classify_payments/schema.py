"""Shared schema and step-local definitions for step 2.1 payment classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_PATH = PROJECT_ROOT / "data" / "processed" / "MA000018" / "MA000018.json"
DEFAULT_MODEL = "gpt-5.4-mini"
SCHEMA_VERSION = "payment-classification-v2"
CONTENT_KEY = "_content"
PLACEHOLDER_PREFIX = "No Level"
SUBSTANTIVE_L1_MINIMUM_CHARACTERS = 30


class PaymentClauseClassifierError(RuntimeError):
    """Raised when the classifier cannot continue with the current award."""


@dataclass(frozen=True)
class DeterministicTagRule:
    """One explicit post-classification tagging rule for auditability."""

    rule_name: str
    tag_to_add: str
    patterns: tuple[str, ...]


EXPLICIT_OVERTIME_TRIGGER_RULES: tuple[DeterministicTagRule, ...] = (
    DeterministicTagRule(
        rule_name="explicit_overtime_will_be_paid",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bovertime will be paid\b",
            r"\bpaid overtime\b",
            r"\bovertime is payable\b",
        ),
    ),
    DeterministicTagRule(
        rule_name="explicit_paid_at_overtime_rates",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bpaid at overtime rates?\b",
            r"\bpayment of overtime\b",
        ),
    ),
    DeterministicTagRule(
        rule_name="explicit_overtime_provisions_apply",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(r"\bovertime provisions\b.*\bapply\b",),
    ),
    DeterministicTagRule(
        rule_name="explicit_without_payment_of_overtime",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(r"\bwithout payment of overtime\b",),
    ),
    DeterministicTagRule(
        rule_name="explicit_excess_hours_reference_to_overtime",
        tag_to_add="Ordinary Hours & Overtime",
        patterns=(
            r"\bfor work in excess of\b[\s\S]*\bovertime\b",
            r"\bfor work in excess of\b[\s\S]*\bpenalties specified\b",
        ),
    ),
)


@dataclass(frozen=True)
class ClauseItem:
    """Store one clause that may be sent to the model for tagging."""

    reference: str
    title: str
    text: str
    node: Mapping[str, Any]


@dataclass(frozen=True)
class TopLevelGroup:
    """Store one top-level clause and the direct L2 clauses grouped under it."""

    reference: str
    title: str
    text: str
    descendants: tuple[ClauseItem, ...]


@dataclass(frozen=True)
class DeterministicTagAdjustment:
    """Record one deterministic tag repair applied after model classification."""

    reference: str
    tag_added: str
    rule_names: tuple[str, ...]
