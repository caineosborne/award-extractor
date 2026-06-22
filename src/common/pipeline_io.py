from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def load_text_file(
    path: Path | str,
    description: str,
    *,
    error_type: type[Exception] = RuntimeError,
) -> str:
    """Load a required text file and raise a domain-specific error when invalid."""
    selected_path = Path(path)
    if not selected_path.exists():
        raise error_type(f"{description} not found: {selected_path}")

    text = selected_path.read_text(encoding="utf-8")
    if not text.strip():
        raise error_type(f"{description} is empty: {selected_path}")

    return text


def load_json_object(
    path: Path | str,
    description: str,
    *,
    error_type: type[Exception] = RuntimeError,
) -> dict[str, Any]:
    """Load a required JSON object file and validate its top-level structure."""
    selected_path = Path(path)
    if not selected_path.exists():
        raise error_type(f"{description} not found: {selected_path}")

    try:
        with selected_path.open(encoding="utf-8") as json_file:
            data = json.load(json_file)
    except json.JSONDecodeError as exc:
        raise error_type(f"{description} is not valid JSON: {selected_path}") from exc

    if not isinstance(data, Mapping):
        raise error_type(f"{description} must contain a JSON object: {selected_path}")

    return dict(data)
