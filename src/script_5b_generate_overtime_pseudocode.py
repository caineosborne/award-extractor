"""Compatibility wrapper for step 5B core overtime pseudocode generation."""

from __future__ import annotations

from src.prompts.core_overtime_pseudocode import (
    PSEUDOCODE_FIELDS,
    build_messages,
    build_repair_messages,
    first_top_level_bullets,
    overtime_rule_bullets,
)
from src.step_5_1_generate_pseudocode.core import (
    CoreOvertimePseudocodeError,
    DEFAULT_MODEL,
    DEFAULT_OVERTIME_SUMMARY_PATH,
    MAX_VALIDATION_REPAIR_ATTEMPTS,
    RULESET_CHOICES,
)
from src.step_5_1_generate_pseudocode.deterministic import (
    default_overtime_interpretation_path,
    fallback_source_paths_for_path,
    load_overtime_interpretation,
    load_overtime_rules,
    output_path_for_summary,
    resolve_generation_inputs,
    select_overtime_interpretation_path,
)
from src.step_5_1_generate_pseudocode.llm import (
    load_openai_client,
    request_initial_pseudocode,
    request_repaired_pseudocode,
    selected_model,
)
from src.step_5_1_generate_pseudocode.run import (
    generate_core_overtime_pseudocode,
    main,
    parse_args,
)


if __name__ == "__main__":
    main()
