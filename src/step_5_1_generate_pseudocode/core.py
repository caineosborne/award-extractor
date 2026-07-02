"""Shared step-local definitions for step 5.1 pseudocode generation."""

from __future__ import annotations

import os
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
DEFAULT_MODEL = "gpt-5.4-mini"
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
RULESET_CHOICES = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
)


class CoreOvertimePseudocodeError(RuntimeError):
    """Base exception for core overtime pseudocode failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load the OpenAI environment used by step 5.1."""
    from dotenv import load_dotenv

    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise CoreOvertimePseudocodeError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )
