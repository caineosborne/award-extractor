"""Step 2.1 stage 6: build and write the classification artifact."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.output_paths import write_text_output

from .schema import SCHEMA_VERSION


def build_result_artifact(
    *,
    source_path: Path,
    model: str,
    top_level_clauses: OrderedDict[str, dict[str, Any]],
    classified_clauses: OrderedDict[str, dict[str, Any]],
) -> OrderedDict[str, Any]:
    """Build the final step 2.1 JSON artifact."""
    result: OrderedDict[str, Any] = OrderedDict()
    result["source_file"] = str(source_path)
    result["model"] = model
    result["schema_version"] = SCHEMA_VERSION
    result["top_level_clauses"] = top_level_clauses
    result["classified_clauses"] = classified_clauses
    return result


def write_result(destination: Path, result: OrderedDict[str, Any]) -> None:
    """Write the current step 2.1 classification artifact."""
    output_json = json.dumps(result, indent=2, ensure_ascii=False)
    write_text_output(destination, output_json)
