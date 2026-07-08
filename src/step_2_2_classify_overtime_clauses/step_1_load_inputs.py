"""Step 2.2 stage 1: load environment and resolve default paths."""

from __future__ import annotations

from pathlib import Path

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    default_classification_path_for_award,
)
from src.common.overtime_clause_classification import OvertimeInterpretationError
from src.common.pipeline_runtime import load_openai_environment


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    """Load and validate the OpenAI environment used by step 2.2."""
    load_openai_environment(env_path=env_path, error_type=OvertimeInterpretationError)


DEFAULT_CLASSIFICATION_PATH = default_classification_path_for_award("MA000018")
