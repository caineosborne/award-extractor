import argparse
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.common.output_paths import (
    FETCH_AWARD_DIR,
    FETCH_AWARD_SUPPORTING_DIR,
    write_text_with_archive,
)
from src.script_1b_generate_fetch_supporting_artifacts import write_supporting_outputs


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
    """Append content to the deepest currently active heading node."""
    target = current.get("part")
    for level in LEVEL_KEYS:
        target = current.get(level) or target

    if target is None:
        return

    target[CONTENT_KEY].append(content)


def table_to_dict(table) -> OrderedDict:
    """Convert one HTML table into a JSON-friendly structure."""
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

        if element.find_parent("table") is not None:
            continue

        _class_name, kind = target_class(element.get("class", []))
        if kind is None:
            continue

        text = normalize_text(element.get_text(" ", strip=True))
        if text:
            elements.append(AwardElement(kind=kind, text=text))

    return elements


def nest_award_elements(elements: list[AwardElement]) -> OrderedDict:
    """Turn flat award elements into the nested part/clause JSON tree.

    The parser keeps track of the most recent heading at each level so content
    attaches to the nearest real clause rather than to artificial placeholders.
    """
    award = OrderedDict()
    current = {"part": None, **{level: None for level in LEVEL_KEYS}}

    for element in elements:
        if element.kind == "table":
            if element.table is not None:
                add_content(current, element.table)
            continue

        if element.kind == "part":
            part_key = unique_key(award, element.text)
            award[part_key] = node()
            current = {
                "part": award[part_key],
                **{level: None for level in LEVEL_KEYS},
            }
            continue

        if current["part"] is None:
            part_key = unique_key(award, "No Part")
            award[part_key] = node()
            current["part"] = award[part_key]

        if element.kind in LEVEL_NUMBERS:
            level_number = LEVEL_NUMBERS[element.kind]
            parent = current["part"]

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

    return award


def extract_award(main_content) -> OrderedDict:
    """Extract the award's part/clause hierarchy from the MainContent element."""
    return nest_award_elements(extract_award_elements(main_content))


def fetch(url: str) -> BeautifulSoup:
    """Fetch a Fair Work award URL and parse the response HTML."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")


def fetch_and_extract_award(url: str) -> tuple[object, OrderedDict]:
    """Fetch one award page and return the main content element and parsed award JSON."""
    soup = fetch(url)
    main_content = soup.find(id="mainContent")

    if main_content is None:
        raise SystemExit("Could not find element with id='mainContent'.")

    award = extract_award(main_content)
    return main_content, award


def raw_html_output_path(url: str, raw_dir: Path) -> Path:
    """Build the raw HTML output path for a fetched award."""
    return raw_dir / f"{output_stem(url)}.html"


def award_json_output_path(url: str, processed_dir: Path) -> Path:
    """Build the main processed award JSON output path."""
    fetch_award_dir = processed_dir / FETCH_AWARD_DIR
    return fetch_award_dir / f"{output_stem(url)}.json"


def write_primary_outputs(
    url: str,
    main_content,
    award: OrderedDict,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write the two step-1 artifacts used by the active pipeline.

    The active pipeline only needs the raw HTML snapshot and the nested award
    JSON. Supporting review files are written separately so this core path stays
    easy to inspect.
    """
    raw_path = raw_html_output_path(url, raw_dir)
    json_path = award_json_output_path(url, processed_dir)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(str(main_content), encoding="utf-8")

    write_text_with_archive(
        json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
    )

    print(f"Raw HTML saved to {raw_path}")
    print(f"Processed JSON saved to {json_path}")


def write_step_1_outputs(
    url: str,
    main_content,
    award: OrderedDict,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """Write all maintained step-1 artifacts in review-friendly order.

    This keeps the main fetch script as the single entrypoint for operators
    while delegating the supporting review outputs to script 1B.
    """
    write_primary_outputs(
        url=url,
        main_content=main_content,
        award=award,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    award_json_path = award_json_output_path(url, processed_dir)
    supporting_output_dir = award_json_path.parent / FETCH_AWARD_SUPPORTING_DIR
    write_supporting_outputs(
        award_json_path=award_json_path,
        output_dir=supporting_output_dir,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for fetching and writing one award."""
    parser = argparse.ArgumentParser(
        description="Fetch a Fair Work award URL and write the raw HTML and main award JSON."
    )
    parser.add_argument(
        "url",
        help="Award URL to fetch, for example https://awards.fairwork.gov.au/MA000018.html",
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help=(
            "Directory for raw MainContent HTML. Defaults to "
            "data/processed/1_fetch_award/raw."
        ),
    )
    parser.add_argument(
        "--processed-dir",
        default="data/processed",
        help="Directory for processed award JSON output.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    main_content, award = fetch_and_extract_award(args.url)

    processed_dir = Path(args.processed_dir)
    raw_dir = Path(args.raw_dir) if args.raw_dir else processed_dir / FETCH_AWARD_DIR / "raw"

    write_step_1_outputs(args.url, main_content, award, raw_dir, processed_dir)


if __name__ == "__main__":
    main()
