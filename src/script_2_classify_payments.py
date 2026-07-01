"""Compatibility wrapper for step 2.1 payment classification."""

from __future__ import annotations

from src.step_2_1_classify_payments.deterministic import (
    Step2ClassificationInputs,
    apply_deterministic_tag_repairs,
    build_result_artifact,
    build_top_level_groups,
    child_clause_nodes,
    clause_content_lines,
    clause_title,
    collect_descendants,
    deterministic_overtime_rule_names,
    direct_l2_reference_for,
    format_child_reference,
    format_content_item,
    flatten_clause,
    has_substantive_l1_content,
    is_lettered_key,
    is_placeholder_key,
    iter_top_level_groups,
    l1_body_text,
    load_award,
    map_relative_reference_to_direct_l2,
    map_to_direct_l2_reference,
    output_path_for_award,
    resolve_classification_inputs,
    timestamped_output_path,
    title_only_top_level_result,
    unique_items,
    write_result,
)
from src.step_2_1_classify_payments.llm import (
    classify_group,
    classify_groups,
    load_environment,
    load_openai_client,
    parse_response_json,
    response_json_schema,
    selected_model,
    validate_group_classification,
)
from src.step_2_1_classify_payments.run import classify_payments
from src.step_2_1_classify_payments.schema import (
    CONTENT_KEY,
    DEFAULT_AWARD_PATH,
    DEFAULT_MODEL,
    EXPLICIT_OVERTIME_TRIGGER_RULES,
    PLACEHOLDER_PREFIX,
    PROJECT_ROOT,
    SCHEMA_VERSION,
    SUBSTANTIVE_L1_MINIMUM_CHARACTERS,
    ClauseItem,
    DeterministicTagAdjustment,
    DeterministicTagRule,
    PaymentClauseClassifierError,
    TopLevelGroup,
)


classify_award = classify_payments


if __name__ == "__main__":
    from src.step_2_1_classify_payments.run import main

    main()
