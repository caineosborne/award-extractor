"""Run step 1.2 award parse and output writing."""

from __future__ import annotations

from pathlib import Path

from .deterministic import (
    extract_pdf_award_source as _extract_pdf_award_source,
    output_stem,
    write_html_outputs_for_paths as _write_html_outputs_for_paths,
    write_pdf_outputs as _write_pdf_outputs,
)


def write_html_step_outputs(
    *,
    url: str,
    main_content,
    award,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write the maintained HTML-based step 1 outputs."""
    output_stem_value = output_stem(url)
    raw_html_path = raw_dir / f"{output_stem_value}.html"
    award_json_path = processed_dir / output_stem_value / f"{output_stem_value}.json"
    _write_html_outputs_for_paths(
        main_content=main_content,
        award=award,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
    )


def write_html_outputs_for_paths(
    *,
    main_content,
    award,
    raw_html_path: Path,
    award_json_path: Path,
) -> None:
    """Write HTML-based step 1 outputs using explicit pipeline paths."""
    _write_html_outputs_for_paths(
        main_content=main_content,
        award=award,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
    )


def extract_pdf_award_source(pdf_path: Path):
    """Extract the maintained PDF-based step 1 source artifacts."""
    return _extract_pdf_award_source(pdf_path)


def write_pdf_step_outputs(
    *,
    pdf_path: Path,
    markdown_text: str,
    award,
    excluded_sections,
    diagnostics,
    output_stem_value: str,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write the maintained PDF-based step 1 outputs."""
    _write_pdf_outputs(
        pdf_path=pdf_path,
        markdown_text=markdown_text,
        award=award,
        excluded_sections=excluded_sections,
        diagnostics=diagnostics,
        output_stem_value=output_stem_value,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )
