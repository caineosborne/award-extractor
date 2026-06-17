import argparse
import csv
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.output_paths import FETCH_AWARD_DIR, timestamped_archive_path, write_text_with_archive


TARGET_CLASSES = {
    "partheading": "part",
    "level1": "level1",
    "level1bold": "level1",
    "level2": "level2",
    "level2bold": "level2",
    "level3": "level3",
    "level3bold": "level3",
    "level4": "level4",
    "level4bold": "level4",
    "level5": "level5",
    "level5bold": "level5",
    "bullet1": "content",
    "bullet2": "content",
    "block1": "content",
    "block2": "content",
    "block3": "content",
}

CONTENT_KEY = "_content"
LEVEL_KEYS = ("level1", "level2", "level3", "level4", "level5")
LEVEL_NUMBERS = {level: index + 1 for index, level in enumerate(LEVEL_KEYS)}

# Fair Work pages sometimes encode bullets as private-use/symbol characters.
# Normalizing them here keeps the JSON easier for humans and LLMs to read.
BULLET_TRANSLATION = str.maketrans(
    {
        "\uf0b7": "-",
        "\u2022": "-",
        "\u00b7": "-",
    }
)

# Headings usually start with a clause reference such as "14", "14.1",
# "A.1.2", or "(a)". The parser stores that reference as the JSON key and
# keeps the remaining heading text in the node's _content list.
SECTION_PATTERN = re.compile(
    r"^("
    r"(?:[A-Z]\.\d+(?:\.\d+)*)"
    r"|(?:[A-Z]?\d+(?:\.\d+)*[A-Z]?\.?)"
    r"|(?:\([A-Za-z]{1,3}\))"
    r")\s*(.*)$"
)


@dataclass(frozen=True)
class AwardElement:
    """One meaningful item extracted from the award HTML."""

    kind: str
    text: str = ""
    table: OrderedDict | None = None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for fetching and writing one award."""
    parser = argparse.ArgumentParser(
        description="Fetch a Fair Work award URL and extract its heading hierarchy."
    )
    parser.add_argument("url", help="Award URL to fetch, for example https://awards.fairwork.gov.au/MA000018.html")
    parser.add_argument("--raw-dir", default="data/raw", help="Directory for raw MainContent HTML")
    parser.add_argument(
        "--processed-dir",
        default="data/processed",
        help="Directory for processed JSON and CSV outputs",
    )
    return parser.parse_args()


def output_stem(url: str) -> str:
    """Build a stable output filename stem from the URL path."""
    parsed = urlparse(url)
    source = Path(parsed.path).stem or parsed.netloc or "award"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", source).strip("_") or "award"


def unique_key(mapping: OrderedDict, key: str) -> str:
    """Return key unless already used, then append a numeric suffix."""
    if key not in mapping:
        return key

    index = 2
    while f"{key} [{index}]" in mapping:
        index += 1
    return f"{key} [{index}]"


def node() -> OrderedDict:
    """Create one award tree node with a standard content bucket."""
    item = OrderedDict()
    item[CONTENT_KEY] = []
    return item


def target_class(classes: list[str]) -> tuple[str, str] | tuple[None, None]:
    """Map an HTML class list to a parser role such as part, level1, or content."""
    for class_name in classes:
        normalized = class_name.replace(" ", "").lower()
        if normalized in TARGET_CLASSES:
            return class_name, TARGET_CLASSES[normalized]
    return None, None


def normalize_text(text: str) -> str:
    """Clean extracted text before it is written to JSON."""
    text = text.translate(BULLET_TRANSLATION)
    text = "".join(" " if "\ue000" <= character <= "\uf8ff" else character for character in text)
    return re.sub(r"\s+", " ", text).strip()


def split_section_heading(text: str) -> tuple[str, str]:
    """Split a heading into its clause key and readable heading text."""
    match = SECTION_PATTERN.match(text)
    if match is None:
        return text, ""
    section = match.group(1).strip().removesuffix(".")
    if section.startswith("(") and section.endswith(")"):
        section = section[1:-1].strip()
    return section, match.group(2).strip()


def add_content(current: dict, content) -> None:
    """Append content to the deepest currently active node."""
    target = current.get("part")
    for level in LEVEL_KEYS:
        target = current.get(level) or target

    if target is None:
        return

    target[CONTENT_KEY].append(content)


def table_to_dict(table) -> OrderedDict:
    """Convert an HTML table into a JSON-friendly table object."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [
            normalize_text(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["th", "td"], recursive=False)
        ]
        if cells:
            rows.append(cells)

    headers = []
    body_rows = rows

    header_row = table.find("thead")
    if header_row is not None:
        first_header_row = header_row.find("tr")
        if first_header_row is not None:
            headers = [
                normalize_text(cell.get_text(" ", strip=True))
                for cell in first_header_row.find_all(["th", "td"], recursive=False)
            ]
            body_rows = rows[1:]
    elif table.find("th") and rows:
        headers = rows[0]
        body_rows = rows[1:]

    table_data = OrderedDict()
    table_data["type"] = "table"
    table_data["headers"] = headers

    has_usable_headers = (
        headers
        and all(headers)
        and len(set(headers)) == len(headers)
        and all(len(row) == len(headers) for row in body_rows)
    )

    # Headered tables become row dictionaries so later steps can address
    # columns by name. Irregular tables stay as raw row lists to avoid guessing.
    if has_usable_headers:
        table_data["rows"] = [
            OrderedDict(zip(headers, row, strict=False))
            for row in body_rows
        ]
    else:
        table_data["rows"] = body_rows

    return table_data


def extract_award_elements(main_content) -> list[AwardElement]:
    """Extract a flat list of meaningful paragraph and table elements.

    Fair Work award pages carry the useful structure in paragraph classes
    such as partheading, level1, block1, and bullet1. Tables are content.
    Other tags are ignored so the nesting step only deals with clean inputs.
    """
    elements: list[AwardElement] = []

    for element in main_content.find_all(["p", "table"]):
        if element.name == "table":
            elements.append(AwardElement(kind="table", table=table_to_dict(element)))
            continue

        # Paragraphs inside tables are already represented by table_to_dict().
        if element.find_parent("table") is not None:
            continue

        _class_name, kind = target_class(element.get("class", []))
        if kind is None:
            continue

        text = normalize_text(element.get_text(" ", strip=True))
        if text:
            elements.append(AwardElement(kind=kind, text=text))

    # print(elements)
    # elements = flat cleaned parser input
    return elements


def nest_award_elements(elements: list[AwardElement]) -> OrderedDict:
    """Turn flat award elements into the nested part/clause JSON tree."""
    award = OrderedDict()

    # current tracks the latest node at each heading level. Content and skipped
    # heading levels attach to the deepest real node currently known.
    current = {"part": None, **{level: None for level in LEVEL_KEYS}}

    for element in elements:
        if element.kind == "table":
            if element.table is not None:
                add_content(current, element.table)
            continue

        if element.kind == "part":
            # A part heading resets all clause-level context.
            part_key = unique_key(award, element.text)
            award[part_key] = node()
            current = {
                "part": award[part_key],
                **{level: None for level in LEVEL_KEYS},
            }
            continue

        if current["part"] is None:
            # Rare defensive fallback: content appeared before any part heading.
            part_key = unique_key(award, "No Part")
            award[part_key] = node()
            current["part"] = award[part_key]

        if element.kind in LEVEL_NUMBERS:
            level_number = LEVEL_NUMBERS[element.kind]
            parent = current["part"]

            # If the page jumps from level1 to level4, use the nearest existing
            # parent instead of creating confusing "No Level" placeholder nodes.
            for parent_level in LEVEL_KEYS[: level_number - 1]:
                parent = current[parent_level] or parent

            heading_key, content = split_section_heading(element.text)
            heading_key = unique_key(parent, heading_key)
            parent[heading_key] = node()
            if content:
                parent[heading_key][CONTENT_KEY].append(content)

            current[element.kind] = parent[heading_key]
            for child_level in LEVEL_KEYS[level_number:]:
                current[child_level] = None
            continue

        add_content(current, element.text)

    # print(award)
    # award = nested award structure, same shape as MA000018.json
    return award


def extract_award(main_content) -> OrderedDict:
    """Extract the award's part/clause hierarchy from the MainContent element."""
    return nest_award_elements(extract_award_elements(main_content))


def iter_heading_rows(award: OrderedDict):
    """Yield rows for the heading-summary CSV output."""
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


def build_section_index(award: OrderedDict) -> OrderedDict:
    """Build a flat lookup of clause reference to clause node."""
    index = OrderedDict()

    for part_heading, part in award.items():
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

    # non-nested lookup version, same shape as MA000018_sections.json
    return index


def child_nodes(mapping: OrderedDict):
    """Yield child heading nodes while skipping the node's content bucket."""
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, dict):
            yield key, value


def write_outputs(url: str, main_content, award: OrderedDict, raw_dir: Path, processed_dir: Path) -> None:
    """Write raw HTML, full JSON, section-index JSON, and heading CSV outputs."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetch_award_dir = processed_dir / FETCH_AWARD_DIR
    fetch_award_dir.mkdir(parents=True, exist_ok=True)

    stem = output_stem(url)
    raw_path = raw_dir / f"{stem}.html"
    json_path = fetch_award_dir / f"{stem}.json"
    section_index_path = fetch_award_dir / f"{stem}_sections.json"
    csv_path = fetch_award_dir / f"{stem}.csv"

    raw_path.write_text(str(main_content), encoding="utf-8")
    archive_timestamp = datetime.now()
    write_text_with_archive(
        json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
        archive_timestamp,
    )
    write_text_with_archive(
        section_index_path,
        json.dumps(build_section_index(award), indent=2, ensure_ascii=False),
        archive_timestamp,
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    archive_csv_path = timestamped_archive_path(csv_path, archive_timestamp)
    archive_csv_path.parent.mkdir(parents=True, exist_ok=True)
    archive_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Raw HTML saved to {raw_path}")
    print(f"Processed JSON saved to {json_path}")
    print(f"Section index JSON saved to {section_index_path}")
    print(f"Heading CSV saved to {csv_path}")


def fetch(url: str) -> BeautifulSoup:
    """Fetch a URL and parse the response HTML."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    soup = fetch(args.url)
    main_content = soup.find(id="mainContent")

    if main_content is None:
        raise SystemExit("Could not find element with id='mainContent'.")

    award = extract_award(main_content)

    write_outputs(args.url, main_content, award, Path(args.raw_dir), Path(args.processed_dir))


if __name__ == "__main__":
    main()
