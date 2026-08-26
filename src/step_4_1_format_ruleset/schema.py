"""Step-local constants for step 4.1 ruleset formatting."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_CODE = "MA000018"
# Step 4.1 must simplify legal-style rules without losing operational meaning.
# Use the quality-first model here; higher-volume extraction steps remain on Luna.
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "templates" / "Template.md"
DEFAULT_CONSEQUENCE_TEMPLATE_PATH = (
    PROJECT_ROOT / "templates" / "overtime_consequence_template.md"
)


class OvertimeEntitlementSummaryError(RuntimeError):
    """Raised when the overtime formatter cannot complete its work."""
