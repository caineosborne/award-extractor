from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.active_pipeline_paths import PROJECT_ROOT, default_award_url_for_code, normalize_award_code
from src.common.output_paths import FETCH_AWARD_DIR, FETCH_AWARD_SUPPORTING_DIR


SOURCE_TYPE_FAIR_WORK_HTML = "fair_work_html"
SOURCE_TYPE_LOCAL_PDF = "local_pdf"
SOURCE_REGISTRY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "_source_registry" / "source_registry.json"
)
LEGACY_SOURCE_REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / FETCH_AWARD_DIR
    / FETCH_AWARD_SUPPORTING_DIR
    / "source_registry.json"
)
DOCUMENTS_DIR = PROJECT_ROOT / "resources" / "Documents"


def load_source_registry(
    registry_path: Path = SOURCE_REGISTRY_PATH,
) -> OrderedDict[str, dict[str, Any]]:
    """Load the saved source registry when present."""
    selected_registry_path = registry_path
    if (
        registry_path == SOURCE_REGISTRY_PATH
        and not registry_path.exists()
        and LEGACY_SOURCE_REGISTRY_PATH.exists()
    ):
        selected_registry_path = LEGACY_SOURCE_REGISTRY_PATH

    if not selected_registry_path.exists():
        return OrderedDict()

    with selected_registry_path.open(encoding="utf-8") as registry_file:
        data = json.load(registry_file, object_pairs_hook=OrderedDict)

    if not isinstance(data, dict):
        return OrderedDict()

    return OrderedDict((str(key), dict(value)) for key, value in data.items())


def write_source_registry(
    registry: OrderedDict[str, dict[str, Any]],
    registry_path: Path = SOURCE_REGISTRY_PATH,
) -> None:
    """Write the source registry in a stable reviewer-readable format."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def register_local_pdf_source(
    award_code: str,
    pdf_path: Path | str,
    display_name: str,
    registry_path: Path = SOURCE_REGISTRY_PATH,
) -> None:
    """Record that one output stem came from one local PDF."""
    registry = load_source_registry(registry_path)
    selected_pdf_path = Path(pdf_path)

    registry[str(award_code)] = {
        "source_type": SOURCE_TYPE_LOCAL_PDF,
        "source_path": str(selected_pdf_path),
        "display_name": display_name,
    }
    write_source_registry(registry, registry_path)


def source_record_for_award(
    award_code: str,
    registry_path: Path = SOURCE_REGISTRY_PATH,
) -> dict[str, Any]:
    """Resolve the source record for one award or EBA output stem."""
    registry = load_source_registry(registry_path)
    if award_code in registry:
        return registry[award_code]

    inferred_pdf_path = DOCUMENTS_DIR / f"{award_code}.pdf"
    if inferred_pdf_path.exists():
        return {
            "source_type": SOURCE_TYPE_LOCAL_PDF,
            "source_path": str(inferred_pdf_path),
            "display_name": award_code,
        }

    normalized_award_code = normalize_fair_work_award_code(award_code)
    if normalized_award_code is not None:
        return {
            "source_type": SOURCE_TYPE_FAIR_WORK_HTML,
            "source_url": default_award_url_for_code(normalized_award_code),
            "display_name": normalized_award_code,
        }

    raise ValueError(
        f"Could not resolve a source for {award_code}. "
        "Register the local PDF first or use a real MA award code."
    )


def normalize_fair_work_award_code(value: str) -> str | None:
    """Return a normalized MA award code or None when the value is not one."""
    try:
        return normalize_award_code(value)
    except ValueError:
        return None


def can_run_pipeline_for_award(
    award_code: str,
    registry_path: Path = SOURCE_REGISTRY_PATH,
) -> bool:
    """Return whether the pipeline runner can resolve a source for the selection."""
    try:
        source_record_for_award(award_code, registry_path=registry_path)
    except ValueError:
        return False
    return True
