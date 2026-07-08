"""Parse markdown input for step 1.2."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class MarkdownEvent:
    """One extracted markdown event from one page."""

    kind: str
    page_number: int
    text: str = ""
    table_markdown: str = ""


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
