import argparse
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf4llm

from src.common.output_paths import (
    FETCH_AWARD_SUPPORTING_DIR,
    write_text_with_archive,
)
from src.common.award_sources import register_local_pdf_source
from src.script_1_fetch_award import CONTENT_KEY, unique_key
from src.script_1b_generate_fetch_supporting_artifacts import write_supporting_outputs


DEFAULT_PART_HEADING = "Main Agreement"
ROMAN_MARKERS = {
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
}
NUMERIC_REFERENCE_PATTERN = re.compile(
    r"^(?P<reference>[A-Z]?\d+[A-Z]?(?:\.\d+[A-Z]?)*|[A-Z]\.\d+(?:\.\d+)*)\.?\s+(?P<title>.+)$"
)
LETTER_REFERENCE_PATTERN = re.compile(
    r"^\(?(?P<reference>[a-z]{1,4})\)?[.:]?\s+(?P<title>.+)$"
)
REFERENCE_ONLY_PATTERN = re.compile(
    r"^(?P<reference>[A-Z]?\d+[A-Z]?(?:\.\d+[A-Z]?)*|[A-Z]\.\d+(?:\.\d+)*|\(?[a-z]{1,4}\)?)\.?$"
)
EXCLUDED_SECTION_PATTERN = re.compile(r"^(APPENDIX|SCHEDULE|SIGNATORIES)\b", re.IGNORECASE)
PART_HEADING_PATTERN = re.compile(r"^PART\s+[A-Z0-9]+(?:\s*[-–—]\s*|\s+).+$", re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownEvent:
    """One extracted markdown event from one page."""

    kind: str
    page_number: int
    text: str = ""
    table_markdown: str = ""


@dataclass(frozen=True)
class ClauseHeading:
    """One recognized clause-like heading from the markdown stream."""

    reference: str
    title: str
    level: int
    marker_kind: str


@dataclass(frozen=True)
class PendingHeading:
    """A heading reference that was emitted without its title on the same line."""

    reference: str
    level: int
    marker_kind: str
    page_number: int
    source_text: str


def node() -> OrderedDict[str, Any]:
    """Create one standard clause node."""
    item: OrderedDict[str, Any] = OrderedDict()
    item[CONTENT_KEY] = []
    return item


def normalize_pdf_stem(pdf_path: Path, explicit_output_stem: str | None) -> str:
    """Build the shared output stem for one PDF run."""
    if explicit_output_stem:
        selected_stem = explicit_output_stem
    else:
        selected_stem = pdf_path.stem

    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", selected_stem).strip("._-")
    if not normalized:
        raise SystemExit("output stem must contain at least one letter or digit")
    return normalized


def readable_title_from_stem(stem: str) -> str:
    """Turn one filename stem into a reviewer-readable document title."""
    text = stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip() or DEFAULT_PART_HEADING


def title_is_usable(title: str) -> bool:
    """Return whether PDF metadata title looks readable enough to use."""
    if not title:
        return False
    if len(title) < 6:
        return False
    if re.fullmatch(r"[A-Z]{2}\d{4,}", title):
        return False
    return True


def markdown_output_path(output_stem_value: str, raw_dir: Path) -> Path:
    """Return the raw markdown output path for one PDF."""
    return raw_dir / f"{output_stem_value}.md"


def award_json_output_path(output_stem_value: str, processed_dir: Path) -> Path:
    """Return the main processed JSON path for one PDF."""
    award_dir = processed_dir / output_stem_value
    return award_dir / f"{output_stem_value}.json"


def diagnostics_output_path(output_stem_value: str, output_dir: Path) -> Path:
    """Return the heading diagnostics output path."""
    return output_dir / f"{output_stem_value}_diagnostics.json"


def excluded_sections_output_path(output_stem_value: str, output_dir: Path) -> Path:
    """Return the excluded sections output path."""
    return output_dir / f"{output_stem_value}_excluded_sections.json"


def strip_markdown_formatting(text: str) -> str:
    """Remove lightweight markdown markers while keeping readable text."""
    cleaned = text.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("###", "")
    cleaned = cleaned.replace("##", "")
    cleaned = cleaned.replace("#", "")
    cleaned = cleaned.replace("\\", "")
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def is_picture_placeholder(text: str) -> bool:
    """Return whether one line is a markdown placeholder for an omitted picture."""
    return "picture [" in text and "intentionally omitted" in text


def is_page_number_line(text: str) -> bool:
    """Return whether one line only carries the page number."""
    cleaned = strip_markdown_formatting(text)
    return bool(re.fullmatch(r"\d+", cleaned))


def is_table_line(text: str) -> bool:
    """Return whether one markdown line looks like a table row."""
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def is_table_separator_row(text: str) -> bool:
    """Return whether one markdown table row is the alignment separator."""
    cells = [cell.strip() for cell in text.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def is_toc_like_line(text: str) -> bool:
    """Return whether one line looks like table-of-contents material."""
    cleaned = strip_markdown_formatting(text)
    if not cleaned:
        return False

    if cleaned.lower() in {"contents", "table of contents"}:
        return True

    if re.search(r"\.{5,}", cleaned):
        return True

    if "|" in text:
        cells = [strip_markdown_formatting(cell) for cell in text.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[-1].isdigit():
            return True

    return False


def normalize_clause_text(text: str) -> str:
    """Normalize one text line before clause parsing and output."""
    cleaned = strip_markdown_formatting(text)
    cleaned = cleaned.lstrip("- ").strip()
    return re.sub(r"\s+", " ", cleaned).strip()


def split_markdown_events(page_chunks: list[dict[str, Any]]) -> list[MarkdownEvent]:
    """Split page markdown into text and table events while keeping page numbers."""
    events: list[MarkdownEvent] = []

    for chunk in page_chunks:
        metadata = chunk.get("metadata", {})
        page_number = int(metadata.get("page_number", 0) or 0)
        page_text = chunk.get("text", "")
        table_lines: list[str] = []

        for raw_line in page_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if table_lines:
                    events.append(
                        MarkdownEvent(
                            kind="table",
                            page_number=page_number,
                            table_markdown="\n".join(table_lines),
                        )
                    )
                    table_lines = []
                continue

            if is_table_line(line):
                table_lines.append(line)
                continue

            if table_lines:
                events.append(
                    MarkdownEvent(
                        kind="table",
                        page_number=page_number,
                        table_markdown="\n".join(table_lines),
                    )
                )
                table_lines = []

            events.append(
                MarkdownEvent(
                    kind="text",
                    page_number=page_number,
                    text=line.strip(),
                )
            )

        if table_lines:
            events.append(
                MarkdownEvent(
                    kind="table",
                    page_number=page_number,
                    table_markdown="\n".join(table_lines),
                )
            )

    return events


def body_start_page_number(events: list[MarkdownEvent]) -> int:
    """Return the first page that appears to contain the agreement body."""
    pages: OrderedDict[int, list[str]] = OrderedDict()

    for event in events:
        if event.kind != "text":
            continue
        pages.setdefault(event.page_number, []).append(event.text)

    for page_number, lines in pages.items():
        found_heading = False
        found_prose = False

        for line in lines:
            if is_picture_placeholder(line) or is_page_number_line(line):
                continue
            if is_toc_like_line(line):
                continue

            cleaned = normalize_clause_text(line)
            if parse_clause_heading(cleaned, current_numeric_depth=None, current_alpha_depth=None):
                found_heading = True
                continue

            if len(cleaned) >= 40:
                found_prose = True

        if found_heading and found_prose:
            return page_number

    return 1


def parse_table_markdown(table_markdown: str) -> OrderedDict[str, Any]:
    """Convert one markdown table into the table structure already used by step 1."""
    rows: list[list[str]] = []

    for line in table_markdown.splitlines():
        if is_table_separator_row(line):
            continue

        cells = [strip_markdown_formatting(cell) for cell in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append(cells)

    table_data: OrderedDict[str, Any] = OrderedDict()
    table_data["type"] = "table"

    if not rows:
        table_data["headers"] = []
        table_data["rows"] = []
        return table_data

    headers = rows[0]
    body_rows = rows[1:]
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


def parse_clause_heading(
    text: str,
    current_numeric_depth: int | None,
    current_alpha_depth: int | None,
) -> ClauseHeading | None:
    """Parse one text line into a clause heading when it clearly looks like one."""
    numeric_match = NUMERIC_REFERENCE_PATTERN.match(text)
    if numeric_match is not None:
        reference = numeric_match.group("reference").strip().removesuffix(".")
        title = numeric_match.group("title").strip()
        level = reference.count(".") + 1
        return ClauseHeading(
            reference=reference,
            title=title,
            level=level,
            marker_kind="numeric",
        )

    letter_match = LETTER_REFERENCE_PATTERN.match(text)
    if letter_match is None:
        return None

    reference = letter_match.group("reference").strip().lower()
    title = letter_match.group("title").strip()
    base_depth = current_numeric_depth or 1

    if reference in ROMAN_MARKERS:
        level = (current_alpha_depth or base_depth) + 1
        marker_kind = "roman"
    else:
        level = base_depth + 1
        marker_kind = "alpha"

    return ClauseHeading(
        reference=reference,
        title=title,
        level=level,
        marker_kind=marker_kind,
    )


def parse_reference_only_heading(
    text: str,
    current_numeric_depth: int | None,
    current_alpha_depth: int | None,
) -> tuple[str, int, str] | None:
    """Parse one reference-only heading line such as 4.4 or (a)."""
    match = REFERENCE_ONLY_PATTERN.match(text)
    if match is None:
        return None

    reference = match.group("reference").strip().removesuffix(".")
    if reference.startswith("(") and reference.endswith(")"):
        reference = reference[1:-1].strip()

    if re.fullmatch(r"[a-z]{1,4}", reference):
        base_depth = current_numeric_depth or 1
        if reference in ROMAN_MARKERS:
            level = (current_alpha_depth or base_depth) + 1
            return reference, level, "roman"
        level = base_depth + 1
        return reference, level, "alpha"

    level = reference.count(".") + 1
    return reference, level, "numeric"


def line_looks_like_heading_title(raw_text: str) -> bool:
    """Return whether the raw markdown line looks like a heading title line."""
    stripped = raw_text.strip()
    return stripped.startswith("#")


def is_standalone_part_heading(text: str) -> bool:
    """Return whether one line is a standalone part heading like PART 12 - UNION RECOGNITION."""
    return bool(PART_HEADING_PATTERN.match(text))


def add_content_to_current(current_nodes: dict[int, OrderedDict[str, Any]], part_node: OrderedDict[str, Any], content: Any) -> None:
    """Append content to the deepest active clause, or the part node when no clause exists."""
    target = part_node

    for depth in sorted(current_nodes):
        target = current_nodes[depth]

    target[CONTENT_KEY].append(content)


@dataclass
class TreeState:
    """Mutable state while building one nested clause tree."""

    tree: OrderedDict[str, OrderedDict[str, Any]]
    current_part_name: str | None = None
    current_part_node: OrderedDict[str, Any] | None = None
    current_nodes: dict[int, OrderedDict[str, Any]] | None = None
    current_numeric_depth: int | None = None
    current_alpha_depth: int | None = None

    def __post_init__(self) -> None:
        if self.current_nodes is None:
            self.current_nodes = {}

    def ensure_part(self, part_name: str) -> None:
        """Ensure one part node exists and make it the active insertion target."""
        if part_name == self.current_part_name and self.current_part_node is not None:
            return

        if part_name not in self.tree:
            self.tree[part_name] = node()

        self.current_part_name = part_name
        self.current_part_node = self.tree[part_name]
        self.current_nodes = {}
        self.current_numeric_depth = None
        self.current_alpha_depth = None

    def add_heading(self, heading: ClauseHeading) -> None:
        """Create one clause node and move the active pointer to it."""
        if self.current_part_node is None:
            self.ensure_part(DEFAULT_PART_HEADING)

        assert self.current_part_node is not None
        assert self.current_nodes is not None

        parent = self.current_part_node

        if heading.level > 1:
            for depth in range(heading.level - 1, 0, -1):
                if depth in self.current_nodes:
                    parent = self.current_nodes[depth]
                    break

        clause_key = unique_key(parent, heading.reference)
        parent[clause_key] = node()

        if heading.title:
            parent[clause_key][CONTENT_KEY].append(heading.title)

        self.current_nodes[heading.level] = parent[clause_key]

        for depth in list(self.current_nodes):
            if depth > heading.level:
                del self.current_nodes[depth]

        if heading.marker_kind == "numeric":
            self.current_numeric_depth = heading.level
            self.current_alpha_depth = None
        elif heading.marker_kind == "alpha":
            self.current_alpha_depth = heading.level

    def add_content(self, content: Any) -> None:
        """Append text or table content to the active clause tree."""
        if self.current_part_node is None:
            self.ensure_part(DEFAULT_PART_HEADING)

        assert self.current_part_node is not None
        assert self.current_nodes is not None
        add_content_to_current(self.current_nodes, self.current_part_node, content)


def parse_markdown_events(
    events: list[MarkdownEvent],
    document_title: str,
) -> tuple[OrderedDict[str, Any], OrderedDict[str, Any], list[dict[str, Any]]]:
    """Parse markdown events into the main clause tree and excluded sections tree."""
    award = OrderedDict()
    excluded_sections = OrderedDict()
    diagnostics: list[dict[str, Any]] = []

    main_state = TreeState(tree=award)
    excluded_state = TreeState(tree=excluded_sections)
    main_state.ensure_part(document_title or DEFAULT_PART_HEADING)

    active_state = main_state
    body_page_number = body_start_page_number(events)
    pending_heading: PendingHeading | None = None

    for event in events:
        if event.page_number < body_page_number:
            continue

        if event.kind == "table":
            if active_state is main_state or excluded_state.current_part_node is not None:
                active_state.add_content(parse_table_markdown(event.table_markdown))
            continue

        raw_text = event.text
        if not raw_text:
            continue
        if is_picture_placeholder(raw_text) or is_page_number_line(raw_text):
            continue
        if is_toc_like_line(raw_text):
            continue

        cleaned_text = normalize_clause_text(raw_text)
        if not cleaned_text:
            continue

        if line_looks_like_heading_title(raw_text) and is_standalone_part_heading(cleaned_text):
            pending_heading = None
            main_state.ensure_part(unique_key(award, cleaned_text))
            active_state = main_state
            diagnostics.append(
                {
                    "page_number": event.page_number,
                    "source_text": cleaned_text,
                    "detected_level": 0,
                    "marker_kind": "part",
                    "reference": "",
                    "title": cleaned_text,
                    "target": "main",
                }
            )
            continue

        if pending_heading is not None:
            attached_title = False
            if line_looks_like_heading_title(raw_text):
                heading = ClauseHeading(
                    reference=pending_heading.reference,
                    title=cleaned_text,
                    level=pending_heading.level,
                    marker_kind=pending_heading.marker_kind,
                )
                if heading.marker_kind == "numeric" and EXCLUDED_SECTION_PATTERN.match(heading.title):
                    excluded_part_name = f"{heading.reference} {heading.title}"
                    excluded_state.ensure_part(unique_key(excluded_sections, excluded_part_name))
                    active_state = excluded_state
                    diagnostics.append(
                        {
                            "page_number": pending_heading.page_number,
                            "source_text": pending_heading.source_text,
                            "detected_level": 0,
                            "marker_kind": "excluded_section",
                            "reference": heading.reference,
                            "title": heading.title,
                            "target": "excluded",
                        }
                    )
                else:
                    active_state.add_heading(heading)
                    diagnostics.append(
                        {
                            "page_number": pending_heading.page_number,
                            "source_text": pending_heading.source_text,
                            "detected_level": heading.level,
                            "marker_kind": heading.marker_kind,
                            "reference": heading.reference,
                            "title": heading.title,
                            "target": "main" if active_state is main_state else "excluded",
                        }
                    )
                pending_heading = None
                attached_title = True

            if not attached_title:
                heading = ClauseHeading(
                    reference=pending_heading.reference,
                    title="",
                    level=pending_heading.level,
                    marker_kind=pending_heading.marker_kind,
                )
                active_state.add_heading(heading)
                diagnostics.append(
                    {
                        "page_number": pending_heading.page_number,
                        "source_text": pending_heading.source_text,
                        "detected_level": heading.level,
                        "marker_kind": heading.marker_kind,
                        "reference": heading.reference,
                        "title": heading.title,
                        "target": "main" if active_state is main_state else "excluded",
                    }
                )
                pending_heading = None

        heading = parse_clause_heading(
            cleaned_text,
            current_numeric_depth=active_state.current_numeric_depth,
            current_alpha_depth=active_state.current_alpha_depth,
        )

        if heading is None:
            reference_only = parse_reference_only_heading(
                cleaned_text,
                current_numeric_depth=active_state.current_numeric_depth,
                current_alpha_depth=active_state.current_alpha_depth,
            )
            if reference_only is not None and line_looks_like_heading_title(raw_text):
                pending_heading = PendingHeading(
                    reference=reference_only[0],
                    level=reference_only[1],
                    marker_kind=reference_only[2],
                    page_number=event.page_number,
                    source_text=cleaned_text,
                )
                continue

            active_state.add_content(cleaned_text)
            continue

        if heading.marker_kind == "numeric" and EXCLUDED_SECTION_PATTERN.match(heading.title):
            excluded_part_name = f"{heading.reference} {heading.title}"
            excluded_state.ensure_part(unique_key(excluded_sections, excluded_part_name))
            active_state = excluded_state

            diagnostics.append(
                {
                    "page_number": event.page_number,
                    "source_text": cleaned_text,
                    "detected_level": 0,
                    "marker_kind": "excluded_section",
                    "reference": heading.reference,
                    "title": heading.title,
                    "target": "excluded",
                }
            )
            continue

        active_state.add_heading(heading)
        diagnostics.append(
            {
                "page_number": event.page_number,
                "source_text": cleaned_text,
                "detected_level": heading.level,
                "marker_kind": heading.marker_kind,
                "reference": heading.reference,
                "title": heading.title,
                "target": "main" if active_state is main_state else "excluded",
            }
        )

    if pending_heading is not None:
        heading = ClauseHeading(
            reference=pending_heading.reference,
            title="",
            level=pending_heading.level,
            marker_kind=pending_heading.marker_kind,
        )
        active_state.add_heading(heading)
        diagnostics.append(
            {
                "page_number": pending_heading.page_number,
                "source_text": pending_heading.source_text,
                "detected_level": heading.level,
                "marker_kind": heading.marker_kind,
                "reference": heading.reference,
                "title": heading.title,
                "target": "main" if active_state is main_state else "excluded",
            }
        )

    return award, excluded_sections, diagnostics


def markdown_text_from_page_chunks(page_chunks: list[dict[str, Any]]) -> str:
    """Build one combined markdown review file from page chunks."""
    sections: list[str] = []

    for chunk in page_chunks:
        metadata = chunk.get("metadata", {})
        page_number = int(metadata.get("page_number", 0) or 0)
        page_text = chunk.get("text", "").strip()
        if not page_text:
            continue

        sections.append(f"<!-- Page {page_number} -->\n\n{page_text}")

    return "\n\n".join(sections).strip()


def extract_pdf_to_award(
    pdf_path: Path,
) -> tuple[str, OrderedDict[str, Any], OrderedDict[str, Any], list[dict[str, Any]]]:
    """Extract markdown, main award JSON, excluded sections, and diagnostics from one PDF."""
    page_chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)

    if not isinstance(page_chunks, list):
        raise SystemExit("Expected pymupdf4llm.to_markdown(..., page_chunks=True) to return a list")

    combined_markdown = markdown_text_from_page_chunks(page_chunks)
    document_title = readable_title_from_stem(pdf_path.stem)

    for chunk in page_chunks:
        metadata = chunk.get("metadata", {})
        title = str(metadata.get("title", "")).strip()
        if title_is_usable(title):
            document_title = title
            break

    events = split_markdown_events(page_chunks)
    award, excluded_sections, diagnostics = parse_markdown_events(events, document_title)
    return combined_markdown, award, excluded_sections, diagnostics


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
    """Write the maintained output files for one PDF parse."""
    raw_markdown_path = markdown_output_path(output_stem_value, raw_dir)
    award_json_path = award_json_output_path(output_stem_value, processed_dir)
    supporting_dir = award_json_path.parent / FETCH_AWARD_SUPPORTING_DIR

    raw_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    raw_markdown_path.write_text(markdown_text, encoding="utf-8")

    write_text_with_archive(
        award_json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
    )
    write_text_with_archive(
        diagnostics_output_path(output_stem_value, supporting_dir),
        json.dumps(diagnostics, indent=2, ensure_ascii=False),
    )
    write_text_with_archive(
        excluded_sections_output_path(output_stem_value, supporting_dir),
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
    print(
        "Diagnostics JSON saved to "
        f"{diagnostics_output_path(output_stem_value, supporting_dir)}"
    )
    print(
        "Excluded sections JSON saved to "
        f"{excluded_sections_output_path(output_stem_value, supporting_dir)}"
    )


def document_title_from_award(award: OrderedDict[str, Any]) -> str:
    """Return a readable display title from the parsed award tree."""
    if not award:
        return DEFAULT_PART_HEADING
    return str(next(iter(award.keys())))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the PDF prototype."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract one local EBA PDF into the current step-1 nested award JSON shape."
        )
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the local PDF, for example resources/Documents/ColesRetailEnterpriseAgreement2024.pdf",
    )
    parser.add_argument(
        "--output-stem",
        default=None,
        help="Optional filename stem for all outputs. Defaults to the PDF filename stem.",
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help=(
            "Optional directory for the raw markdown review file. Defaults to "
            "data/processed/1_fetch_award/raw."
        ),
    )
    parser.add_argument(
        "--processed-dir",
        default="data/processed",
        help="Directory for processed outputs. Defaults to data/processed.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    processed_dir = Path(args.processed_dir)
    raw_dir = (
        Path(args.raw_dir)
        if args.raw_dir
        else processed_dir / output_stem_from_pdf_path(Path(args.pdf_path)) / "raw"
    )
    output_stem_value = normalize_pdf_stem(pdf_path, args.output_stem)

    markdown_text, award, excluded_sections, diagnostics = extract_pdf_to_award(pdf_path)
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


if __name__ == "__main__":
    main()
