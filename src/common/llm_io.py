from typing import Any


def extract_response_text(response: Any) -> str:
    """Extract plain text from the OpenAI response object."""
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    text_parts: list[str] = []

    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue

        for content_item in content:
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text)

    return "\n".join(text_parts)
