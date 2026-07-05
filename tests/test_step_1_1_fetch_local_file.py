from pathlib import Path

from src.step_1_1_fetch.deterministic import fetch_main_content


def test_fetch_main_content_supports_local_path(tmp_path: Path):
    html_path = tmp_path / "award.html"
    html_path.write_text(
        "<html><body><div id='mainContent'><p>Local award</p></div></body></html>",
        encoding="utf-8",
    )

    main_content = fetch_main_content(str(html_path))

    assert main_content is not None
    assert "Local award" in main_content.get_text(" ", strip=True)


def test_fetch_main_content_supports_file_url(tmp_path: Path):
    html_path = tmp_path / "award.html"
    html_path.write_text(
        "<html><body><div id='mainContent'><p>File award</p></div></body></html>",
        encoding="utf-8",
    )

    main_content = fetch_main_content(f"file://{html_path}")

    assert main_content is not None
    assert "File award" in main_content.get_text(" ", strip=True)
