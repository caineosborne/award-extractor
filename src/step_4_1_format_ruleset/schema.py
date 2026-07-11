"""Step-local constants for step 4.1 ruleset formatting."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AWARD_CODE = "MA000018"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "resources" / "Templates" / "Template.md"
DEFAULT_CONSEQUENCE_TEMPLATE_PATH = (
    PROJECT_ROOT / "resources" / "Templates" / "overtime_consequence_template.md"
)


class OvertimeEntitlementSummaryError(RuntimeError):
    """Raised when the overtime formatter cannot complete its work."""
