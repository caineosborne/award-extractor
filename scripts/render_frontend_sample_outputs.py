"""Create static, readable sample-output pages from the selected Aged Care Markdown files."""

from html import escape
from pathlib import Path
import re
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FOLDER = PROJECT_ROOT / "data" / "processed" / "MA000018"
OUTPUT_FOLDER = PROJECT_ROOT / "frontend" / "sample-outputs" / "aged-care"


def render_inline_markdown(text: str) -> str:
    escaped_text = escape(text)
    escaped_text = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped_text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped_text)


def render_markdown(markdown_text: str) -> str:
    html_lines: list[str] = []
    list_is_open = False
    code_block_is_open = False

    for line in markdown_text.splitlines():
        if line.lstrip().startswith("```"):
            if list_is_open:
                html_lines.append("</ul>")
                list_is_open = False

            if code_block_is_open:
                html_lines.append("</code></pre>")
                code_block_is_open = False
            else:
                html_lines.append('<pre><code class="pseudocode">')
                code_block_is_open = True
            continue

        if code_block_is_open:
            html_lines.append(escape(line))
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        list_match = re.match(r"^(\s*)-\s+(.+)$", line)

        if heading_match:
            if list_is_open:
                html_lines.append("</ul>")
                list_is_open = False

            level = len(heading_match.group(1))
            content = render_inline_markdown(heading_match.group(2))
            html_lines.append(f"<h{level}>{content}</h{level}>")
            continue

        if list_match:
            if not list_is_open:
                html_lines.append("<ul>")
                list_is_open = True

            indent = len(list_match.group(1)) // 2
            content = render_inline_markdown(list_match.group(2))
            html_lines.append(f'<li class="indent-{indent}">{content}</li>')
            continue

        if not line.strip():
            if list_is_open:
                html_lines.append("</ul>")
                list_is_open = False
            continue

        if list_is_open:
            html_lines.append("</ul>")
            list_is_open = False

        html_lines.append(f"<p>{render_inline_markdown(line)}</p>")

    if list_is_open:
        html_lines.append("</ul>")

    if code_block_is_open:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


def build_page(title: str, description: str, source_filename: str, markdown_html: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"description\" content=\"{escape(description)}\">
  <title>{escape(title)} | Award Extractor sample output</title>
  <style>
    :root {{ --ink: #16323b; --ink-soft: #385761; --teal: #107f7b; --line: #cbdadb; --wash: #f3f8f7; --warning: #d9811d; }}
    * {{ box-sizing: border-box; }}
    body {{ background: var(--wash); color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; margin: 0; }}
    .shell {{ margin: 0 auto; max-width: 1100px; padding: 34px 24px 70px; }}
    .back {{ color: var(--teal); font-size: 13px; font-weight: 700; text-decoration: none; }}
    .back:hover {{ text-decoration: underline; }}
    header {{ border-bottom: 4px solid var(--warning); margin-top: 23px; padding: 28px 0 24px; }}
    .eyebrow {{ color: var(--teal); font-size: 11px; font-weight: 800; letter-spacing: .12em; margin: 0 0 11px; text-transform: uppercase; }}
    h1, h2, h3 {{ font-family: Georgia, \"Times New Roman\", serif; }}
    h1 {{ font-size: clamp(2.25rem, 5vw, 4rem); font-weight: 400; letter-spacing: -.04em; line-height: 1.04; margin: 0; }}
    .status {{ background: #fff4dd; border-left: 4px solid var(--warning); color: var(--ink-soft); font-size: 14px; line-height: 1.5; margin-top: 22px; padding: 14px 16px; }}
    .status strong {{ color: var(--ink); }}
    .file-meta {{ color: var(--ink-soft); font-size: 13px; line-height: 1.55; margin: 20px 0 0; }}
    .file-meta code {{ background: #e6f1ef; color: #116d69; font-size: .92em; padding: 2px 5px; }}
    .file-meta a {{ color: var(--teal); font-weight: 700; }}
    article {{ background: #fff; border: 1px solid var(--line); margin-top: 28px; padding: clamp(25px, 5vw, 60px); }}
    article > h1 {{ font-size: clamp(2rem, 4.2vw, 3.4rem); margin: 0 0 25px; }}
    article h2 {{ border-top: 1px solid var(--line); font-size: clamp(1.6rem, 3vw, 2.2rem); font-weight: 400; margin: 40px 0 17px; padding-top: 27px; }}
    article h3 {{ color: var(--ink-soft); font-size: 1.1rem; margin: 28px 0 12px; }}
    article p, article li {{ font-size: 16px; line-height: 1.65; }}
    article p {{ margin: 0 0 16px; }}
    article ul {{ margin: 0 0 20px; padding-left: 24px; }}
    article li {{ margin: 7px 0; }}
    article li.indent-1 {{ margin-left: 24px; }}
    article li.indent-2 {{ margin-left: 48px; }}
    article code {{ background: #edf3f3; border-radius: 3px; color: #116d69; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; padding: 2px 4px; }}
    article pre {{ background: #eef3f4; border-left: 4px solid var(--teal); color: var(--ink); margin: 16px 0 28px; overflow-x: auto; padding: 20px; }}
    article pre code {{ background: transparent; color: inherit; display: block; font-size: 14px; line-height: 1.55; padding: 0; white-space: pre; }}
    @media (max-width: 600px) {{ .shell {{ padding: 22px 16px 48px; }} article {{ padding: 22px; }} article p, article li {{ font-size: 15px; }} }}
  </style>
</head>
<body>
  <main class=\"shell\">
    <a class=\"back\" href=\"../../index.html#top\">← Back to Award Extractor</a>
    <header>
      <p class=\"eyebrow\">Award Extractor · sample output</p>
      <h1>{escape(title)}</h1>
      <div class=\"status\"><strong>Sample Award Extractor output for the Aged Care Award.</strong> Created before any user edit or review, this page shows what Award Extractor produces. In real-world use, a user would review and refine the draft before relying on it. It is not an approved interpretation.</div>
      <p class=\"file-meta\">Source file: <code>{escape(source_filename)}</code> · <a href=\"{escape(source_filename)}\">View raw Markdown</a></p>
    </header>
    <article>
{markdown_html}
    </article>
  </main>
</body>
</html>
"""


def create_sample_output(source_filename: str, page_filename: str, title: str, description: str) -> None:
    source_path = SOURCE_FOLDER / source_filename
    output_markdown_path = OUTPUT_FOLDER / source_filename
    output_page_path = OUTPUT_FOLDER / page_filename

    markdown_text = source_path.read_text(encoding="utf-8")
    markdown_html = render_markdown(markdown_text)
    page_html = build_page(title, description, source_filename, markdown_html)

    shutil.copyfile(source_path, output_markdown_path)
    output_page_path.write_text(page_html, encoding="utf-8")


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    create_sample_output(
        "4_1_OT_creation_formatted_ruleset.md",
        "overtime-creation-guide.html",
        "Aged Care Award: draft overtime creation guide",
        "Full Aged Care Award draft Interpretation Matrix output for overtime creation.",
    )
    create_sample_output(
        "5_1_OT_creation_pseudocode.md",
        "overtime-creation-pseudocode.html",
        "Aged Care Award: draft overtime creation pseudocode",
        "Full Aged Care Award draft pseudocode output for overtime creation.",
    )


if __name__ == "__main__":
    main()
