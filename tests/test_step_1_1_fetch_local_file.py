from pathlib import Path

from src.step_1_1_fetch.fetch_award import fetch_award_source


def test_fetch_award_source_supports_local_path(tmp_path: Path):
    html_path = tmp_path / "award.html"
    html_path.write_text(
        (
            "<html><body><div id='mainContent'>"
            "<p class='partheading'>Part 1 - Local award</p>"
            "<p class='level1'>1. Local clause</p>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )

    result = fetch_award_source(str(html_path))

    assert result.main_content is not None
    assert "Local award" in result.main_content.get_text(" ", strip=True)
    assert result.award


def test_fetch_award_source_supports_file_url(tmp_path: Path):
    html_path = tmp_path / "award.html"
    html_path.write_text(
        (
            "<html><body><div id='mainContent'>"
            "<p class='partheading'>Part 1 - File award</p>"
            "<p class='level1'>1. File clause</p>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )

    result = fetch_award_source(f"file://{html_path}")

    assert result.main_content is not None
    assert "File award" in result.main_content.get_text(" ", strip=True)
    assert result.award
