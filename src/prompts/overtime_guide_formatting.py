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
- Only include a template heading when the source supports at least one real rule for that heading.
- If a heading is not supported by the source, omit it entirely.
- Do not output placeholder bullets, fallback sentences, or explanatory text such as `No source-supported rule provided`.
- Ignore any validation-notes preamble in the source interpretation and format only the actual rules.
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
omit that heading entirely. Do not output placeholder bullets, fallback sentences,
or explanatory text saying that no rule was provided.
"""
    return [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
