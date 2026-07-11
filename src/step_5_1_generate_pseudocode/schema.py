"""Step-local constants for step 5.1 pseudocode generation."""

from __future__ import annotations

from pathlib import Path

from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OVERTIME_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "MA000018"
    / "3_2_OT_creation_revised_ruleset.md"
)
DEFAULT_MODEL = "gpt-5.6-luna"
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
RULESET_CHOICES = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
)


class CoreOvertimePseudocodeError(RuntimeError):
    """Base exception for core overtime pseudocode failures."""
