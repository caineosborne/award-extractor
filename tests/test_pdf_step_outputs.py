"""Tests for canonical filenames produced by PDF Step 1."""

from collections import OrderedDict
from pathlib import Path

from src.step_1_2_parse_award.step_3_write_outputs import write_pdf_outputs


def test_pdf_step_outputs_use_canonical_active_pipeline_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.step_1_2_parse_award.step_3_write_outputs.register_local_pdf_source",
        lambda **kwargs: None,
    )
    raw_dir = tmp_path / "ColesEA" / "raw"
    processed_dir = tmp_path
    pdf_path = tmp_path / "ColesRetailEnterpriseAgreement2024.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    write_pdf_outputs(
        pdf_path=pdf_path,
        markdown_text="# Agreement",
        award=OrderedDict({"Part 1": {"_content": ["Clause 1"]}}),
        excluded_sections=OrderedDict(),
        diagnostics=[],
        output_stem_value="ColesEA",
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    output_dir = processed_dir / "ColesEA"
    assert (raw_dir / "1_1_raw.md").exists()
    assert (output_dir / "1_2_award.json").exists()
    assert (output_dir / "supporting" / "1_2_award_sections.json").exists()
    assert not (output_dir / "ColesEA.json").exists()
