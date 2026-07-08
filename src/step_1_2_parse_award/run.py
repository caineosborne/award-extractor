"""Run step 1.2 award parse and output writing."""

from __future__ import annotations

from pathlib import Path

from .step_2_build_tree import extract_pdf_to_award
from .step_3_write_outputs import (
    write_html_outputs_for_paths,
    write_html_step_outputs,
    write_pdf_step_outputs,
)


def review_l1_clauses(
    *,
    url: str,
    main_content,
    award,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Stub for the L1 clause review flow."""
    write_html_step_outputs(
        url=url,
        main_content=main_content,
        award=award,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )


def review_l2_clauses(
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
    """Stub for the L2 clause review flow."""
    write_pdf_step_outputs(
        pdf_path=pdf_path,
        markdown_text=markdown_text,
        award=award,
        excluded_sections=excluded_sections,
        diagnostics=diagnostics,
        output_stem_value=output_stem_value,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )
