from collections.abc import Mapping, Sequence
from typing import Any


def _extract_text_value(value: Any) -> str:
    """Extract text from common SDK and dict response shapes."""
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, Mapping):
        direct_text = value.get("text")
        if isinstance(direct_text, str):
            return direct_text.strip()

        if isinstance(direct_text, Mapping):
            nested_value = direct_text.get("value")
            if isinstance(nested_value, str):
                return nested_value.strip()

        direct_value = value.get("value")
        if isinstance(direct_value, str):
            return direct_value.strip()

        output_text = value.get("output_text")
        if isinstance(output_text, str):
            return output_text.strip()

    object_text = getattr(value, "text", None)
    if isinstance(object_text, str):
        return object_text.strip()

    object_text_value = getattr(object_text, "value", None)
    if isinstance(object_text_value, str):
        return object_text_value.strip()

    object_value = getattr(value, "value", None)
    if isinstance(object_value, str):
        return object_value.strip()

    return ""


def extract_response_text(response: Any) -> str:
    """Extract plain text from the OpenAI response object."""
    output = getattr(response, "output", None)
    if isinstance(output, list):
        text_parts: list[str] = []

        for item in output:
            if isinstance(item, Mapping):
                content = item.get("content")
            else:
                content = getattr(item, "content", None)

            if not isinstance(content, list):
                continue

            for content_item in content:
                extracted_text = _extract_text_value(content_item)
                if extracted_text:
                    text_parts.append(extracted_text)

        if text_parts:
            return "\n".join(text_parts).strip()

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if isinstance(output_text, Sequence) and not isinstance(output_text, (str, bytes)):
        text_parts: list[str] = []

        for item in output_text:
            extracted_text = _extract_text_value(item)
            if extracted_text:
                text_parts.append(extracted_text)

        if text_parts:
            return "\n".join(text_parts).strip()

    return ""
