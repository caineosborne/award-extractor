"""Step-local constants for step 3.2 ruleset review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.common.active_pipeline_paths import PROJECT_ROOT

DEFAULT_INTERPRETATION_PATH = (
    PROJECT_ROOT / "data" / "processed" / "MA000018" / "MA000018_overtime_interpretation.md"
)
EVALUATOR_MODEL = "gpt-5.4"
DEFAULT_CREATOR_MODEL = "gpt-5-mini"
DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS = 8000
DEFAULT_CREATOR_MAX_OUTPUT_TOKENS = 8000
DEFAULT_INTER_CALL_DELAY_SECONDS = 15.0
MAX_CREATOR_REPAIR_ATTEMPTS = 2
MAX_EVALUATOR_REPAIR_ATTEMPTS = 2


class OvertimeInterpretationReviewError(RuntimeError):
    """Base exception for overtime interpretation review failures."""


@dataclass(frozen=True)
class OvertimeInterpretationReviewArtifacts:
    """Store the output paths and text produced by the step 3.2 review workflow."""

    evaluator_feedback_path: Path
    evaluator_feedback_json_path: Path
    creator_response_path: Path
    creator_response_json_path: Path
    revised_interpretation_path: Path
    revised_interpretation_json_path: Path
    evaluator_feedback_markdown: str
    creator_response_markdown: str
    revised_interpretation_markdown: str
