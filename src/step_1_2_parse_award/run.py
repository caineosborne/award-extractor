"""Run step 1.2 award parse and output writing."""

from __future__ import annotations

import json
from pathlib import Path

from src.common.output_paths import FETCH_AWARD_SUPPORTING_DIR, write_text_with_archive
from src.script_1_fetch_award import write_step_1_outputs
from src.script_1_pdf_to_award_json import extract_pdf_to_award, write_pdf_outputs
from src.script_1b_generate_fetch_supporting_artifacts import write_supporting_outputs


def write_html_step_outputs(
    *,
    url: str,
    main_content,
    award,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write the maintained HTML-based step 1 outputs."""
    write_step_1_outputs(
        url=url,
        main_content=main_content,
        award=award,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )


def write_html_outputs_for_paths(
    *,
    main_content,
    award,
    raw_html_path: Path,
    award_json_path: Path,
) -> None:
    """Write HTML-based step 1 outputs using explicit pipeline paths."""
    raw_html_path.parent.mkdir(parents=True, exist_ok=True)
    raw_html_path.write_text(str(main_content), encoding="utf-8")
    write_text_with_archive(
        award_json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
    )
    supporting_output_dir = award_json_path.parent / FETCH_AWARD_SUPPORTING_DIR
    write_supporting_outputs(
        award_json_path=award_json_path,
        output_dir=supporting_output_dir,
    )
    print(f"Raw HTML saved to {raw_html_path}")
    print(f"Processed JSON saved to {award_json_path}")


def extract_pdf_award_source(pdf_path: Path):
    """Extract the maintained PDF-based step 1 source artifacts."""
    return extract_pdf_to_award(pdf_path)


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
    write_pdf_outputs(
        pdf_path=pdf_path,
        markdown_text=markdown_text,
        award=award,
        excluded_sections=excluded_sections,
        diagnostics=diagnostics,
        output_stem_value=output_stem_value,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )
