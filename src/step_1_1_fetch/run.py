"""Run step 1.1 award fetch."""

from __future__ import annotations

from .deterministic import Step1FetchResult, fetch_main_content, parse_main_content


def fetch_award_source(url: str) -> Step1FetchResult:
    """Fetch one Fair Work award URL and parse its main content."""
    print(f"Step 1.1: Fetching award source from {url}")
    main_content = fetch_main_content(url)
    print("Step 1.1: Parsing fetched HTML into the step 1 source structure")
    award = parse_main_content(main_content)
    print("Step 1.1: Fetch complete")
    return Step1FetchResult(main_content=main_content, award=award)
