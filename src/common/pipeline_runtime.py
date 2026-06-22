from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def load_openai_environment(
    *,
    env_path: Path | str,
    error_type: type[Exception] = RuntimeError,
) -> str:
    """Load and validate the OpenAI API key from the environment."""
    load_dotenv(env_path)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise error_type(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )
    return api_key


def load_openrouter_api_key(
    *,
    env_path: Path | str,
    error_type: type[Exception] = RuntimeError,
) -> str:
    """Load and validate the OpenRouter API key from the environment."""
    load_dotenv(env_path)

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise error_type(
            "OpenRouter API key is not set. Add OPENROUTER_API_KEY or "
            "OPEN_ROUTER_API_KEY to the root .env file or export it."
        )

    return api_key


def build_openrouter_client(api_key: str) -> OpenAI:
    """Create an OpenAI-compatible client configured for OpenRouter."""
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
