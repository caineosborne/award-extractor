import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


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
SECTION_PATTERN = re.compile(
    r"^("
    r"(?:[A-Z]\.\d+(?:\.\d+)*)"
    r"|(?:[A-Z]?\d+(?:\.\d+)*[A-Z]?\.?)"
    r"|(?:\([A-Za-z]{1,3}\))"
    r")\s*(.*)$"
)


def parse_args() -> argparse.Namespace:
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
    parsed = urlparse(url)
    source = Path(parsed.path).stem or parsed.netloc or "award"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", source).strip("_") or "award"


def unique_key(mapping: OrderedDict, key: str) -> str:
    if key not in mapping:
        return key

    index = 2
    while f"{key} [{index}]" in mapping:
        index += 1
    return f"{key} [{index}]"


def node() -> OrderedDict:
    item = OrderedDict()
    item[CONTENT_KEY] = []
    return item


def target_class(classes: list[str]) -> tuple[str, str] | tuple[None, None]:
    for class_name in classes:
        normalized = class_name.replace(" ", "").lower()
        if normalized in TARGET_CLASSES:
            return class_name, TARGET_CLASSES[normalized]
    return None, None


def split_section_heading(text: str) -> tuple[str, str]:
    match = SECTION_PATTERN.match(text)
    if match is None:
        return text, ""
    section = match.group(1).strip().removesuffix(".")
    if section.startswith("(") and section.endswith(")"):
        section = section[1:-1].strip()
    return section, match.group(2).strip()


def add_content(current: dict, content) -> None:
    target = current.get("part")
    for level in LEVEL_KEYS:
        target = current.get(level) or target

    if target is None:
        return

    target[CONTENT_KEY].append(content)


def table_to_dict(table) -> OrderedDict:
    rows = []
    for tr in table.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True)
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
                cell.get_text(" ", strip=True)
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

    if has_usable_headers:
        table_data["rows"] = [
            OrderedDict(zip(headers, row, strict=False))
            for row in body_rows
        ]
    else:
        table_data["rows"] = body_rows

    return table_data


def extract_award(main_content) -> OrderedDict:
    award = OrderedDict()
    current = {"part": None, **{level: None for level in LEVEL_KEYS}}

    for element in main_content.find_all(True):
        if element.name == "table":
            add_content(current, table_to_dict(element))
            continue

        classes = element.get("class", [])
        class_name, kind = target_class(classes)
        if kind is None:
            continue

        text = element.get_text(" ", strip=True)
        if not text:
            continue

        if kind == "part":
            part_key = unique_key(award, text)
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

        if kind == "level1":
            level1_key, content = split_section_heading(text)
            level1_key = unique_key(current["part"], level1_key)
            current["part"][level1_key] = node()
            if content:
                current["part"][level1_key][CONTENT_KEY].append(content)
            current["level1"] = current["part"][level1_key]
            for level in LEVEL_KEYS[1:]:
                current[level] = None
            continue

        if current["level1"] is None:
            level1_key = unique_key(current["part"], "No Level 1")
            current["part"][level1_key] = node()
            current["level1"] = current["part"][level1_key]

        if kind == "level2":
            level2_key, content = split_section_heading(text)
            level2_key = unique_key(current["level1"], level2_key)
            current["level1"][level2_key] = node()
            if content:
                current["level1"][level2_key][CONTENT_KEY].append(content)
            current["level2"] = current["level1"][level2_key]
            for level in LEVEL_KEYS[2:]:
                current[level] = None
            continue

        if current["level2"] is None:
            level2_key = unique_key(current["level1"], "No Level 2")
            current["level1"][level2_key] = node()
            current["level2"] = current["level1"][level2_key]

        if kind == "level3":
            level3_key, content = split_section_heading(text)
            level3_key = unique_key(current["level2"], level3_key)
            current["level2"][level3_key] = node()
            if content:
                current["level2"][level3_key][CONTENT_KEY].append(content)
            current["level3"] = current["level2"][level3_key]
            for level in LEVEL_KEYS[3:]:
                current[level] = None
            continue

        if current["level3"] is None:
            level3_key = unique_key(current["level2"], "No Level 3")
            current["level2"][level3_key] = node()
            current["level3"] = current["level2"][level3_key]

        if kind == "level4":
            level4_key, content = split_section_heading(text)
            level4_key = unique_key(current["level3"], level4_key)
            current["level3"][level4_key] = node()
            if content:
                current["level3"][level4_key][CONTENT_KEY].append(content)
            current["level4"] = current["level3"][level4_key]
            current["level5"] = None
            continue

        if current["level4"] is None:
            level4_key = unique_key(current["level3"], "No Level 4")
            current["level3"][level4_key] = node()
            current["level4"] = current["level3"][level4_key]

        if kind == "level5":
            level5_key, content = split_section_heading(text)
            level5_key = unique_key(current["level4"], level5_key)
            current["level4"][level5_key] = node()
            if content:
                current["level4"][level5_key][CONTENT_KEY].append(content)
            current["level5"] = current["level4"][level5_key]
            continue

        add_content(current, text)

    return award


def iter_heading_rows(award: OrderedDict):
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
    if parent_key and re.fullmatch(r"[A-Za-z]{1,3}", key):
        return f"{parent_key}{key}"
    return key


def build_section_index(award: OrderedDict) -> OrderedDict:
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

    return index


def child_nodes(mapping: OrderedDict):
    for key, value in mapping.items():
        if key == CONTENT_KEY:
            continue
        if isinstance(value, dict):
            yield key, value


def write_outputs(url: str, main_content, award: OrderedDict, raw_dir: Path, processed_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    stem = output_stem(url)
    raw_path = raw_dir / f"{stem}.html"
    json_path = processed_dir / f"{stem}.json"
    section_index_path = processed_dir / f"{stem}_sections.json"
    csv_path = processed_dir / f"{stem}.csv"

    raw_path.write_text(str(main_content), encoding="utf-8")
    json_path.write_text(json.dumps(award, indent=2, ensure_ascii=False), encoding="utf-8")
    section_index_path.write_text(
        json.dumps(build_section_index(award), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    print(f"Raw HTML saved to {raw_path}")
    print(f"Processed JSON saved to {json_path}")
    print(f"Section index JSON saved to {section_index_path}")
    print(f"Heading CSV saved to {csv_path}")


def fetch(url: str) -> BeautifulSoup:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")


def main() -> None:
    args = parse_args()
    soup = fetch(args.url)
    main_content = soup.find(id="MainContent") or soup.find(
        id=lambda value: isinstance(value, str) and value.lower() == "maincontent"
    )

    if main_content is None:
        raise SystemExit("Could not find div with id='MainContent'.")

    award = extract_award(main_content)
    write_outputs(args.url, main_content, award, Path(args.raw_dir), Path(args.processed_dir))


if __name__ == "__main__":
    main()
