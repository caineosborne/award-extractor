"""LLM helpers for step 3.2 ruleset review."""

from __future__ import annotations

from openai import OpenAI

from .core import (
    build_openai_client,
    load_openai_environment,
    request_creator_revision,
    request_evaluator_feedback,
    selected_review_models,
)


def load_client() -> OpenAI:
    """Load the OpenAI environment and return a client for step 3.2."""
    load_openai_environment()
    return build_openai_client()


__all__ = [
    "load_client",
    "request_creator_revision",
    "request_evaluator_feedback",
    "selected_review_models",
]
