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
    "PartHeading": "part",
    "Level1": "level1",
    "Level1Bold": "level1",
    "Level2": "level2",
    "Level2Bold": "level2",
    "Level3": "level3",
    "Level3Bold": "level3",
    "Level4": "content",
    "Bullet1": "content",
    "Bullet2": "content",
    "Bullet 1": "content",
    "Bullet 2": "content",
}

CONTENT_KEY = "_content"
CLASS_KEY = "_classes"


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
    item[CLASS_KEY] = []
    return item


def target_class(classes: list[str]) -> tuple[str, str] | tuple[None, None]:
    for class_name in classes:
        normalized = class_name.replace(" ", "")
        if class_name in TARGET_CLASSES:
            return class_name, TARGET_CLASSES[class_name]
        if normalized in TARGET_CLASSES:
            return class_name, TARGET_CLASSES[normalized]
    return None, None


def add_content(current: dict, text: str, class_name: str) -> None:
    target = (
        current.get("level3")
        or current.get("level2")
        or current.get("level1")
        or current.get("part")
    )

    if target is None:
        return

    target[CONTENT_KEY].append(text)
    target[CLASS_KEY].append(class_name)


def extract_award(main_content) -> OrderedDict:
    award = OrderedDict()
    current = {"part": None, "level1": None, "level2": None, "level3": None}

    for element in main_content.find_all(True):
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
                "level1": None,
                "level2": None,
                "level3": None,
            }
            continue

        if current["part"] is None:
            part_key = unique_key(award, "No Part")
            award[part_key] = node()
            current["part"] = award[part_key]

        if kind == "level1":
            level1_key = unique_key(current["part"], text)
            current["part"][level1_key] = node()
            current["level1"] = current["part"][level1_key]
            current["level2"] = None
            current["level3"] = None
            continue

        if current["level1"] is None:
            level1_key = unique_key(current["part"], "No Level 1")
            current["part"][level1_key] = node()
            current["level1"] = current["part"][level1_key]

        if kind == "level2":
            level2_key = unique_key(current["level1"], text)
            current["level1"][level2_key] = node()
            current["level2"] = current["level1"][level2_key]
            current["level3"] = None
            continue

        if current["level2"] is None:
            level2_key = unique_key(current["level1"], "No Level 2")
            current["level1"][level2_key] = node()
            current["level2"] = current["level1"][level2_key]

        if kind == "level3":
            level3_key = unique_key(current["level2"], text)
            current["level2"][level3_key] = node()
            current["level3"] = current["level2"][level3_key]
            continue

        add_content(current, text, class_name)

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


def child_nodes(mapping: OrderedDict):
    for key, value in mapping.items():
        if key in {CONTENT_KEY, CLASS_KEY}:
            continue
        if isinstance(value, dict):
            yield key, value


def write_outputs(url: str, main_content, award: OrderedDict, raw_dir: Path, processed_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    stem = output_stem(url)
    raw_path = raw_dir / f"{stem}.html"
    json_path = processed_dir / f"{stem}.json"
    csv_path = processed_dir / f"{stem}.csv"

    raw_path.write_text(str(main_content), encoding="utf-8")
    json_path.write_text(json.dumps(award, indent=2, ensure_ascii=False), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    print(f"Raw HTML saved to {raw_path}")
    print(f"Processed JSON saved to {json_path}")
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
