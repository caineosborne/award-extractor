import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.output_paths import (
    FETCH_AWARD_SUPPORTING_DIR,
    timestamped_archive_path,
    write_text_with_archive,
)


CONTENT_KEY = "_content"

def load_award_json(award_json_path: Path | str) -> OrderedDict[str, Any]:
    """Load one processed award JSON file while preserving key order."""
    path = Path(award_json_path)
    with path.open(encoding="utf-8") as award_file:
        return json.load(award_file, object_pairs_hook=OrderedDict)


def output_stem_for_award_json(award_json_path: Path | str) -> str:
    """Return the filename stem for supporting artifacts derived from one award JSON."""
    return Path(award_json_path).stem


def default_supporting_output_dir(award_json_path: Path | str) -> Path:
    """Return the default subfolder used for supporting fetch artifacts."""
    award_path = Path(award_json_path)
    return award_path.parent / FETCH_AWARD_SUPPORTING_DIR


def child_nodes(mapping: OrderedDict[str, Any]):
    """Yield child heading nodes while skipping the node's content bucket."""
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, dict):
            yield key, value


def iter_heading_rows(award: OrderedDict[str, Any]):
    """Yield one CSV row per visible heading combination.

    The CSV is for reviewer navigation rather than for downstream execution, so
    it stays flat and easy to scan.
    """
    for part_heading, part in award.items():
        for level1, level1_node in child_nodes(part):
            level2_rows = list(child_nodes(level1_node))
            if not level2_rows:
                yield {
                    "PartHeading": part_heading,
                    "L1": level1,
                    "L2": "",
                    "L3": "",
                }
                continue

            for level2, level2_node in level2_rows:
                level3_rows = list(child_nodes(level2_node))
                if not level3_rows:
                    yield {
                        "PartHeading": part_heading,
                        "L1": level1,
                        "L2": level2,
                        "L3": "",
                    }
                    continue

                for level3, _level3_node in level3_rows:
                    yield {
                        "PartHeading": part_heading,
                        "L1": level1,
                        "L2": level2,
                        "L3": level3,
                    }


def section_index_key(key: str, parent_key: str | None) -> str:
    """Format lettered clause keys in the flat section index."""
    if parent_key and re.fullmatch(r"[A-Za-z]{1,3}", key):
        return f"{parent_key}{key}"
    return key


def build_section_index(award: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    """Build a flat lookup of clause reference to clause node.

    This gives reviewers and ad hoc tools a direct clause-to-node map without
    changing the nested award JSON used by the active pipeline.
    """
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


def section_index_output_path(award_json_path: Path | str, output_dir: Path) -> Path:
    """Build the supporting section-index JSON output path."""
    stem = output_stem_for_award_json(award_json_path)
    return output_dir / f"{stem}_sections.json"


def heading_csv_output_path(award_json_path: Path | str, output_dir: Path) -> Path:
    """Build the supporting heading-summary CSV output path."""
    stem = output_stem_for_award_json(award_json_path)
    return output_dir / f"{stem}.csv"


def write_supporting_outputs(
    award_json_path: Path | str,
    output_dir: Path | str | None = None,
) -> tuple[Path, Path]:
    """Write the section index JSON and heading summary CSV for one award JSON."""
    award_path = Path(award_json_path)
    selected_output_dir = (
        Path(output_dir)
        if output_dir is not None
        else default_supporting_output_dir(award_path)
    )
    selected_output_dir.mkdir(parents=True, exist_ok=True)

    award = load_award_json(award_path)
    section_index_path = section_index_output_path(award_path, selected_output_dir)
    heading_csv_path = heading_csv_output_path(award_path, selected_output_dir)

    write_text_with_archive(
        section_index_path,
        json.dumps(build_section_index(award), indent=2, ensure_ascii=False),
    )

    with heading_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    archive_csv_path = timestamped_archive_path(heading_csv_path)
    archive_csv_path.parent.mkdir(parents=True, exist_ok=True)
    archive_csv_path.write_text(heading_csv_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Section index JSON saved to {section_index_path}")
    print(f"Heading CSV saved to {heading_csv_path}")
    return section_index_path, heading_csv_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for generating supporting step-1 review artifacts."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate section index JSON and heading CSV from a fetched award JSON file."
        )
    )
    parser.add_argument(
        "award_json_path",
        help="Path to the processed award JSON, for example data/processed/1_fetch_award/MA000018.json",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Optional output directory. Defaults to "
            "data/processed/1_fetch_award/supporting beside the award JSON."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    write_supporting_outputs(
        award_json_path=args.award_json_path,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
