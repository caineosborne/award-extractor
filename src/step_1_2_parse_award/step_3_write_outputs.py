"""Write step 1.2 outputs."""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.award_sources import register_local_pdf_source
from src.common.output_paths import FETCH_AWARD_SUPPORTING_DIR, write_text_output
from src.step_1_1_fetch.fetch_award import CONTENT_KEY, output_stem

def load_award_json(award_json_path: Path | str) -> OrderedDict[str, Any]:
    """Load one processed award JSON file while preserving key order."""
    path = Path(award_json_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def output_stem_for_award_json(award_json_path: Path | str) -> str:
    """Return the filename stem for supporting artifacts derived from one award JSON."""
    return Path(award_json_path).stem


def child_nodes(mapping: OrderedDict[str, Any]):
    """Yield child heading nodes while skipping the node's content bucket."""
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, dict):
            yield key, value


def iter_heading_rows(award: OrderedDict[str, Any]):
    """Yield one CSV row per visible heading combination."""
    for part_heading, part in award.items():
        for level1, level1_node in child_nodes(part):
            level2_rows = list(child_nodes(level1_node))
            if not level2_rows:
                yield {"PartHeading": part_heading, "L1": level1, "L2": "", "L3": ""}
                continue

            for level2, level2_node in level2_rows:
                level3_rows = list(child_nodes(level2_node))
                if not level3_rows:
                    yield {"PartHeading": part_heading, "L1": level1, "L2": level2, "L3": ""}
                    continue

                for level3, _level3_node in level3_rows:
                    yield {"PartHeading": part_heading, "L1": level1, "L2": level2, "L3": level3}


def section_index_key(key: str, parent_key: str | None) -> str:
    """Format lettered clause keys in the flat section index."""
    if parent_key and re.fullmatch(r"[A-Za-z]{1,3}", key):
        return f"{parent_key}{key}"
    return key


def build_section_index(award: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    """Build a flat lookup of clause reference to clause node."""
    index = OrderedDict()

    for _part_heading, part in award.items():
        for level1, level1_node in child_nodes(part):
            level1_index_key = section_index_key(level1, None)
            index[level1_index_key] = level1_node

            for level2, level2_node in child_nodes(level1_node):
                level2_index_key = section_index_key(level2, level1_index_key)
                index[level2_index_key] = level2_node

                for level3, level3_node in child_nodes(level2_node):
                    level3_index_key = section_index_key(level3, level2_index_key)
                    index[level3_index_key] = level3_node

                    for level4, level4_node in child_nodes(level3_node):
                        level4_index_key = section_index_key(level4, level3_index_key)
                        index[level4_index_key] = level4_node

                        for level5, level5_node in child_nodes(level4_node):
                            level5_index_key = section_index_key(level5, level4_index_key)
                            index[level5_index_key] = level5_node

    return index


def document_title_from_award(award: OrderedDict[str, Any]) -> str:
    """Return a readable display title from the parsed award tree."""
    if not award:
        return "Main Agreement"
    return str(next(iter(award.keys())))


def write_supporting_outputs(
    award_json_path: Path | str,
    output_dir: Path | str | None = None,
) -> tuple[Path, Path]:
    """Write the section index JSON and heading summary CSV for one award JSON."""
    award_path = Path(award_json_path)
    selected_output_dir = (
        Path(output_dir)
        if output_dir is not None
        else award_path.parent / FETCH_AWARD_SUPPORTING_DIR
    )
    selected_output_dir.mkdir(parents=True, exist_ok=True)

    award = load_award_json(award_path)
    section_index_path = selected_output_dir / f"{output_stem_for_award_json(award_path)}_sections.json"
    heading_csv_path = selected_output_dir / f"{output_stem_for_award_json(award_path)}.csv"

    write_text_output(
        section_index_path,
        json.dumps(build_section_index(award), indent=2, ensure_ascii=False),
    )

    with heading_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    print(f"Section index JSON saved to {section_index_path}")
    print(f"Heading CSV saved to {heading_csv_path}")
    return section_index_path, heading_csv_path


def write_html_outputs_for_paths(
    *,
    main_content,
    award,
    raw_html_path: Path,
    award_json_path: Path,
) -> None:
    """Write HTML-based step 1 outputs using explicit pipeline paths."""
    print(
        "Step 1.2: Writing parsed award outputs to "
        f"{award_json_path.parent}"
    )
    raw_html_path.parent.mkdir(parents=True, exist_ok=True)
    raw_html_path.write_text(str(main_content), encoding="utf-8")
    write_text_output(
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
    print(f"Step 1.2: Wrote raw HTML to {raw_html_path}")
    print(f"Step 1.2: Wrote parsed award JSON to {award_json_path}")


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
    write_html_outputs_for_paths(
        main_content=main_content,
        award=award,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
    )


def write_pdf_outputs(
    pdf_path: Path,
    markdown_text: str,
    award: OrderedDict[str, Any],
    excluded_sections: OrderedDict[str, Any],
    diagnostics: list[dict[str, Any]],
    output_stem_value: str,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write PDF outputs using the canonical active-pipeline filenames."""
    raw_markdown_path = raw_dir / "1_1_raw.md"
    award_json_path = processed_dir / output_stem_value / "1_2_award.json"
    supporting_dir = award_json_path.parent / FETCH_AWARD_SUPPORTING_DIR
    diagnostics_path = supporting_dir / "1_2_award_diagnostics.json"
    excluded_sections_path = supporting_dir / "1_2_award_excluded_sections.json"

    raw_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    raw_markdown_path.write_text(markdown_text, encoding="utf-8")

    write_text_output(
        award_json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
    )
    write_text_output(
        diagnostics_path,
        json.dumps(diagnostics, indent=2, ensure_ascii=False),
    )
    write_text_output(
        excluded_sections_path,
        json.dumps(
            {
                "source_pdf": str(pdf_path),
                "excluded_from_downstream": True,
                "sections": excluded_sections,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    write_supporting_outputs(
        award_json_path=award_json_path,
        output_dir=supporting_dir,
    )
    register_local_pdf_source(
        award_code=output_stem_value,
        pdf_path=pdf_path,
        display_name=document_title_from_award(award),
    )

    print(f"Raw markdown saved to {raw_markdown_path}")
    print(f"Processed JSON saved to {award_json_path}")
    print(f"Diagnostics JSON saved to {diagnostics_path}")
    print(f"Excluded sections JSON saved to {excluded_sections_path}")


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
