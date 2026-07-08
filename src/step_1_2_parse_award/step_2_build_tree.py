"""Build the step 1.2 award tree from parsed markdown events."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf4llm

from src.step_1_1_fetch.fetch_award import CONTENT_KEY, node, unique_key

from .step_1_parse_markdown import (
    MarkdownEvent,
    is_page_number_line,
    is_picture_placeholder,
    is_toc_like_line,
    markdown_text_from_page_chunks,
    normalize_clause_text,
    parse_table_markdown,
    split_markdown_events,
)


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


def add_content_to_current(
    current_nodes: dict[int, OrderedDict[str, Any]],
    part_node: OrderedDict[str, Any],
    content: Any,
) -> None:
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


def parse_markdown_events(
    events: list[MarkdownEvent],
    document_title: str,
) -> tuple[OrderedDict[str, Any], OrderedDict[str, Any], list[dict[str, Any]]]:
    """Parse markdown events into the main clause tree and excluded sections tree."""
    award = OrderedDict()
    excluded_sections = OrderedDict()
    diagnostics: list[dict[str, Any]] = []

    def line_looks_like_heading_title(raw_text: str) -> bool:
        """Return whether the raw markdown line looks like a heading title line."""
        stripped = raw_text.strip()
        return stripped.startswith("#")

    def is_standalone_part_heading(text: str) -> bool:
        """Return whether one line is a standalone part heading."""
        return bool(PART_HEADING_PATTERN.match(text))

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


def extract_pdf_to_award(
    pdf_path: Path,
) -> tuple[str, OrderedDict[str, Any], OrderedDict[str, Any], list[dict[str, Any]]]:
    """Extract markdown, main award JSON, excluded sections, and diagnostics from one PDF."""
    page_chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)

    if not isinstance(page_chunks, list):
        raise SystemExit("Expected pymupdf4llm.to_markdown(..., page_chunks=True) to return a list")

    combined_markdown = markdown_text_from_page_chunks(page_chunks)
    document_title = pdf_path.stem.replace("_", " ").replace("-", " ").strip() or DEFAULT_PART_HEADING

    for chunk in page_chunks:
        metadata = chunk.get("metadata", {})
        title = str(metadata.get("title", "")).strip()
        if title and len(title) >= 6 and not re.fullmatch(r"[A-Z]{2}\d{4,}", title):
            document_title = title
            break

    events = split_markdown_events(page_chunks)
    award, excluded_sections, diagnostics = parse_markdown_events(events, document_title)
    return combined_markdown, award, excluded_sections, diagnostics
