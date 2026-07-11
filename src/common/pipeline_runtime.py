from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_MAX_RETRIES = 5
DEFAULT_OPENAI_TIMEOUT_SECONDS = 600.0


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
    return build_openai_client(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )


def build_openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAI:
    """Create a client that retries transient API connection failures.

    A long pipeline makes occasional dropped connections expected. The OpenAI
    SDK retries connection failures automatically, but its default is only two
    retries. These settings are shared by every pipeline step so one temporary
    disconnect does not stop a Run all execution prematurely.

    The values can be overridden in .env when needed:
    OPENAI_MAX_RETRIES and OPENAI_TIMEOUT_SECONDS.
    """
    max_retries = int(
        os.getenv("OPENAI_MAX_RETRIES", str(DEFAULT_OPENAI_MAX_RETRIES))
    )
    timeout_seconds = float(
        os.getenv(
            "OPENAI_TIMEOUT_SECONDS",
            str(DEFAULT_OPENAI_TIMEOUT_SECONDS),
        )
    )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=max_retries,
        timeout=timeout_seconds,
    )
