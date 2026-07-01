"""Run step 1.1 award fetch."""

from __future__ import annotations

from .deterministic import Step1FetchResult, fetch_main_content, parse_main_content


def fetch_award_source(url: str) -> Step1FetchResult:
    """Fetch one Fair Work award URL and parse its main content."""
    main_content = fetch_main_content(url)
    award = parse_main_content(main_content)
    return Step1FetchResult(main_content=main_content, award=award)
