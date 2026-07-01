"""LLM helpers for step 3.1 ruleset generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.overtime_rules import OvertimeRule
from src.common.overtime_rulesets import OVERTIME_CREATION_RULESET

from .core import (
    DEFAULT_MODEL,
    build_expert_comparison_messages,
    compare_expert_interpretation_runs,
    load_environment,
    request_structured_interpretation_run,
)


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 3.1 client."""
    load_environment()
    return OpenAI()


def selected_models(
    *,
    model: str | None,
    comparison_model: str | None,
) -> tuple[str, str]:
    """Resolve the generation and comparison models for step 3.1."""
    selected_model = model or os.getenv("OVERTIME_INTERPRETATION_MODEL", DEFAULT_MODEL)
    selected_comparison_model = comparison_model or os.getenv(
        "OVERTIME_INTERPRETATION_COMPARISON_MODEL",
        selected_model,
    )
    return selected_model, selected_comparison_model


def draft_expert_a(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run expert A for step 3.1."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def draft_expert_b(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run expert B for step 3.1."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def draft_additional_expert(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], list[str]]:
    """Run any additional expert draft beyond expert A and B."""
    rules, validation_warnings, _output_text = request_structured_interpretation_run(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        ruleset_key=ruleset_key,
    )
    return rules, validation_warnings


def merge_expert_drafts(
    *,
    client: Any,
    model: str,
    source_path: Path,
    overtime_creation_clauses: list[Any],
    run_a_rules: list[OvertimeRule],
    run_b_rules: list[OvertimeRule],
    ruleset_key: str = OVERTIME_CREATION_RULESET,
) -> tuple[list[OvertimeRule], dict[str, Any], list[str]]:
    """Merge expert A and expert B into one ruleset."""
    return compare_expert_interpretation_runs(
        client=client,
        model=model,
        source_path=source_path,
        overtime_creation_clauses=overtime_creation_clauses,
        run_a_rules=run_a_rules,
        run_b_rules=run_b_rules,
        ruleset_key=ruleset_key,
    )
