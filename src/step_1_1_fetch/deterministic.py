"""Deterministic helpers for step 1.1 award fetch."""

from __future__ import annotations

from dataclasses import dataclass

from src.script_1_fetch_award import extract_award, fetch


@dataclass(frozen=True)
class Step1FetchResult:
    """Fetched HTML main content plus parsed award tree."""

    main_content: object
    award: object


def fetch_main_content(url: str) -> object:
    """Fetch the award HTML and return the main content element."""
    soup = fetch(url)
    main_content = soup.find(id="mainContent")
    if main_content is None:
        raise SystemExit("Could not find element with id='mainContent'.")
    return main_content


def parse_main_content(main_content: object) -> object:
    """Parse the main content HTML into the nested award tree."""
    return extract_award(main_content)
