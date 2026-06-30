import json
import re
import sys
import time
import traceback
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from html import escape
from io import StringIO
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.award_pipeline import (
    AwardPipelineError,
    build_paths,
    run_default_pipeline,
    run_selected_step,
)
from src.common.active_pipeline_paths import (
    normalize_award_code,
)
from src.common.award_sources import (
    SOURCE_TYPE_FAIR_WORK_HTML,
    SOURCE_TYPE_LOCAL_PDF,
    can_run_pipeline_for_award,
    source_record_for_award,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
)
from src.script_1_pdf_to_award_json import extract_pdf_to_award, write_pdf_outputs
from src.script_4a_summarize_overtime import summarize_overtime_entitlements
from streamlit_review.pipeline_runs import (
    log_path_for_award,
    normalized_status_for_award,
    start_background_pipeline_run,
    status_path_for_award,
)
from streamlit_review.output_data import (
    artifact_paths_for_award,
    clamp_index,
    delete_processed_files_matching_prefix,
    discover_award_codes,
    format_last_modified_for_display,
    format_path_for_display,
    l1_clause_keys,
    l1_record,
    l2_clause_keys,
    l2_record,
    load_json_file,
    next_index,
    overtime_classification_keys,
    overtime_classification_record,
    previous_index,
    processed_files_matching_prefix,
    read_text_file,
    ruleset_artifact_paths_for_award,
    source_path_for_core_overtime_pseudocode,
    source_path_for_ruleset_core_overtime_pseudocode,
    source_path_for_manual_4b_editor,
    write_text_file_with_archive,
)


SCREEN_L1_PAYMENT = "1. Payment clauses"
SCREEN_L2_PAYMENT = "2. Payment clause categories"
SCREEN_OVERTIME_CLASSIFICATION = "3. Ruleset clause classification"
SCREEN_EXPERT_A_OVERTIME = "4. Expert A ruleset draft"
SCREEN_EXPERT_B_OVERTIME = "5. Expert B ruleset draft"
SCREEN_EXPERT_COMPARISON = "6. Comparison of expert outputs"
SCREEN_ORIGINAL_OVERTIME = "7. Combined ruleset"
SCREEN_REVIEW_FEEDBACK = "8. Reviewer feedback and commentary"
SCREEN_FORMATTED_4A = "9. Final formatted ruleset"
SCREEN_MANUAL_4B_EDITOR = "10. Manually edited ruleset"
SCREEN_CORE_OVERTIME_PSEUDOCODE = "11. Pseudocode"

RULESET_OPTIONS = {
    "Overtime creation": OVERTIME_CREATION_RULESET,
    "Overtime consequence": OVERTIME_CONSEQUENCE_RULESET,
}

SCREEN_OPTIONS = [
    SCREEN_L1_PAYMENT,
    SCREEN_L2_PAYMENT,
    SCREEN_OVERTIME_CLASSIFICATION,
    SCREEN_EXPERT_A_OVERTIME,
    SCREEN_EXPERT_B_OVERTIME,
    SCREEN_EXPERT_COMPARISON,
    SCREEN_ORIGINAL_OVERTIME,
    SCREEN_REVIEW_FEEDBACK,
    SCREEN_FORMATTED_4A,
    SCREEN_MANUAL_4B_EDITOR,
    SCREEN_CORE_OVERTIME_PSEUDOCODE,
]

COMPARISON_PRESETS = {
    "Payment clauses vs payment clause categories": (
        SCREEN_L1_PAYMENT,
        SCREEN_L2_PAYMENT,
    ),
    "Ruleset clause classification vs final formatted ruleset": (
        SCREEN_OVERTIME_CLASSIFICATION,
        SCREEN_FORMATTED_4A,
    ),
    "Combined ruleset vs final formatted ruleset": (
        SCREEN_ORIGINAL_OVERTIME,
        SCREEN_FORMATTED_4A,
    ),
    "Expert A draft vs Expert B draft": (
        SCREEN_EXPERT_A_OVERTIME,
        SCREEN_EXPERT_B_OVERTIME,
    ),
    "Comparison of expert outputs vs combined ruleset": (
        SCREEN_EXPERT_COMPARISON,
        SCREEN_ORIGINAL_OVERTIME,
    ),
    "Reviewer feedback vs final formatted ruleset": (
        SCREEN_REVIEW_FEEDBACK,
        SCREEN_FORMATTED_4A,
    ),
}

PIPELINE_STEP_LABELS = {
    "1": "Retrieve award",
    "2": "Classify clauses",
    "3": "Generate overtime",
    "3b": "Review overtime",
    "4": "Format overtime guide",
    "5b": "Generate pseudocode",
}


def main() -> None:
    st.set_page_config(
        page_title="Award Output Review",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Award Output Review")

    award_codes = discover_award_codes()

    apply_review_styles()

    selected_award_code = render_sidebar(award_codes)
    validated_award_code, validation_error = validate_award_code_input(
        selected_award_code,
        existing_output_sets=award_codes,
    )

    if validation_error is not None:
        st.error(validation_error)
        return

    artifact_paths = artifact_paths_for_award(validated_award_code)
    selected_ruleset = st.session_state.get("step3_ruleset", OVERTIME_CREATION_RULESET)

    st.caption(f"Reviewing generated outputs for `{validated_award_code}`.")

    screen_one = st.session_state["screen_one"]
    screen_two = st.session_state["screen_two"]
    layout_mode = st.session_state["layout_mode"]

    render_screens(
        screen_one=screen_one,
        screen_two=screen_two,
        layout_mode=layout_mode,
        artifact_paths=artifact_paths,
        ruleset_key=selected_ruleset,
    )


def render_sidebar(award_codes: list[str]) -> str:
    with st.sidebar:
        st.header("Review controls")
        ensure_layout_state()

        default_award_code = st.session_state.get(
            "award_code",
            award_codes[0] if award_codes else "",
        )
        if "award_code" not in st.session_state:
            st.session_state["award_code"] = default_award_code

        st.text_input(
            "Award code",
            key="award_code",
            placeholder="MA000002",
        )

        if award_codes:
            available_award_code = st.selectbox(
                "Load existing output set",
                award_codes,
                index=available_award_code_index(award_codes, st.session_state["award_code"]),
                key="available_award_code",
                on_change=copy_available_award_code_to_input,
            )
            st.caption(f"Selected saved output set: `{available_award_code}`")
        else:
            st.caption("No existing processed outputs were found. Enter an award code to run the pipeline.")

        selected_award_code = st.session_state["award_code"].strip()
        validated_award_code, validation_error = validate_award_code_input(
            selected_award_code,
            existing_output_sets=award_codes,
        )
        if validation_error is not None:
            st.warning(validation_error)

        pipeline_controls_disabled = (
            validation_error is not None
            or validated_award_code is None
            or not can_run_pipeline_for_award(validated_award_code)
        )
        if validated_award_code and not looks_like_modern_award_code(validated_award_code):
            st.caption(
                "Viewing a saved local PDF output set. Pipeline buttons will use the registered PDF source."
            )

        st.divider()
        selected_label = st.selectbox(
            "Step 3 ruleset",
            list(RULESET_OPTIONS),
            key="step3_ruleset_label",
        )
        st.session_state["step3_ruleset"] = RULESET_OPTIONS[selected_label]

        st.divider()
        render_pipeline_run_controls(
            selected_award_code=validated_award_code or selected_award_code,
            controls_disabled=pipeline_controls_disabled,
            ruleset_key=st.session_state["step3_ruleset"],
        )

        st.divider()
        st.caption("Quick comparisons")

        for preset_label, screens in COMPARISON_PRESETS.items():
            if st.button(preset_label, use_container_width=True):
                st.session_state["screen_one"] = screens[0]
                st.session_state["screen_two"] = screens[1]
                st.session_state["layout_mode"] = "Side by side"
                sync_layout_widgets_from_state()

        st.caption("Single screen shortcuts")

        if st.button("Combined ruleset", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_ORIGINAL_OVERTIME
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("Final formatted ruleset", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_FORMATTED_4A
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("Manually edited ruleset", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_MANUAL_4B_EDITOR
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("Pseudocode", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_CORE_OVERTIME_PSEUDOCODE
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        st.divider()

        st.selectbox(
            "First screen",
            SCREEN_OPTIONS,
            key="screen_one_widget",
            on_change=update_screen_one_from_widget,
        )
        st.selectbox(
            "Second screen",
            ["None"] + SCREEN_OPTIONS,
            key="screen_two_widget",
            on_change=update_screen_two_from_widget,
        )
        st.radio(
            "Layout",
            ["Side by side", "Single expanded"],
            horizontal=False,
            key="layout_mode_widget",
            on_change=update_layout_mode_from_widget,
        )

        st.divider()
        render_processed_file_cleanup_controls()

    return selected_award_code


def available_award_code_index(award_codes: list[str], selected_award_code: str) -> int:
    normalized_award_code = selected_award_code.strip()

    if normalized_award_code in award_codes:
        return award_codes.index(normalized_award_code)

    upper_lookup = {award_code.upper(): index for index, award_code in enumerate(award_codes)}
    if normalized_award_code.upper() in upper_lookup:
        return upper_lookup[normalized_award_code.upper()]

    return 0


def copy_available_award_code_to_input() -> None:
    st.session_state["award_code"] = st.session_state["available_award_code"]


def ensure_layout_state() -> None:
    """Initialize persistent and widget-backed layout state once per session."""
    if "screen_one" not in st.session_state:
        st.session_state["screen_one"] = SCREEN_L2_PAYMENT
    if "screen_two" not in st.session_state:
        st.session_state["screen_two"] = SCREEN_ORIGINAL_OVERTIME
    if "layout_mode" not in st.session_state:
        st.session_state["layout_mode"] = "Side by side"

    sync_layout_widgets_from_state()


def sync_layout_widgets_from_state() -> None:
    """Keep sidebar widget values aligned with the persistent layout state."""
    st.session_state["screen_one_widget"] = st.session_state["screen_one"]
    st.session_state["screen_two_widget"] = st.session_state["screen_two"]
    st.session_state["layout_mode_widget"] = st.session_state["layout_mode"]


def update_screen_one_from_widget() -> None:
    """Persist the first screen selection from the sidebar widget."""
    st.session_state["screen_one"] = st.session_state["screen_one_widget"]
    st.session_state["screen_one_widget"] = st.session_state["screen_one"]


def update_screen_two_from_widget() -> None:
    """Persist the second screen selection from the sidebar widget."""
    st.session_state["screen_two"] = st.session_state["screen_two_widget"]
    st.session_state["screen_two_widget"] = st.session_state["screen_two"]


def update_layout_mode_from_widget() -> None:
    """Persist the layout mode selection from the sidebar widget."""
    st.session_state["layout_mode"] = st.session_state["layout_mode_widget"]
    st.session_state["layout_mode_widget"] = st.session_state["layout_mode"]


def validate_award_code_input(
    value: str,
    existing_output_sets: list[str] | None = None,
) -> tuple[str | None, str | None]:
    available_output_sets = existing_output_sets or []
    selected_award_code = value.strip()
    if not selected_award_code:
        return None, "Enter an award code to review or run."

    if selected_award_code in available_output_sets:
        return selected_award_code, None

    try:
        normalized_award_code = normalize_award_code(selected_award_code.upper())
    except ValueError:
        return None, "Select an existing output set or enter an award code like `MA000002`."

    return normalized_award_code, None


def looks_like_modern_award_code(value: str) -> bool:
    """Return whether the selected value is a runnable MA-style award code."""
    try:
        normalize_award_code(value.upper())
    except ValueError:
        return False
    return True


def render_screens(
    screen_one: str,
    screen_two: str,
    layout_mode: str,
    artifact_paths: Any,
    ruleset_key: str,
) -> None:
    if layout_mode == "Single expanded" or screen_two == "None":
        with st.container(height=790, border=True):
            render_screen_panel(
                screen_one,
                artifact_paths,
                panel_key="screen_one",
                ruleset_key=ruleset_key,
            )
        return

    left_column, right_column = st.columns(2, gap="medium")

    with left_column:
        with st.container(height=790, border=True):
            render_screen_panel(
                screen_one,
                artifact_paths,
                panel_key="screen_one",
                ruleset_key=ruleset_key,
            )

    with right_column:
        with st.container(height=790, border=True):
            render_screen_panel(
                screen_two,
                artifact_paths,
                panel_key="screen_two",
                ruleset_key=ruleset_key,
            )


def render_screen_panel(
    screen_name: str,
    artifact_paths: Any,
    panel_key: str,
    ruleset_key: str,
) -> None:
    render_panel_heading(
        screen_name,
        panel_key,
        artifact_paths,
    )

    render_screen(screen_name, artifact_paths, panel_key, ruleset_key)


def render_screen(
    screen_name: str,
    artifact_paths: Any,
    panel_key: str,
    ruleset_key: str,
) -> None:
    renderers: dict[str, Callable[[Any, str], None]] = {
        SCREEN_L1_PAYMENT: render_l1_payment_screen,
        SCREEN_L2_PAYMENT: render_l2_payment_screen,
        SCREEN_OVERTIME_CLASSIFICATION: render_overtime_classification_screen,
        SCREEN_ORIGINAL_OVERTIME: render_original_overtime_screen,
        SCREEN_EXPERT_A_OVERTIME: render_expert_a_overtime_screen,
        SCREEN_EXPERT_B_OVERTIME: render_expert_b_overtime_screen,
        SCREEN_EXPERT_COMPARISON: render_expert_comparison_screen,
        SCREEN_REVIEW_FEEDBACK: render_review_feedback_screen,
        SCREEN_FORMATTED_4A: render_formatted_4a_screen,
        SCREEN_MANUAL_4B_EDITOR: render_manual_4b_editor_screen,
        SCREEN_CORE_OVERTIME_PSEUDOCODE: render_core_overtime_pseudocode_screen,
    }

    renderer = renderers[screen_name]
    renderer(artifact_paths, panel_key, ruleset_key)


def render_l1_payment_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del ruleset_key
    render_file_details(artifact_paths.payment_classification)

    payment_classification = load_json_or_show_error(artifact_paths.payment_classification)
    if payment_classification is None:
        return

    clause_keys = l1_clause_keys(payment_classification)
    selected_key = render_key_navigation(
        label="L1 clause",
        keys=clause_keys,
        state_key=f"{panel_key}_l1_index",
    )
    if selected_key is None:
        st.info("No L1 clauses were found.")
        return

    record = l1_record(payment_classification, selected_key)

    st.markdown(f"#### Clause {selected_key}: {record.get('title', '')}")
    st.markdown(
        " | ".join(
            [
                f"**Payment relevant:** {bool_label(record.get('payment_relevant'))}",
                f"**Definition relevant:** {bool_label(record.get('definition_relevant'))}",
                f"**Requires L2:** {bool_label(record.get('requires_l2_classification'))}",
            ]
        )
    )

    st.markdown("**Reason**")
    st.write(record.get("reason", ""))
    render_json_expander("Selected L1 JSON", record, key_suffix=panel_key)


def render_l2_payment_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del ruleset_key
    render_file_details(artifact_paths.payment_classification)

    payment_classification = load_json_or_show_error(artifact_paths.payment_classification)
    if payment_classification is None:
        return

    clause_keys = l2_clause_keys(payment_classification)
    selected_key = render_key_navigation(
        label="L2 clause",
        keys=clause_keys,
        state_key=f"{panel_key}_l2_index",
    )
    if selected_key is None:
        st.info("No L2 classified clauses were found.")
        return

    record = l2_record(payment_classification, selected_key)

    st.markdown(f"#### Clause {selected_key}")
    st.markdown("**Tags**")
    st.write(", ".join(record.get("tags", [])))
    st.markdown("**Reason**")
    st.write(record.get("reason", ""))
    render_json_expander("Selected L2 JSON", record, key_suffix=panel_key)


def render_overtime_classification_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        artifact_paths.payment_classification.stem.removesuffix("_payment_classification"),
        ruleset_key,
    )
    render_file_details(ruleset_artifacts.clause_classification)

    overtime_classification = load_json_or_show_error(
        ruleset_artifacts.clause_classification
    )
    if overtime_classification is None:
        return

    clause_keys = overtime_classification_keys(overtime_classification)
    selected_key = render_key_navigation(
        label="Classified clause",
        keys=clause_keys,
        state_key=f"{panel_key}_overtime_classification_index",
    )
    if selected_key is None:
        st.info("No overtime clause classifications were found.")
        return

    record = overtime_classification_record(overtime_classification, selected_key)
    classification_labels = record.get("classifications")
    if not isinstance(classification_labels, list):
        classification_labels = [record.get("classification", "")]

    st.markdown(f"#### Clause {record.get('clause_number', selected_key)}")
    st.markdown(f"**Classifications:** {', '.join(classification_labels)}")
    st.markdown(f"**Employee cohort:** {record.get('employee_cohort', 'all')}")
    st.markdown(f"**Work arrangement:** {record.get('work_arrangement', 'all')}")
    other_scope_notes = str(record.get("other_scope_notes", "")).strip()
    if other_scope_notes:
        st.markdown(f"**Other scope notes:** {other_scope_notes}")
    st.markdown("**Explanation**")
    st.write(record.get("explanation", ""))
    st.markdown("**Clause text**")
    st.text_area(
        "Clause text",
        value=record.get("clause_text", ""),
        height=320,
        label_visibility="collapsed",
        disabled=True,
        key=overtime_clause_text_widget_key(panel_key, selected_key),
    )
    render_json_expander(
        "Selected overtime classification JSON",
        record,
        key_suffix=panel_key,
    )


def overtime_clause_text_widget_key(panel_key: str, selected_clause_key: str) -> str:
    return f"{panel_key}_overtime_clause_text_{selected_clause_key}"


def render_original_overtime_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        artifact_paths.payment_classification.stem.removesuffix("_payment_classification"),
        ruleset_key,
    )
    json_path = ruleset_artifacts.combined_json
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.combined_markdown,
    )


def render_expert_a_overtime_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        artifact_paths.payment_classification.stem.removesuffix("_payment_classification"),
        ruleset_key,
    )
    json_path = ruleset_artifacts.expert_a_markdown.with_suffix(".json")
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.expert_a_markdown,
    )


def render_expert_b_overtime_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        artifact_paths.payment_classification.stem.removesuffix("_payment_classification"),
        ruleset_key,
    )
    json_path = ruleset_artifacts.expert_b_markdown.with_suffix(".json")
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.expert_b_markdown,
    )


def render_expert_comparison_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        artifact_paths.payment_classification.stem.removesuffix("_payment_classification"),
        ruleset_key,
    )
    render_file_details(ruleset_artifacts.comparison_json)

    comparison_data = load_json_or_show_error(
        ruleset_artifacts.comparison_json
    )
    if comparison_data is None:
        return

    summary_markdown = str(
        comparison_data.get("comparison_summary_markdown", "")
    ).strip()
    validation_warnings = comparison_data.get("validation_warnings", [])
    expert_outputs = comparison_data.get("expert_outputs", [])
    merge_explanations = comparison_data.get("merge_explanations", [])

    if summary_markdown:
        st.markdown("#### Comparison summary")
        st.markdown(summary_markdown)

    if isinstance(validation_warnings, list) and validation_warnings:
        with st.expander("Validation notes", expanded=True):
            for warning in validation_warnings:
                st.write(f"- {format_validation_warning_for_display(str(warning))}")

    if isinstance(expert_outputs, list) and expert_outputs:
        with st.expander("Expert run artifacts", expanded=False):
            for artifact in expert_outputs:
                if not isinstance(artifact, dict):
                    continue
                label = str(artifact.get("label", "expert"))
                json_path = str(artifact.get("json_path", ""))
                markdown_path = str(artifact.get("markdown_path", ""))
                st.write(
                    f"- `{label}`: JSON `{json_path}` | Markdown `{markdown_path}`"
                )

    if isinstance(merge_explanations, list) and merge_explanations:
        with st.expander("Merge decisions", expanded=False):
            for explanation in merge_explanations:
                if not isinstance(explanation, dict):
                    continue
                merged_rule_id = str(explanation.get("merged_rule_id", ""))
                run_a_rule_ids = ", ".join(explanation.get("run_a_rule_ids", []))
                run_b_rule_ids = ", ".join(explanation.get("run_b_rule_ids", []))
                reason = str(explanation.get("reason", "")).strip()
                st.markdown(f"##### {merged_rule_id}")
                if run_a_rule_ids:
                    st.write(f"**Run A rules:** {run_a_rule_ids}")
                if run_b_rule_ids:
                    st.write(f"**Run B rules:** {run_b_rule_ids}")
                if reason:
                    st.write(reason)
                st.divider()

    render_json_expander("Expert comparison JSON", comparison_data, key_suffix=panel_key)


def render_review_feedback_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        selected_award_code(),
        ruleset_key,
    )
    if artifact_paths.agentic_review_conversation.exists():
        with st.expander("Agentic review conversation", expanded=False):
            render_markdown_file(artifact_paths.agentic_review_conversation)

    evaluator_column, creator_column, outcome_column = st.columns(3, gap="medium")

    with evaluator_column:
        with st.container(border=True):
            st.markdown("#### Evaluator feedback")
            render_evaluator_feedback_panel(ruleset_artifacts.evaluator_feedback)

    with creator_column:
        with st.container(border=True):
            st.markdown("#### Creator commentary")
            render_creator_commentary_panel(ruleset_artifacts.creator_response)

    with outcome_column:
        with st.container(border=True):
            st.markdown("#### Final outcome")
            revised_json_path = ruleset_artifacts.revised_json
            if revised_json_path.exists():
                render_overtime_rules_json(
                    revised_json_path,
                    source_markdown_path=ruleset_artifacts.revised_markdown,
                )
            else:
                render_markdown_file(ruleset_artifacts.revised_markdown)


def render_evaluator_feedback_panel(markdown_path: Path) -> None:
    """Render evaluator feedback with markdown as the primary display source."""
    render_file_details(markdown_path)

    rendered_summary_markdown = False
    markdown_content = read_text_file(markdown_path)
    if markdown_content.exists:
        markdown_text = markdown_content.text.strip()
        if (
            markdown_text
            and not markdown_text.startswith("# Evaluator feedback validation failure")
            and not markdown_text.startswith("{")
        ):
            st.markdown(markdown_text)
            rendered_summary_markdown = True

    json_path = markdown_path.with_suffix(".json")
    json_data = load_json_or_show_error(json_path) if json_path.exists() else None
    if isinstance(json_data, dict):
        summary_markdown = str(json_data.get("summary_markdown", "")).strip()
        rule_reviews = json_data.get("rule_reviews", [])
        new_rules = json_data.get("new_rules", [])

        if summary_markdown.startswith("# Evaluator feedback validation failure"):
            main_markdown, raw_block = split_markdown_at_heading(
                summary_markdown,
                "## Raw evaluator response",
            )
            if main_markdown:
                st.markdown(main_markdown)
            if raw_block:
                with st.expander("Raw evaluator response", expanded=False):
                    st.markdown(
                        strip_leading_heading(raw_block, "## Raw evaluator response")
                    )
            return

        if summary_markdown.startswith("{"):
            st.warning(
                "The evaluator returned an incomplete structured response. "
                "The saved review is shown as a raw payload for manual checking."
            )
            with st.expander("Raw evaluator response", expanded=False):
                st.code(summary_markdown, language="json")
            return

        if summary_markdown and not rendered_summary_markdown:
            st.markdown(summary_markdown)

        if isinstance(rule_reviews, list) and rule_reviews:
            with st.expander("Rule-by-rule recommendations", expanded=False):
                for rule_review in rule_reviews:
                    if not isinstance(rule_review, dict):
                        continue
                    rule_id = str(rule_review.get("rule_id", "")).strip()
                    recommendation = str(
                        rule_review.get("recommendation", "")
                    ).strip()
                    rationale = str(rule_review.get("rationale", "")).strip()
                    heading = rule_id or "rule"
                    if recommendation:
                        heading = f"{heading} ({recommendation})"
                    st.markdown(f"##### {heading}")
                    if rationale:
                        st.write(rationale)
                    st.divider()

        if isinstance(new_rules, list) and new_rules:
            with st.expander("Suggested new rules", expanded=False):
                for new_rule in new_rules:
                    if not isinstance(new_rule, dict):
                        continue
                    rule_id = str(new_rule.get("rule_id", "")).strip()
                    st.markdown(f"##### {rule_id or 'new rule'}")
                    rule_markdown = str(new_rule.get("rule_markdown", "")).strip()
                    if rule_markdown:
                        st.markdown(rule_markdown)
                    st.divider()

        with st.expander("Structured evaluator feedback JSON", expanded=False):
            render_json_expander(
                "Evaluator feedback JSON",
                json_data,
                key_suffix=str(json_path),
            )
        return

    render_markdown_file(markdown_path)


def render_creator_commentary_panel(markdown_path: Path) -> None:
    """Render creator commentary with markdown as the primary display source."""
    render_file_details(markdown_path)

    rendered_markdown = False
    markdown_content = read_text_file(markdown_path)
    if markdown_content.exists:
        markdown_text = markdown_content.text.strip()
        if (
            markdown_text
            and not markdown_text.startswith("# Creator response validation failure")
            and not markdown_text.startswith("{")
        ):
            st.markdown(markdown_text)
            rendered_markdown = True

    json_path = markdown_path.with_suffix(".json")
    json_data = load_json_or_show_error(json_path) if json_path.exists() else None
    if isinstance(json_data, dict):
        decision_record_markdown = str(
            json_data.get("decision_record_markdown", "")
        ).strip()
        validation_error = str(json_data.get("validation_error", "")).strip()
        raw_creator_response = str(json_data.get("raw_creator_response", "")).strip()

        if validation_error:
            st.warning(
                "The creator response could not be applied automatically and requires manual review."
            )
            st.write(f"Validation issue: {validation_error}")

        if decision_record_markdown and not rendered_markdown:
            st.markdown(decision_record_markdown)

        if raw_creator_response:
            with st.expander("Raw creator response", expanded=False):
                st.code(raw_creator_response, language="json")

        with st.expander("Structured creator commentary JSON", expanded=False):
            render_json_expander(
                "Creator commentary JSON",
                json_data,
                key_suffix=str(json_path),
            )
        return

    render_markdown_file(markdown_path)


def split_markdown_at_heading(markdown_text: str, heading: str) -> tuple[str, str]:
    """Split a markdown document at the nominated heading."""
    heading_index = markdown_text.find(heading)
    if heading_index == -1:
        return markdown_text.strip(), ""

    main_markdown = markdown_text[:heading_index].strip()
    trailing_markdown = markdown_text[heading_index:].strip()
    return main_markdown, trailing_markdown


def strip_leading_heading(markdown_text: str, heading: str) -> str:
    """Remove a duplicated leading heading when content is shown inside an expander."""
    stripped_text = markdown_text.strip()
    if not stripped_text.startswith(heading):
        return stripped_text

    return stripped_text[len(heading) :].lstrip()


def render_formatted_4a_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        selected_award_code(),
        ruleset_key,
    )
    render_markdown_file(
        ruleset_artifacts.formatted_markdown,
        source_path=ruleset_artifacts.revised_markdown,
    )


def render_manual_4b_editor_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del ruleset_key
    source_path = source_path_for_manual_4b_editor(artifact_paths)
    source_content = read_text_file(source_path)

    render_file_details(
        artifact_paths.manual_4b_overtime_interpretation,
        source_path=source_path,
        file_label="Save target",
        source_label="Editor source",
    )

    if not source_content.exists:
        render_missing_file(source_path)
        return

    editor_key = manual_4b_editor_widget_key(
        panel_key,
        artifact_paths.manual_4b_overtime_interpretation,
    )
    edited_markdown = st.text_area(
        "4B overtime markdown",
        value=source_content.text,
        height=610,
        label_visibility="collapsed",
        key=editor_key,
    )

    if st.button("Save updated version", key=f"{editor_key}_save"):
        if not edited_markdown.strip():
            st.error("The edited overtime markdown is empty. Nothing was saved.")
            return

        archive_path = write_text_file_with_archive(
            artifact_paths.manual_4b_overtime_interpretation,
            edited_markdown,
        )
        st.success(
            "Saved updated version to "
            f"`{format_path_for_display(artifact_paths.manual_4b_overtime_interpretation)}`."
        )
        st.caption(f"Archive copy: `{format_path_for_display(archive_path)}`")


def render_core_overtime_pseudocode_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key, artifact_paths
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        selected_award_code(),
        ruleset_key,
    )
    render_markdown_file(
        ruleset_artifacts.pseudocode_markdown,
        source_path=source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifacts),
    )
    render_ruleset_validation_summary(ruleset_artifacts)


def manual_4b_editor_widget_key(panel_key: str, output_path: Path) -> str:
    return f"{panel_key}_manual_4b_editor_{output_path.stem}"


def render_key_navigation(
    label: str,
    keys: list[str],
    state_key: str,
) -> str | None:
    if not keys:
        return None

    selected_value_key = f"{state_key}_selected_value"
    widget_key = f"{state_key}_selector"
    stored_selected_value = st.session_state.get(selected_value_key)

    if stored_selected_value in keys:
        current_index = keys.index(stored_selected_value)
    else:
        current_index = clamp_index(st.session_state.get(state_key, 0), len(keys))

    st.session_state[state_key] = current_index
    if widget_key not in st.session_state or st.session_state.get(widget_key) not in keys:
        st.session_state[widget_key] = keys[current_index]

    previous_column, selector_column, next_column = st.columns([1, 3, 1])

    with previous_column:
        st.button(
            "Previous",
            key=f"{state_key}_previous",
            on_click=move_selected_index,
            args=(state_key, selected_value_key, widget_key, keys, -1),
            use_container_width=True,
        )

    with selector_column:
        selected_key = st.selectbox(
            f"{label} selector for {state_key}",
            keys,
            label_visibility="collapsed",
            key=widget_key,
        )
        st.session_state[state_key] = keys.index(selected_key)
        st.session_state[selected_value_key] = selected_key

    with next_column:
        st.button(
            "Next",
            key=f"{state_key}_next",
            on_click=move_selected_index,
            args=(state_key, selected_value_key, widget_key, keys, 1),
            use_container_width=True,
        )

    return keys[st.session_state[state_key]]


def move_selected_index(
    state_key: str,
    selected_value_key: str,
    widget_key: str,
    keys: list[str],
    direction: int,
) -> None:
    item_count = len(keys)
    if item_count == 0:
        return

    current_index = clamp_index(st.session_state.get(state_key, 0), item_count)

    if direction < 0:
        updated_index = previous_index(current_index, item_count)
    else:
        updated_index = next_index(current_index, item_count)

    st.session_state[state_key] = updated_index
    st.session_state[selected_value_key] = keys[updated_index]
    st.session_state[widget_key] = keys[updated_index]


def save_current_side_by_side_layout() -> None:
    """Remember the current two-panel layout so it can be restored later."""
    st.session_state["last_side_by_side_screen_one"] = st.session_state.get("screen_one")
    st.session_state["last_side_by_side_screen_two"] = st.session_state.get("screen_two")


def load_json_or_show_error(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        render_missing_file(path)
        return None

    return load_json_file(path)


def render_markdown_file(path: Path, source_path: Path | None = None) -> None:
    render_file_details(path, source_path=source_path)
    file_content = read_text_file(path)

    if not file_content.exists:
        render_missing_file(path)
        return

    st.markdown(file_content.text)


def strip_prepended_validation_block(rendered_markdown: str) -> str:
    """Remove the saved validation-notes header so the UI can render it separately."""
    validation_header = "# Validation notes"

    if not rendered_markdown.startswith(validation_header):
        return rendered_markdown

    heading_match = re.search(r"^##\s", rendered_markdown, flags=re.MULTILINE)
    if heading_match is None:
        return rendered_markdown

    return rendered_markdown[heading_match.start() :].lstrip()


def format_validation_warning_for_display(warning: str) -> str:
    """Normalize older warning text into the current reviewer-friendly wording."""
    direct_match = re.fullmatch(
        r"Shortlisted clause ([^ ]+) from step 3\.2 is not referenced by any step 3\.4 rule\.",
        warning,
    )
    if direct_match:
        clause_number = direct_match.group(1)
        return (
            f"Clause {clause_number} was shortlisted as potentially relevant to overtime, "
            "but no rule in this ruleset currently represents it."
        )

    merged_match = re.fullmatch(
        r"Shortlisted clause ([^ ]+) from step 3\.2 is not referenced by any merged expert-comparison rule\.",
        warning,
    )
    if merged_match:
        clause_number = merged_match.group(1)
        return (
            f"Clause {clause_number} was shortlisted as potentially relevant to overtime, "
            "and it is still not represented in the combined ruleset after expert comparison."
        )

    return warning


def render_overtime_rules_json(
    json_path: Path,
    *,
    source_markdown_path: Path | None = None,
) -> None:
    render_file_details(
        json_path,
        source_path=source_markdown_path,
        source_label="Derived markdown view",
    )

    rules_data = load_json_or_show_error(json_path)
    if rules_data is None:
        return

    validation_warnings = rules_data.get("validation_warnings", [])
    rendered_markdown = strip_prepended_validation_block(
        str(rules_data.get("rendered_markdown", "")).strip()
    )
    rules = rules_data.get("rules", [])

    if rendered_markdown:
        st.markdown("#### Markdown view")
        st.markdown(rendered_markdown)

    if isinstance(validation_warnings, list) and validation_warnings:
        with st.expander("Validation notes", expanded=True):
            for warning in validation_warnings:
                st.write(f"- {format_validation_warning_for_display(str(warning))}")

    if not isinstance(rules, list) or not rules:
        st.warning("No structured overtime rules were found in this JSON artifact.")
        render_json_expander(
            "Structured overtime rules JSON",
            rules_data,
            key_suffix=str(json_path),
        )
        return

    with st.expander("Rule-by-rule breakdown", expanded=False):
        for rule in rules:
            if not isinstance(rule, dict):
                continue

            rule_id = str(rule.get("rule_id", ""))
            section_heading = str(rule.get("section_heading", ""))
            clause_references = ", ".join(rule.get("clause_references", []))
            employee_scope = ", ".join(rule.get("employee_scope", []))
            employee_cohort = str(rule.get("employee_cohort", "")).strip()
            work_arrangement = str(rule.get("work_arrangement", "")).strip()
            other_scope_notes = str(rule.get("other_scope_notes", "")).strip()
            st.markdown(f"##### {rule_id}")
            if section_heading:
                st.caption(f"Section: {section_heading}")
            if employee_scope:
                st.write(f"**Employee scope:** {employee_scope}")
            if employee_cohort:
                st.write(f"**Employee cohort:** {employee_cohort}")
            if work_arrangement:
                st.write(f"**Work arrangement:** {work_arrangement}")
            if other_scope_notes:
                st.write(f"**Other scope notes:** {other_scope_notes}")
            if clause_references:
                st.write(f"**Clause references:** {clause_references}")
            st.markdown(rule.get("rule_markdown", ""))
            plain_text = str(rule.get("rule_plain_text", "")).strip()
            if plain_text:
                st.caption(plain_text)
            st.divider()

    render_json_expander(
        "Structured overtime rules JSON",
        rules_data,
        key_suffix=str(json_path),
    )


def render_missing_file(path: Path) -> None:
    st.warning(f"File not found: `{format_path_for_display(path)}`")


def render_file_details(
    path: Path,
    source_path: Path | None = None,
    file_label: str = "Displayed file",
    source_label: str = "Source file used",
) -> None:
    metadata_lines = [
        (
            escape(file_label),
            escape(format_path_for_display(path)),
        ),
        (
            "Last modified",
            escape(format_last_modified_for_display(path)),
        ),
    ]

    if source_path is not None and source_path != path:
        metadata_lines.append(
            (
                escape(source_label),
                escape(format_path_for_display(source_path)),
            )
        )
        metadata_lines.append(
            (
                "Source last modified",
                escape(format_last_modified_for_display(source_path)),
            )
        )

    metadata_html = "".join(
        (
            f'<div class="review-file-detail-row">'
            f"<strong>{label}:</strong> <code>{value}</code>"
            f"</div>"
        )
        for label, value in metadata_lines
    )

    st.markdown(
        f'<div class="review-file-details">{metadata_html}</div>',
        unsafe_allow_html=True,
    )


def render_panel_heading(
    heading: str,
    panel_key: str,
    artifact_paths: Any,
) -> None:
    st.markdown(f"### {heading}")

    previous_column, next_column, layout_column, button_column = st.columns(4)

    with previous_column:
        st.button(
            "Prev",
            key=f"{panel_key}_screen_previous",
            on_click=move_screen_selection,
            args=(panel_key, -1),
            use_container_width=True,
        )

    with next_column:
        st.button(
            "Next",
            key=f"{panel_key}_screen_next",
            on_click=move_screen_selection,
            args=(panel_key, 1),
            use_container_width=True,
        )

    with layout_column:
        if st.session_state.get("layout_mode") == "Side by side":
            st.button(
                "Full Screen",
                key=f"{panel_key}_screen_expand",
                on_click=expand_panel_to_single_view,
                args=(panel_key,),
                use_container_width=True,
            )
        else:
            st.button(
                "Split Screen",
                key=f"{panel_key}_screen_show_both",
                on_click=restore_side_by_side_view,
                use_container_width=True,
            )

    with button_column:
        if st.button("Refresh", key=f"{panel_key}_refresh", use_container_width=True):
            refresh_panel(panel_key, heading, artifact_paths)


def move_screen_selection(panel_key: str, direction: int) -> None:
    current_screen = st.session_state.get(panel_key, SCREEN_OPTIONS[0])
    current_index = SCREEN_OPTIONS.index(current_screen)

    if direction < 0:
        updated_index = previous_index(current_index, len(SCREEN_OPTIONS))
    else:
        updated_index = next_index(current_index, len(SCREEN_OPTIONS))

    st.session_state[panel_key] = SCREEN_OPTIONS[updated_index]
    sync_layout_widgets_from_state()


def expand_panel_to_single_view(panel_key: str) -> None:
    if st.session_state.get("layout_mode") == "Side by side":
        save_current_side_by_side_layout()

    st.session_state["screen_one"] = st.session_state[panel_key]
    st.session_state["screen_two"] = "None"
    st.session_state["layout_mode"] = "Single expanded"
    sync_layout_widgets_from_state()


def restore_side_by_side_view() -> None:
    saved_screen_one = st.session_state.get("last_side_by_side_screen_one")
    saved_screen_two = st.session_state.get("last_side_by_side_screen_two")

    if saved_screen_one in SCREEN_OPTIONS:
        st.session_state["screen_one"] = saved_screen_one

    if saved_screen_two in SCREEN_OPTIONS:
        st.session_state["screen_two"] = saved_screen_two
    elif st.session_state.get("screen_two") == "None":
        st.session_state["screen_two"] = SCREEN_ORIGINAL_OVERTIME

    st.session_state["layout_mode"] = "Side by side"
    sync_layout_widgets_from_state()


def refresh_panel(panel_key: str, screen_name: str, artifact_paths: Any) -> None:
    if screen_name == SCREEN_MANUAL_4B_EDITOR:
        editor_key = manual_4b_editor_widget_key(
            panel_key,
            artifact_paths.manual_4b_overtime_interpretation,
        )
        st.session_state.pop(editor_key, None)

    if screen_name == SCREEN_OVERTIME_CLASSIFICATION:
        clear_session_state_prefix(f"{panel_key}_overtime_clause_text_")

    st.rerun()


def clear_session_state_prefix(prefix: str) -> None:
    keys_to_remove = [
        key for key in st.session_state.keys() if key.startswith(prefix)
    ]

    for key in keys_to_remove:
        st.session_state.pop(key, None)


def render_processed_file_cleanup_controls() -> None:
    st.header("Processed file cleanup")
    st.caption("Deletes matching files under `data/processed` only. Archive files are never deleted.")

    prefix = st.text_input(
        "Filename prefix to delete",
        key="cleanup_prefix",
        placeholder="MA000018",
    )

    matching_paths = processed_files_matching_prefix(prefix)

    if prefix.strip():
        st.caption(f"Matching non-archive files: {len(matching_paths)}")

    if matching_paths:
        preview_paths = matching_paths[:5]
        preview_text = "\n".join(
            f"- `{format_path_for_display(path)}`" for path in preview_paths
        )
        if len(matching_paths) > len(preview_paths):
            preview_text += f"\n- ... and {len(matching_paths) - len(preview_paths)} more"
        st.markdown(preview_text)

    if st.button("Delete matching processed files", use_container_width=True):
        if not prefix.strip():
            st.error("Enter a filename prefix before deleting files.")
            return

        deleted_paths = delete_processed_files_matching_prefix(prefix)
        if not deleted_paths:
            st.info("No matching non-archive processed files were found.")
            return

        st.success(f"Deleted {len(deleted_paths)} processed files.")
        st.rerun()


def render_pipeline_run_controls(
    selected_award_code: str,
    controls_disabled: bool,
    ruleset_key: str,
) -> None:
    st.header("Pipeline runs")
    st.caption(
        "Runs the review workflow for the selected award code through the formatted ruleset and pseudocode steps."
    )
    current_status = normalized_status_for_award(selected_award_code)
    run_is_active = bool(
        current_status and current_status.get("state") in {"starting", "running"}
    )
    run_controls_disabled = controls_disabled or run_is_active

    full_run_key = f"run_full_{selected_award_code}"
    if st.button(
        "Run active pipeline",
        key=full_run_key,
        use_container_width=True,
        disabled=run_controls_disabled,
    ):
        execute_pipeline_run(selected_award_code, step=None, ruleset_key=ruleset_key)

    step_one_column, step_two_column = st.columns(2, gap="small")
    step_three_column, step_three_b_column = st.columns(2, gap="small")
    step_four_column, step_five_b_column = st.columns(2, gap="small")

    with step_one_column:
        if st.button(
            PIPELINE_STEP_LABELS["1"],
            key=f"run_step_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="1")

    with step_two_column:
        if st.button(
            PIPELINE_STEP_LABELS["2"],
            key=f"run_step_2_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="2")

    with step_three_column:
        if st.button(
            PIPELINE_STEP_LABELS["3"],
            key=f"run_step_3_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="3", ruleset_key=ruleset_key)

    with step_three_b_column:
        if st.button(
            PIPELINE_STEP_LABELS["3b"],
            key=f"run_step_3b_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="3b", ruleset_key=ruleset_key)

    with step_four_column:
        if st.button(
            PIPELINE_STEP_LABELS["4"],
            key=f"run_step_4_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="4", ruleset_key=ruleset_key)

    with step_five_b_column:
        if st.button(
            PIPELINE_STEP_LABELS["5b"],
            key=f"run_step_5b_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="5b", ruleset_key=ruleset_key)

    render_pipeline_run_status(selected_award_code, current_status)


def render_pipeline_run_status(
    selected_award_code: str,
    current_status: dict[str, Any] | None,
) -> None:
    if current_status is None:
        return

    state = str(current_status.get("state", "unknown"))
    status_message = str(current_status.get("message", ""))

    if state == "success" and status_message:
        st.success(status_message)
    elif state == "warning" and status_message:
        st.warning(status_message)
    elif state == "error" and status_message:
        st.error(status_message)
    elif state in {"starting", "running"} and status_message:
        st.info(status_message)

    completed_steps = current_status.get("completed_steps")
    total_steps = current_status.get("total_steps")
    progress_fraction = current_status.get("progress_fraction")
    current_step_label = current_status.get("current_step_label")

    if isinstance(progress_fraction, (int, float)):
        progress_percent = int(max(0.0, min(float(progress_fraction), 1.0)) * 100)
        st.progress(progress_percent)

    if (
        isinstance(completed_steps, int)
        and isinstance(total_steps, int)
        and total_steps > 0
    ):
        progress_caption = f"Progress: {completed_steps} of {total_steps} steps completed."
        if state == "running" and current_step_label:
            progress_caption += f" Current step: {current_step_label}."
        st.caption(progress_caption)

    if state in {"starting", "running"}:
        st.caption(
            "This run is continuing in the background. This panel refreshes automatically every 5 seconds."
        )

    refresh_column, clear_column = st.columns(2, gap="small")

    with refresh_column:
        if st.button(
            "Refresh run status",
            key=f"refresh_run_status_{selected_award_code}",
            use_container_width=True,
        ):
            st.rerun()

    with clear_column:
        if state != "running" and st.button(
            "Clear run status",
            key=f"clear_run_status_{selected_award_code}",
            use_container_width=True,
        ):
            clear_pipeline_run_status(selected_award_code)
            st.rerun()

    log_path = log_path_for_award(selected_award_code)
    log_text = ""
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8").strip()

    if state in {"starting", "running"}:
        st.markdown("**Live run log**")
        if log_text:
            log_lines = log_text.splitlines()
            displayed_log = "\n".join(log_lines[-200:])
            if len(log_lines) > 200:
                st.caption("Showing the most recent 200 log lines.")
            st.code(displayed_log, language="text")
        else:
            st.code("No log output yet.", language="text")
    elif log_text:
        with st.expander("Pipeline run log", expanded=False):
            st.code(log_text, language="text")

def execute_pipeline_run(
    selected_award_code: str,
    step: str | None,
    ruleset_key: str | None = None,
) -> None:
    try:
        start_background_pipeline_run(selected_award_code, step, ruleset_key=ruleset_key)
    except RuntimeError as exc:
        st.error(str(exc))
        return

    st.rerun()


def clear_pipeline_run_status(selected_award_code: str) -> None:
    status_path = status_path_for_award(selected_award_code)
    log_path = log_path_for_award(selected_award_code)

    if status_path.exists():
        status_path.unlink()

    if log_path.exists():
        log_path.unlink()


def pipeline_run_label(step: str | None) -> str:
    """Return the user-facing label for one pipeline step."""
    if step is None:
        return "Active pipeline run"

    return PIPELINE_STEP_LABELS[step]


def combine_pipeline_logs(stdout_text: str, stderr_text: str) -> str:
    """Combine captured stdout and stderr into one reviewable log."""
    sections: list[str] = []

    if stdout_text.strip():
        sections.append(stdout_text.strip())

    if stderr_text.strip():
        sections.append(stderr_text.strip())

    return "\n\n".join(sections)


def load_5b_validation_summary(paths: Any, step: str | None) -> dict[str, Any] | None:
    """Load the 5B validation summary when a 5B run just completed."""
    if step != "5b":
        return None

    validation_json_path = getattr(paths, "core_overtime_validation_json_path", None)
    if validation_json_path is None:
        return None

    if not validation_json_path.exists():
        return None

    validation_data = load_json_file(validation_json_path)

    return {
        "overall_status": validation_data.get("overall_status", "unknown"),
        "passed_rule_count": validation_data.get("passed_rule_count", 0),
        "failed_rule_count": validation_data.get("failed_rule_count", 0),
        "unresolved_rule_count": validation_data.get("unresolved_rule_count", 0),
    }


def run_pipeline_for_award(award_code: str, step: str | None) -> dict[str, Any]:
    """Run the pipeline synchronously for test and utility callers."""
    source_record = source_record_for_award(award_code)
    if source_record["source_type"] == SOURCE_TYPE_FAIR_WORK_HTML:
        url = str(source_record["source_url"])
    else:
        url = ""
    paths = build_paths(award_code, suffix=None, url=url)
    artifact_paths = artifact_paths_for_award(award_code)
    output_buffer = StringIO()
    error_buffer = StringIO()
    started_at = time.perf_counter()

    try:
        with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
            if step is None:
                if source_record["source_type"] == SOURCE_TYPE_LOCAL_PDF:
                    run_pdf_step_1(paths, award_code, source_record)
                    for selected_step in ("2", "3", "3b"):
                        run_selected_step(paths, selected_step)
                else:
                    run_default_pipeline(paths)
            elif step == "1" and source_record["source_type"] == SOURCE_TYPE_LOCAL_PDF:
                run_pdf_step_1(paths, award_code, source_record)
            elif step == "4":
                summarize_overtime_entitlements(
                    interpretation_path=artifact_paths.revised_overtime_interpretation,
                    output_path=artifact_paths.overtime_entitlements,
                )
                print(
                    f"Formatted overtime guide saved to {artifact_paths.overtime_entitlements}"
                )
            else:
                run_selected_step(paths, step)
    except Exception as exc:
        traceback.print_exc(file=error_buffer)
        combined_log = combine_pipeline_logs(
            output_buffer.getvalue(),
            error_buffer.getvalue(),
        )
        if isinstance(exc, AwardPipelineError):
            return {
                "success": False,
                "duration_seconds": time.perf_counter() - started_at,
                "log": combined_log,
            }

        return {
            "success": False,
            "duration_seconds": time.perf_counter() - started_at,
            "log": combined_log,
        }

    return {
        "success": True,
        "duration_seconds": time.perf_counter() - started_at,
        "log": combine_pipeline_logs(output_buffer.getvalue(), error_buffer.getvalue()),
        "validation_summary": load_5b_validation_summary(paths, step),
    }


def run_pdf_step_1(paths: Any, award_code: str, source_record: dict[str, Any]) -> None:
    """Run step 1 for a registered local PDF source."""
    pdf_path = Path(str(source_record["source_path"]))
    if not pdf_path.exists():
        raise AwardPipelineError(f"Missing registered PDF source for {award_code}: {pdf_path}")

    markdown_text, award, excluded_sections, diagnostics = extract_pdf_to_award(pdf_path)
    processed_dir = paths.award_json_path.parent.parent
    raw_dir = paths.raw_html_path.parent
    write_pdf_outputs(
        pdf_path=pdf_path,
        markdown_text=markdown_text,
        award=award,
        excluded_sections=excluded_sections,
        diagnostics=diagnostics,
        output_stem_value=paths.output_stem,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )


def render_json_expander(
    label: str,
    value: dict[str, Any],
    *,
    key_suffix: str = "",
) -> None:
    with st.expander(label, expanded=False):
        rendered_json = json.dumps(value, indent=2, ensure_ascii=False)
        line_count = rendered_json.count("\n") + 1
        widget_height = min(max(220, line_count * 20), 700)
        unique_widget_key = (
            f"{label}_{key_suffix}_{abs(hash(rendered_json))}_json_view"
            if key_suffix
            else f"{label}_{abs(hash(rendered_json))}_json_view"
        )
        st.text_area(
            label,
            value=rendered_json,
            height=widget_height,
            disabled=True,
            key=unique_widget_key,
        )


def bool_label(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def render_validation_summary(artifact_paths: Any) -> None:
    validation_data = load_optional_json_file(artifact_paths.core_overtime_validation_json)
    if validation_data is None:
        st.info("No 5B validation report was found for this output yet.")
        return

    overall_status = str(validation_data.get("overall_status", "unknown"))
    passed_count = int(validation_data.get("passed_rule_count", 0))
    failed_count = int(validation_data.get("failed_rule_count", 0))
    unresolved_count = int(validation_data.get("unresolved_rule_count", 0))

    if overall_status == "passed":
        st.success("5B validation passed.")
    elif overall_status == "unresolved":
        st.warning("5B validation completed with unresolved coverage checks.")
    else:
        st.warning("5B validation found coverage issues.")

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Passed rules", passed_count)
    metric_two.metric("Failed rules", failed_count)
    metric_three.metric("Unresolved rules", unresolved_count)

    validation_report = read_text_file(artifact_paths.core_overtime_validation_markdown)
    if validation_report.exists:
        with st.expander("5B validation report", expanded=False):
            st.markdown(validation_report.text)


def render_ruleset_validation_summary(ruleset_artifacts: Any) -> None:
    validation_data = load_optional_json_file(
        ruleset_artifacts.pseudocode_validation_json
    )
    if validation_data is None:
        st.info("No 5B validation report was found for this output yet.")
        return

    overall_status = str(validation_data.get("overall_status", "unknown"))
    passed_count = int(validation_data.get("passed_rule_count", 0))
    failed_count = int(validation_data.get("failed_rule_count", 0))
    unresolved_count = int(validation_data.get("unresolved_rule_count", 0))

    if overall_status == "passed":
        st.success("5B validation passed.")
    elif overall_status == "unresolved":
        st.warning("5B validation completed with unresolved coverage checks.")
    else:
        st.warning("5B validation found coverage issues.")

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Passed rules", passed_count)
    metric_two.metric("Failed rules", failed_count)
    metric_three.metric("Unresolved rules", unresolved_count)

    validation_report = read_text_file(ruleset_artifacts.pseudocode_validation_markdown)
    if validation_report.exists:
        with st.expander("5B validation report", expanded=False):
            st.markdown(validation_report.text)


def load_optional_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    return load_json_file(path)


def apply_review_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
        }
        h1 {
            font-size: 1.45rem !important;
            margin-bottom: 0.45rem !important;
        }
        h3 {
            font-size: 1.02rem !important;
            margin-top: 0 !important;
            margin-bottom: 0.45rem !important;
            line-height: 1.35 !important;
        }
        h4 {
            font-size: 0.94rem !important;
            margin-top: 0.7rem !important;
            margin-bottom: 0.3rem !important;
            line-height: 1.35 !important;
        }
        p, li {
            font-size: 0.9rem;
            line-height: 1.45;
        }
        div[data-testid="stMarkdownContainer"] ul {
            padding-left: 1.15rem;
            margin-top: 0.25rem;
            margin-bottom: 0.45rem;
        }
        div[data-testid="stMarkdownContainer"] ul ul {
            padding-left: 1.4rem;
            margin-top: 0.2rem;
            margin-bottom: 0.2rem;
            list-style-type: circle;
        }
        div[data-testid="stMarkdownContainer"] ul ul ul {
            list-style-type: square;
        }
        div[data-testid="stCaptionContainer"] p {
            font-size: 0.78rem;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.5rem;
        }
        div[data-testid="stButton"] button {
            padding: 0.25rem 0.45rem;
            min-height: 2rem;
            font-size: 0.82rem;
        }
        div[data-baseweb="select"] {
            font-size: 0.84rem;
        }
        div[data-testid="stMetric"] {
            border: 1px solid #d7dde5;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            background: #f8fafc;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.8rem;
        }
        textarea {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem !important;
            line-height: 1.25 !important;
        }
        pre, code {
            font-size: 0.78rem !important;
        }
        div[data-testid="stExpander"] details {
            padding-top: 0;
        }
        .review-file-details {
            font-size: 0.83rem;
            line-height: 1.5;
            margin-top: 0.15rem;
            margin-bottom: 0.45rem;
        }
        .review-file-detail-row {
            margin-bottom: 0.15rem;
        }
        .review-refresh-button div[data-testid="stButton"] button {
            min-height: 1.75rem;
            padding: 0.15rem 0.35rem;
            font-size: 0.76rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
