"""Prompt content for step 4A overtime guide formatting.

Used by:
- `src/script_4a_summarize_overtime.py`
"""

from pathlib import Path


FORMATTER_SYSTEM_PROMPT = """You convert an overtime interpretation working document into a polished
human-readable overtime guide.

Requirements:
- Use only the supplied interpretation document for award-specific facts.
- Follow the supplied template heading structure and heading order.
- Keep the output concise and easy to scan.
- Use short markdown bullet points under each heading.
- Preserve employee groups, thresholds, assumptions, and clause references from the source.
- Do not invent rules, clause references, or categories that are not supported by the source.
- If the source does not support a section in the template, leave a single bullet with `-`.
- Return markdown only.
- Do not wrap the answer in a markdown code fence.
"""


def build_messages(
    interpretation_path: Path | str,
    interpretation_markdown: str,
    template_path: Path | str,
    template_markdown: str,
) -> list[dict[str, str]]:
    user_prompt = f"""Format the supplied overtime interpretation into the supplied template.

Interpretation source: {interpretation_path}

```markdown
{interpretation_markdown}
```

Template source: {template_path}

```markdown
{template_markdown}
```

Use the template headings exactly as provided. Replace placeholder bullets with source-based content.
Do not add headings outside the template. If a template section is not supported by the source,
leave a single bullet with `-`.
"""
    return [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
