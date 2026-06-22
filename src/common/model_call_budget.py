import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any


DEFAULT_ASSUMED_MAX_OUTPUT_TOKENS = 4000
DEFAULT_LARGE_CALL_INPUT_TOKENS = 12000


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0

    return max(1, (len(text) + 3) // 4)


def estimate_input_tokens(payload: Any) -> int:
    if payload is None:
        return 0

    if isinstance(payload, str):
        return estimate_text_tokens(payload)

    if isinstance(payload, Mapping):
        return estimate_text_tokens(
            json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        total_tokens = 0
        for item in payload:
            total_tokens += estimate_input_tokens(item)
        return total_tokens

    return estimate_text_tokens(str(payload))


def log_model_call_budget(
    status_callback: Callable[[str], None] | None,
    *,
    call_label: str,
    model: str,
    payload: Any,
    max_output_tokens: int | None = None,
) -> int:
    estimated_input_tokens = estimate_input_tokens(payload)
    selected_max_output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else DEFAULT_ASSUMED_MAX_OUTPUT_TOKENS
    )
    total_estimated_budget = estimated_input_tokens + selected_max_output_tokens

    if status_callback:
        status_callback(
            f"Token budget for {call_label}: "
            f"model={model}; "
            f"estimated_input_tokens={estimated_input_tokens}; "
            f"max_output_tokens={selected_max_output_tokens}; "
            f"total_estimated_tokens={total_estimated_budget}"
        )

    return estimated_input_tokens


def is_large_model_call(
    payload: Any,
    threshold_tokens: int = DEFAULT_LARGE_CALL_INPUT_TOKENS,
) -> bool:
    return estimate_input_tokens(payload) >= threshold_tokens
