import ast
import hashlib
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
    DOCUMENTS_DIR,
    SOURCE_TYPE_FAIR_WORK_HTML,
    SOURCE_TYPE_LOCAL_PDF,
    can_run_pipeline_for_award,
    register_local_pdf_source,
    source_record_for_award,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    PENALTIES_RULESET,
)
from src.common.overtime_rules import (
    HIGH_IMPACT_VALIDATION_SECTION,
    HIDDEN_DIAGNOSTIC_VALIDATION_SECTION,
    REVIEW_NOTES_VALIDATION_SECTION,
    VALIDATION_SECTION_TITLES,
    categorize_validation_warnings,
)
from src.common.prompt_logging import configure_prompt_log
from src.step_1_2_parse_award.run import (
    extract_pdf_to_award,
    write_pdf_step_outputs as write_pdf_outputs,
)
from src.step_4_1_format_ruleset.run import summarize_overtime_entitlements
from src.step_6_1_generate_calculator_yaml.core import (
    align_questionnaire_to_calculator_contract,
    normalize_response_data,
    write_python_output,
)
from src.step_6_1_generate_calculator_yaml.run import load_inputs
from src.step_6_2_validate_calculator_ruleset.run import (
    CalculatorRulesetValidationError,
    validate_calculator_python,
)
from streamlit_review.pipeline_runs import (
    log_path_for_award,
    normalized_status_for_award,
    start_background_pipeline_run,
    status_path_for_award,
)
from streamlit_review.output_data import (
    artifact_paths_for_award,
    calculator_rules_questionnaire_path_for_award,
    calculator_rules_python_path_for_award,
    calculator_rules_validation_json_path_for_award,
    calculator_rules_validation_markdown_path_for_award,
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
    source_path_for_ruleset_core_overtime_pseudocode,
    source_path_for_ruleset_manual_ruleset_editor,
    write_text_file,
)


SCREEN_L1_PAYMENT = "1. Payment clauses"
SCREEN_L2_PAYMENT = "2. Payment clause categories"
SCREEN_OVERTIME_CLASSIFICATION = "3. Ruleset clause classification"
SCREEN_EXPERT_A_OVERTIME = "4. Step 3.1 Expert A ruleset draft"
SCREEN_EXPERT_B_OVERTIME = "5. Step 3.1 Expert B ruleset draft"
SCREEN_EXPERT_COMPARISON = "6. Comparison of expert outputs"
SCREEN_ORIGINAL_OVERTIME = "7. Step 3.1 Combined ruleset"
SCREEN_REVIEW_FEEDBACK = "8. Step 3.2 Review and revised ruleset"
SCREEN_FORMATTED_4A = "9. Step 4.1 Formatted overtime guide"
SCREEN_HUMAN_REVIEW = "10. Step 4.9 Human review"
SCREEN_CORE_OVERTIME_PSEUDOCODE = "11. Step 5.1 Pseudocode"
SCREEN_CALCULATOR_QUESTIONNAIRE = "12. Step 6.1 Calculator Ruleset"
SCREEN_CALCULATOR_PYTHON = "13. Step 6.1 Calculator Python"
CLAUSE_REFERENCE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\b",
    re.IGNORECASE,
)

RULESET_OPTIONS = {
    "Overtime creation": OVERTIME_CREATION_RULESET,
    "Overtime consequence": OVERTIME_CONSEQUENCE_RULESET,
    "Penalties": PENALTIES_RULESET,
}

RULESET_SEQUENCE = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
    PENALTIES_RULESET,
)

STEP3_RUN_RULESET_OPTIONS = {
    "Overtime creation": OVERTIME_CREATION_RULESET,
    "Overtime consequence": OVERTIME_CONSEQUENCE_RULESET,
    "Penalties": PENALTIES_RULESET,
}

ADD_NEW_AWARD_LABEL = "Add new award"

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
    SCREEN_HUMAN_REVIEW,
    SCREEN_CORE_OVERTIME_PSEUDOCODE,
    SCREEN_CALCULATOR_QUESTIONNAIRE,
    SCREEN_CALCULATOR_PYTHON,
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
    "2.1": "Classify clauses",
    "2.2": "Classify ruleset clauses",
    "3.1": "Generate ruleset",
    "3.2": "Review overtime ruleset",
    "4.1": "Format overtime guide",
    "5.1": "Generate pseudocode",
    "6.1": "Generate calculator Python",
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

    st.caption(f"Reviewing canonical pipeline outputs for `{validated_award_code}`.")

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

        award_selection_options = [*award_codes, ADD_NEW_AWARD_LABEL]
        selected_award_choice = st.selectbox(
            "Award code",
            award_selection_options,
            index=award_selection_index(award_codes, st.session_state["award_code"]),
            key="award_selection",
        )

        if selected_award_choice == ADD_NEW_AWARD_LABEL:
            if "award_code_new" not in st.session_state:
                st.session_state["award_code_new"] = ""
            st.text_input(
                "MA award code (optional when uploading a PDF)",
                key="award_code_new",
                placeholder="MA000002",
            )
            uploaded_pdf = st.file_uploader(
                "Or upload a PDF",
                type=["pdf"],
                key="new_award_pdf",
            )
            uploaded_pdf_code = ""
            if uploaded_pdf is not None:
                uploaded_pdf_code = register_uploaded_pdf(
                    uploaded_pdf,
                    output_stem=st.session_state["award_code_new"].strip() or None,
                )

            selected_award_code = selected_award_code_from_choice(
                selected_award_choice,
                st.session_state["award_code_new"] or uploaded_pdf_code,
            )
            if uploaded_pdf_code:
                st.caption(
                    f"Using PDF filename stem as the local output set: `{uploaded_pdf_code}`"
                )
            else:
                st.caption("Enter an MA code or upload a PDF to add a review workspace.")
        else:
            st.session_state["award_code"] = selected_award_choice
            selected_award_code = selected_award_code_from_choice(selected_award_choice)
            st.caption(f"Selected saved output set: `{selected_award_choice}`")

        validated_award_code, validation_error = validate_award_code_input(
            selected_award_code,
            existing_output_sets=award_codes,
            local_pdf_codes=[uploaded_pdf_code] if selected_award_choice == ADD_NEW_AWARD_LABEL else None,
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
            "Step 3 ruleset to view",
            list(RULESET_OPTIONS),
            key="step3_ruleset_label",
        )
        st.session_state["step3_ruleset"] = RULESET_OPTIONS[selected_label]

        st.divider()
        render_pipeline_run_controls(
            selected_award_code=validated_award_code or selected_award_code,
            controls_disabled=pipeline_controls_disabled,
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

        if st.button("3.1 combined ruleset", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_ORIGINAL_OVERTIME
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("4.1 formatted overtime guide", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_FORMATTED_4A
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("3.2 manual ruleset editor", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_HUMAN_REVIEW
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"
            sync_layout_widgets_from_state()

        if st.button("5.1 pseudocode", use_container_width=True):
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


def award_selection_index(award_codes: list[str], selected_award_code: str) -> int:
    normalized_award_code = selected_award_code.strip()

    if normalized_award_code in award_codes:
        return award_codes.index(normalized_award_code)

    upper_lookup = {award_code.upper(): index for index, award_code in enumerate(award_codes)}
    if normalized_award_code.upper() in upper_lookup:
        return upper_lookup[normalized_award_code.upper()]

    return len(award_codes)


def selected_award_code_from_choice(
    selected_award_choice: str,
    award_code_new: str | None = None,
) -> str:
    if selected_award_choice == ADD_NEW_AWARD_LABEL:
        return (award_code_new or "").strip()

    return selected_award_choice.strip()


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
    local_pdf_codes: list[str] | None = None,
) -> tuple[str | None, str | None]:
    available_output_sets = existing_output_sets or []
    available_local_pdf_codes = local_pdf_codes or []
    selected_award_code = value.strip()
    if not selected_award_code:
        return None, "Enter an award code to review or run."

    if selected_award_code in available_output_sets:
        return selected_award_code, None

    if selected_award_code in available_local_pdf_codes:
        return selected_award_code, None

    try:
        normalized_award_code = normalize_award_code(selected_award_code.upper())
    except ValueError:
        return None, "Select an existing output set or enter an award code like `MA000002`."

    return normalized_award_code, None


def register_uploaded_pdf(uploaded_pdf: Any, output_stem: str | None = None) -> str:
    """Persist an uploaded PDF under its original filename and register its stem."""
    original_filename = Path(str(uploaded_pdf.name)).name
    pdf_path = DOCUMENTS_DIR / original_filename
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(uploaded_pdf.getvalue())

    selected_output_stem = (output_stem or Path(original_filename).stem).strip()
    if not selected_output_stem:
        raise ValueError("The uploaded PDF filename must contain a name before .pdf.")

    register_local_pdf_source(
        award_code=selected_output_stem,
        pdf_path=pdf_path,
        display_name=original_filename,
    )
    return selected_output_stem


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
        ruleset_key,
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
        SCREEN_HUMAN_REVIEW: render_manual_ruleset_editor_screen,
        SCREEN_CORE_OVERTIME_PSEUDOCODE: render_core_overtime_pseudocode_screen,
        SCREEN_CALCULATOR_QUESTIONNAIRE: render_calculator_questionnaire_screen,
        SCREEN_CALCULATOR_PYTHON: render_calculator_python_screen,
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
    tags = record.get("tags", [])
    if tags:
        st.write(", ".join(tags))
    else:
        st.caption(
            "No payment or definition category assigned. Retained for audit; "
            "not selected for downstream ruleset classification."
        )
    st.markdown("**Reason**")
    st.write(record.get("reason", ""))
    render_json_expander("Selected L2 JSON", record, key_suffix=panel_key)


def render_overtime_classification_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
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
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    json_path = ruleset_artifacts.combined_json
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.combined_markdown,
        panel_key=panel_key,
        enable_clause_hover=True,
    )


def render_expert_a_overtime_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    json_path = ruleset_artifacts.expert_a_markdown.with_suffix(".json")
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.expert_a_markdown,
        panel_key=panel_key,
    )


def render_expert_b_overtime_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    json_path = ruleset_artifacts.expert_b_markdown.with_suffix(".json")
    render_overtime_rules_json(
        json_path,
        source_markdown_path=ruleset_artifacts.expert_b_markdown,
        panel_key=panel_key,
    )


def render_expert_comparison_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
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
            render_validation_warning_sections(
                [str(warning) for warning in validation_warnings]
            )

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


def award_code_for_artifact_paths(artifact_paths: Any) -> str:
    """Derive the selected award code from the active artifact bundle."""
    return artifact_paths.payment_classification.parent.name


def render_review_feedback_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    original_data = load_optional_json_file(ruleset_artifacts.combined_json) or {}
    evaluator_data = load_json_or_show_error(ruleset_artifacts.evaluator_feedback_json)
    creator_data = load_json_or_show_error(ruleset_artifacts.creator_response_json)
    revised_data = load_json_or_show_error(ruleset_artifacts.revised_json)

    if evaluator_data is None or creator_data is None or revised_data is None:
        return

    decision_rows = build_review_decision_rows(
        evaluator_feedback_data=evaluator_data,
        creator_response_data=creator_data,
        original_rules_data=original_data,
        revised_rules_data=revised_data,
    )
    ordered_decision_rows = order_review_decision_rows_for_display(decision_rows)
    concern_rows = review_decision_concerns(ordered_decision_rows)
    decision_summary = summarize_review_decision_rows(ordered_decision_rows)
    validation_warnings = revised_data.get("validation_warnings", [])
    clause_index = load_clause_hover_index(
        str(revised_data.get("source_clause_classification_file") or "")
    )
    creator_validation_error = str(creator_data.get("validation_error", "")).strip()
    creator_raw_response = str(creator_data.get("raw_creator_response", "")).strip()

    st.markdown("#### Generated artifacts")
    evaluator_column, creator_column, revised_column = st.columns(3, gap="small")

    with evaluator_column:
        render_file_details(
            ruleset_artifacts.evaluator_feedback_json,
            source_path=ruleset_artifacts.evaluator_feedback,
            file_label="Evaluator review JSON",
            source_label="Evaluator review markdown",
        )

    with creator_column:
        render_file_details(
            ruleset_artifacts.creator_response_json,
            source_path=ruleset_artifacts.creator_response,
            file_label="Creator response JSON",
            source_label="Creator response markdown",
        )

    with revised_column:
        render_file_details(
            ruleset_artifacts.revised_json,
            source_path=ruleset_artifacts.revised_markdown,
            file_label="Revised ruleset JSON",
            source_label="Revised ruleset markdown",
        )

    if creator_validation_error:
        creator_failure_explanation = explain_creator_validation_failure(
            creator_validation_error,
            creator_raw_response,
        )
        st.warning(creator_failure_explanation)
        st.write(f"Validation issue: {creator_validation_error}")

    review_column, outcome_column = st.columns([1.2, 1.0], gap="medium")

    with review_column:
        with st.container(border=True):
            st.markdown("#### Review decision ledger")
            render_review_decision_summary(decision_summary)

            if concern_rows or validation_warnings:
                st.markdown("##### Concern items")
                if concern_rows:
                    for row in concern_rows:
                        render_review_decision_card(
                            row,
                            expanded=True,
                            clause_index=clause_index,
                        )
                if isinstance(validation_warnings, list):
                    render_validation_warning_sections_with_hover(
                        [str(warning) for warning in validation_warnings],
                        clause_index,
                    )
            else:
                st.info("No rejected or unimplemented evaluator recommendations were found.")

            st.markdown("##### Rule-by-rule decisions")
            for row in ordered_decision_rows:
                render_review_decision_card(
                    row,
                    expanded=False,
                    clause_index=clause_index,
                )

        with st.container():
            with st.expander("Raw evaluator commentary", expanded=False):
                render_evaluator_feedback_panel(ruleset_artifacts.evaluator_feedback)

            with st.expander("Raw creator commentary", expanded=False):
                render_creator_commentary_panel(ruleset_artifacts.creator_response)

    with outcome_column:
        with st.container(border=True):
            st.markdown("#### Final outcome")
            render_overtime_rules_json(
                ruleset_artifacts.revised_json,
                source_markdown_path=ruleset_artifacts.revised_markdown,
                panel_key=f"{panel_key}_review_feedback_outcome",
                enable_clause_hover=True,
            )


def summarize_review_decision_rows(decision_rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(decision_rows),
        "accepted": 0,
        "modified": 0,
        "kept": 0,
        "rejected": 0,
        "not_implemented": 0,
        "unchanged_existing": 0,
        "modified_existing": 0,
        "rejected_new": 0,
    }

    for row in decision_rows:
        final_decision = str(row.get("final_decision", "")).strip().lower()
        is_new_rule = bool(row.get("is_new_rule"))
        final_rule_changed = bool(row.get("final_rule_changed_from_combined"))
        if final_decision in summary:
            summary[final_decision] += 1

        if bool(row.get("is_concern")):
            summary["not_implemented"] += 1

        if is_new_rule:
            if final_decision == "rejected":
                summary["rejected_new"] += 1
            continue

        if final_decision == "removed":
            continue

        if final_rule_changed or final_decision == "modified":
            summary["modified_existing"] += 1
        else:
            summary["unchanged_existing"] += 1

    return summary


def build_review_decision_rows(
    *,
    evaluator_feedback_data: dict[str, Any],
    creator_response_data: dict[str, Any],
    original_rules_data: dict[str, Any] | None = None,
    revised_rules_data: dict[str, Any],
) -> list[dict[str, Any]]:
    evaluator_reviews = evaluator_feedback_data.get("rule_reviews", [])
    evaluator_new_rules = evaluator_feedback_data.get("new_rules", [])
    creator_rule_updates = creator_response_data.get("rule_updates", [])
    creator_new_rule_reviews = creator_response_data.get("new_rule_reviews", [])
    original_rules = (original_rules_data or {}).get("rules", [])
    review_decisions = revised_rules_data.get("review_decisions", [])
    final_rules = revised_rules_data.get("rules", [])

    evaluator_review_map = {
        str(review.get("rule_id", "")).strip(): review
        for review in evaluator_reviews
        if isinstance(review, dict)
    }
    evaluator_new_rule_map = {
        str(rule.get("rule_id", "")).strip(): rule
        for rule in evaluator_new_rules
        if isinstance(rule, dict)
    }
    creator_rule_update_map = {
        str(update.get("rule_id", "")).strip(): update
        for update in creator_rule_updates
        if isinstance(update, dict)
    }
    creator_new_rule_review_map = {
        str(review.get("rule_id", "")).strip(): review
        for review in creator_new_rule_reviews
        if isinstance(review, dict)
    }
    original_rule_map = {
        str(rule.get("rule_id", "")).strip(): rule
        for rule in original_rules
        if isinstance(rule, dict)
    }
    final_rule_map = {
        str(rule.get("rule_id", "")).strip(): rule
        for rule in final_rules
        if isinstance(rule, dict)
    }

    rows: list[dict[str, Any]] = []

    for review_decision in review_decisions:
        if not isinstance(review_decision, dict):
            continue

        rule_id = str(review_decision.get("rule_id", "")).strip()
        evaluator_recommendation = str(
            review_decision.get("evaluator_recommendation", "")
        ).strip()
        creator_decision = str(review_decision.get("creator_decision", "")).strip()
        final_decision = str(review_decision.get("final_decision", "")).strip()

        evaluator_review = evaluator_review_map.get(rule_id)
        evaluator_new_rule = evaluator_new_rule_map.get(rule_id)
        creator_rule_update = creator_rule_update_map.get(rule_id)
        creator_new_rule_review = creator_new_rule_review_map.get(rule_id)
        original_rule = original_rule_map.get(rule_id)
        final_rule = final_rule_map.get(rule_id)

        evaluator_rationale = ""
        proposed_rule_markdown = ""
        if isinstance(evaluator_review, dict):
            evaluator_rationale = str(evaluator_review.get("rationale", "")).strip()
        if isinstance(evaluator_new_rule, dict):
            proposed_rule_markdown = str(
                evaluator_new_rule.get("rule_markdown", "")
            ).strip()

        creator_reason = str(review_decision.get("reason", "")).strip()
        creator_payload = creator_rule_update or creator_new_rule_review or {}
        creator_updated_rule_markdown = ""
        if isinstance(creator_payload, dict):
            updated_rule = creator_payload.get("updated_rule")
            if isinstance(updated_rule, dict):
                creator_updated_rule_markdown = str(
                    updated_rule.get("rule_markdown", "")
                ).strip()

        original_rule_markdown = ""
        original_clause_references: list[str] = []
        if isinstance(original_rule, dict):
            original_rule_markdown = str(original_rule.get("rule_markdown", "")).strip()
            raw_original_clause_references = original_rule.get("clause_references", [])
            if isinstance(raw_original_clause_references, list):
                original_clause_references = [
                    str(reference).strip()
                    for reference in raw_original_clause_references
                    if str(reference).strip()
                ]

        final_rule_markdown = ""
        clause_references: list[str] = []
        if isinstance(final_rule, dict):
            final_rule_markdown = str(final_rule.get("rule_markdown", "")).strip()
            raw_clause_references = final_rule.get("clause_references", [])
            if isinstance(raw_clause_references, list):
                clause_references = [
                    str(reference).strip()
                    for reference in raw_clause_references
                    if str(reference).strip()
                ]

        final_rule_changed_from_combined = (
            bool(original_rule_markdown)
            and bool(final_rule_markdown)
            and original_rule_markdown != final_rule_markdown
        )

        is_concern = recommendation_not_implemented(
            evaluator_recommendation=evaluator_recommendation,
            creator_decision=creator_decision,
            final_decision=final_decision,
        )

        rows.append(
            {
                "rule_id": rule_id,
                "evaluator_recommendation": evaluator_recommendation,
                "creator_decision": creator_decision,
                "final_decision": final_decision,
                "is_new_rule": evaluator_recommendation.strip().lower() == "add",
                "evaluator_rationale": evaluator_rationale,
                "creator_reason": creator_reason,
                "proposed_rule_markdown": proposed_rule_markdown,
                "creator_updated_rule_markdown": creator_updated_rule_markdown,
                "original_rule_markdown": original_rule_markdown,
                "original_clause_references": original_clause_references,
                "final_rule_markdown": final_rule_markdown,
                "clause_references": clause_references,
                "final_rule_changed_from_combined": final_rule_changed_from_combined,
                "is_concern": is_concern,
            }
        )

    return rows


def recommendation_not_implemented(
    *,
    evaluator_recommendation: str,
    creator_decision: str,
    final_decision: str,
) -> bool:
    normalized_recommendation = evaluator_recommendation.strip().lower()
    normalized_creator_decision = creator_decision.strip().lower()
    normalized_final_decision = final_decision.strip().lower()

    if normalized_recommendation == "add":
        return normalized_final_decision == "rejected"

    if normalized_recommendation in {"modify", "remove"}:
        return normalized_creator_decision == "keep"

    return False


def review_decision_concerns(
    decision_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [row for row in decision_rows if bool(row.get("is_concern"))]


def order_review_decision_rows_for_display(
    decision_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Show new-rule decisions before original-rule decisions in Screen 8."""
    return sorted(
        decision_rows,
        key=lambda row: (
            0 if bool(row.get("is_new_rule")) else 1,
            0 if str(row.get("final_decision", "")).strip().lower() in {"accepted", "modified"} else 1,
            str(row.get("rule_id", "")),
        ),
    )


def render_review_decision_summary(summary: dict[str, int]) -> None:
    st.markdown("**Decision summary**")
    summary_columns = st.columns(6, gap="small")
    summary_columns[0].metric("Total", summary["total"])
    summary_columns[1].metric("Accept New", summary["accepted"])
    summary_columns[2].metric("Modify Existing", summary["modified_existing"])
    summary_columns[3].metric("Unchanged", summary["unchanged_existing"])
    summary_columns[4].metric("Modify Rejected", summary["not_implemented"])
    summary_columns[5].metric("New Rejected", summary["rejected_new"])


def explain_creator_validation_failure(
    validation_error: str,
    raw_creator_response: str,
) -> str:
    """Explain creator failures in reviewer-friendly wording."""
    stripped_response = raw_creator_response.rstrip()
    likely_truncated = bool(stripped_response) and not stripped_response.endswith("}")

    if likely_truncated:
        return (
            "The creator response could not be applied automatically in this run and "
            "looks likely to have been truncated before the JSON finished. "
            "The revised ruleset preserved the Screen 7 combined ruleset, so "
            "`keep/kept` rows below reflect fallback preservation rather than a successful "
            "review rewrite."
        )

    return (
        "The creator response could not be applied automatically in this run. "
        "The revised ruleset preserved the Screen 7 combined ruleset, so "
        "`keep/kept` rows below reflect fallback preservation rather than a successful "
        "review rewrite."
    )


def render_review_decision_card(
    decision_row: dict[str, Any],
    *,
    expanded: bool,
    clause_index: dict[str, dict[str, str]] | None = None,
) -> None:
    rule_id = str(decision_row.get("rule_id", "")).strip()
    evaluator_recommendation = str(
        decision_row.get("evaluator_recommendation", "")
    ).strip()
    creator_decision = str(decision_row.get("creator_decision", "")).strip()
    final_decision = str(decision_row.get("final_decision", "")).strip()
    clause_references = decision_row.get("clause_references", [])
    clause_text = ", ".join(clause_references) if isinstance(clause_references, list) else ""

    label = (
        f"{rule_id or 'rule'} | evaluator: {evaluator_recommendation or 'n/a'} | "
        f"creator: {creator_decision or 'n/a'} | final: {final_decision or 'n/a'}"
    )

    with st.expander(label, expanded=expanded):
        if bool(decision_row.get("is_concern")):
            st.warning("Evaluator recommendation was not implemented in the final ruleset.")

        active_clause_index = clause_index or {}

        if clause_text:
            st.write("Clause references:")
            if active_clause_index:
                render_clause_reference_badges(clause_references, active_clause_index)
                render_clause_source_details(
                    clause_references,
                    active_clause_index,
                    label_prefix="Source clause",
                )
            else:
                st.write(clause_text)

        st.write(
            " | ".join(
                [
                    f"Evaluator recommendation: {evaluator_recommendation or 'n/a'}",
                    f"Creator decision: {creator_decision or 'n/a'}",
                    f"Final outcome: {final_decision or 'n/a'}",
                ]
            )
        )

        evaluator_rationale = str(decision_row.get("evaluator_rationale", "")).strip()
        if evaluator_rationale:
            st.markdown("**Evaluator rationale**")
            st.write(evaluator_rationale)

        proposed_rule_markdown = str(
            decision_row.get("proposed_rule_markdown", "")
        ).strip()
        if proposed_rule_markdown:
            st.markdown("**Evaluator proposed rule**")
            st.markdown(proposed_rule_markdown)

        creator_reason = str(decision_row.get("creator_reason", "")).strip()
        if creator_reason:
            st.markdown("**Creator reason**")
            st.write(creator_reason)

        creator_updated_rule_markdown = str(
            decision_row.get("creator_updated_rule_markdown", "")
        ).strip()
        if creator_updated_rule_markdown:
            st.markdown("**Creator revised rule text**")
            st.markdown(creator_updated_rule_markdown)

        original_rule_markdown = str(
            decision_row.get("original_rule_markdown", "")
        ).strip()
        final_rule_markdown = str(decision_row.get("final_rule_markdown", "")).strip()
        if original_rule_markdown or final_rule_markdown:
            compare_label = "Quick compare: Screen 7 combined rule vs Screen 8 revised rule"
            with st.expander(compare_label, expanded=expanded and bool(decision_row.get("is_concern"))):
                if original_rule_markdown:
                    st.markdown("**Screen 7 combined rule**")
                    st.markdown(original_rule_markdown)
                else:
                    st.info("No matching Screen 7 combined rule was found for this row.")

                if final_rule_markdown:
                    st.markdown("**Screen 8 revised rule**")
                    st.markdown(final_rule_markdown)
                else:
                    st.info("No matching Screen 8 revised rule was found for this row.")


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
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    formatted_json_path = ruleset_artifacts.formatted_markdown.with_name(
        f"{ruleset_artifacts.formatted_markdown.stem}_metadata.json"
    )
    formatted_data = load_optional_json_file(formatted_json_path) or {}
    validation_warnings = formatted_data.get("validation_warnings", [])

    if isinstance(validation_warnings, list) and validation_warnings:
        st.warning(
            "**Formatting catch-all — reviewed rules omitted by the formatter:** "
            f"{len(validation_warnings)} rule(s). The rules remain part of the "
            "reviewed ruleset and require placement."
        )
        with st.expander("Reviewed rules omitted by the formatter", expanded=True):
            for warning in validation_warnings:
                st.write(f"- {formatted_ruleset_warning_rule_text(str(warning))}")

    render_markdown_file(
        ruleset_artifacts.formatted_markdown,
        source_path=ruleset_artifacts.revised_markdown,
    )


def render_manual_ruleset_editor_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    save_path = ruleset_artifacts.manual_ruleset_markdown
    source_path = source_path_for_ruleset_manual_ruleset_editor(ruleset_artifacts)
    source_content = read_text_file(source_path)

    render_file_details(
        save_path,
        source_path=source_path,
        file_label="Save target",
        source_label="Editor source",
    )

    if not source_content.exists:
        render_missing_file(source_path)
        return

    editor_key = manual_ruleset_editor_widget_key(
        panel_key,
        save_path,
    )
    edited_markdown = st.text_area(
        "Manual ruleset markdown",
        value=source_content.text,
        height=610,
        label_visibility="collapsed",
        key=editor_key,
    )

    if st.button("Save updated version", key=f"{editor_key}_save"):
        if not edited_markdown.strip():
            st.error("The edited overtime markdown is empty. Nothing was saved.")
            return

        write_text_file(save_path, edited_markdown)
        st.success(
            "Saved updated version to "
            f"`{format_path_for_display(save_path)}`."
        )


def render_core_overtime_pseudocode_screen(artifact_paths: Any, panel_key: str, ruleset_key: str) -> None:
    del panel_key
    ruleset_artifacts = ruleset_artifact_paths_for_award(
        award_code_for_artifact_paths(artifact_paths),
        ruleset_key,
    )
    render_markdown_file(
        ruleset_artifacts.pseudocode_markdown,
        source_path=source_path_for_ruleset_core_overtime_pseudocode(ruleset_artifacts),
    )
    render_ruleset_validation_summary(ruleset_artifacts)


def manual_ruleset_editor_widget_key(panel_key: str, output_path: Path) -> str:
    return f"{panel_key}_manual_ruleset_editor_{output_path.stem}"


def render_calculator_python_screen(
    artifact_paths: Any,
    panel_key: str,
    ruleset_key: str,
) -> None:
    del ruleset_key

    award_code = award_code_for_artifact_paths(artifact_paths)
    python_path = calculator_rules_python_path_for_award(award_code)
    render_file_details(python_path)
    python_content = read_text_file(python_path)

    if not python_content.exists:
        render_missing_file(python_path)
        st.info("Run step 6.1 to create the first calculator Python draft.")
        return

    calculator_warnings = calculator_warnings_from_python_text(python_content.text)
    if calculator_warnings:
        st.error(
            "**Calculator is not approved for use until these items are reviewed:** "
            f"{len(calculator_warnings)} item(s)."
        )
        with st.expander("Calculator generation warnings", expanded=False):
            for warning in calculator_warnings:
                st.write(f"- {warning}")

    render_calculator_ruleset_validation_panel(award_code, python_path)

    st.subheader("Calculator Python")
    editor_key = calculator_python_editor_widget_key(panel_key, python_path)
    with st.expander("Edit calculator Python", expanded=True):
        edited_python = st.text_area(
            "Calculator Python source",
            value=python_content.text,
            height=610,
            key=editor_key,
        )

        if st.button("Save updated Python", key=f"{editor_key}_save"):
            if not edited_python.strip():
                st.error("The calculator Python file is empty. Nothing was saved.")
                return
            try:
                ast.parse(edited_python)
            except SyntaxError as exc:
                st.error(f"Python is invalid and was not saved: {exc}")
                return

            write_text_file(python_path, edited_python)
            st.success(f"Saved updated Python to `{format_path_for_display(python_path)}`.")


def render_calculator_questionnaire_screen(
    artifact_paths: Any,
    panel_key: str,
    ruleset_key: str,
) -> None:
    del ruleset_key

    award_code = award_code_for_artifact_paths(artifact_paths)
    questionnaire_path = calculator_rules_questionnaire_path_for_award(award_code)
    python_path = calculator_rules_python_path_for_award(award_code)
    render_file_details(
        questionnaire_path,
        source_path=python_path if python_path.exists() else None,
        file_label="Displayed questionnaire JSON",
        source_label="Current calculator Python",
    )
    questionnaire_content = read_text_file(questionnaire_path)

    if not questionnaire_content.exists:
        render_missing_file(questionnaire_path)
        st.info(
            "Run step 6.1 to create the first calculator questionnaire draft before editing it here."
        )
        return

    try:
        loaded_questionnaire = json.loads(questionnaire_content.text)
    except json.JSONDecodeError as exc:
        st.error(f"Questionnaire JSON is invalid on disk: {exc}")
        return

    if not isinstance(loaded_questionnaire, dict):
        st.error("Questionnaire JSON must be a JSON object.")
        return

    loaded_questionnaire = align_questionnaire_to_calculator_contract(
        loaded_questionnaire
    )

    questionnaire_answers = loaded_questionnaire.get("questionnaire_answers")
    if not isinstance(questionnaire_answers, dict):
        st.error("Questionnaire JSON is missing questionnaire_answers.")
        return

    editor_key = calculator_questionnaire_editor_widget_key(panel_key, questionnaire_path)

    st.caption(
        "This ruleset is the structured calculator input derived from the reviewed step 3.2 rulesets. "
        "Use it to confirm the live calculator settings before generating or regenerating the Python rules file."
    )
    st.caption(
        "Review the calculator answers field by field. Saving this form updates the questionnaire JSON and rebuilds the Python rules file."
    )

    review_required_questions = calculator_questions_requiring_review(
        questionnaire_answers
    )
    if review_required_questions:
        st.error(
            "**Calculator review is incomplete.** "
            f"Resolve the following {len(review_required_questions)} item(s) "
            "before approving this calculator:"
        )
        for question_path in review_required_questions:
            st.write(f"- {calculator_question_display_name(question_path)}")

    updated_answers: dict[tuple[str, str], Any] = {}

    st.subheader("Core Hours")
    updated_answers[("core_hours", "day_worker_daily_limit_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="core_hours",
        question_name="day_worker_daily_limit_hours",
        label="What daily ordinary-hours limit applies to day workers?",
        widget_key=f"{editor_key}_core_day_daily",
    )
    updated_answers[("core_hours", "shift_worker_daily_limit_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="core_hours",
        question_name="shift_worker_daily_limit_hours",
        label="What daily ordinary-hours limit applies to shiftworkers?",
        widget_key=f"{editor_key}_core_shift_daily",
    )
    updated_answers[("core_hours", "day_worker_weekly_limit_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="core_hours",
        question_name="day_worker_weekly_limit_hours",
        label="What is the ordinary-hours weekly limit before overtime applies for day workers?",
        widget_key=f"{editor_key}_core_day_weekly",
    )
    updated_answers[("core_hours", "shift_worker_weekly_limit_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="core_hours",
        question_name="shift_worker_weekly_limit_hours",
        label="What is the ordinary-hours weekly limit before overtime applies for shift workers?",
        widget_key=f"{editor_key}_core_shift_weekly",
    )

    st.subheader("Overtime")
    st.caption(
        "If two-tier overtime applies on a listed day, the calculator uses the standard "
        "overtime rate up to the threshold and the extended overtime rate only after "
        "overtime hours are greater than the threshold. On those listed days, Saturday "
        "and Sunday overtime multipliers do not control overtime-rate selection, but "
        "weekend penalty logic remains separate."
    )
    updated_answers[("overtime", "standard_overtime_multiplier")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="overtime",
        question_name="standard_overtime_multiplier",
        label="What is the standard overtime multiplier? (Enter the total paid rate, for example 1.5 for 150%.)",
        widget_key=f"{editor_key}_ot_standard",
    )
    if calculator_question_exists(questionnaire_answers, "overtime", "casual_standard_overtime_multiplier"):
        updated_answers[("overtime", "casual_standard_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_standard_overtime_multiplier",
            label="What is the casual standard overtime multiplier? (Enter the total paid rate.)",
            widget_key=f"{editor_key}_ot_casual_standard",
        )
    updated_answers[("overtime", "has_two_tier_overtime")] = render_calculator_question_boolean(
        questionnaire_answers,
        section_name="overtime",
        question_name="has_two_tier_overtime",
        label="Is there a two-tier overtime structure? (Overtime hours are paid at different multipliers depending on how many overtime hours are worked.)",
        widget_key=f"{editor_key}_ot_two_tier",
    )
    updated_answers[("overtime", "extended_overtime_multiplier")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="overtime",
        question_name="extended_overtime_multiplier",
        label="If yes, what is the extended overtime multiplier? (Enter the total paid rate, for example 2.0 for 200%.)",
        widget_key=f"{editor_key}_ot_extended",
    )
    if calculator_question_exists(questionnaire_answers, "overtime", "casual_extended_overtime_multiplier"):
        updated_answers[("overtime", "casual_extended_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_extended_overtime_multiplier",
            label="What is the casual extended overtime multiplier? (Enter the total paid rate.)",
            widget_key=f"{editor_key}_ot_casual_extended",
        )
    updated_answers[("overtime", "higher_overtime_starts_after_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="overtime",
        question_name="higher_overtime_starts_after_hours",
        label="If yes, after how many overtime hours does it switch? (The extended rate starts only when overtime hours are greater than this threshold, not when they are equal to it.)",
        widget_key=f"{editor_key}_ot_threshold",
    )
    updated_answers[("overtime", "extended_overtime_days")] = render_extended_overtime_days_question(
        questionnaire_answers,
        widget_key=f"{editor_key}_ot_extended_days",
    )
    updated_answers[("overtime", "saturday_overtime_multiplier")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="overtime",
        question_name="saturday_overtime_multiplier",
        label="What overtime multiplier applies on Saturday? (Enter the total paid rate, for example 2.0 for 200%.)",
        widget_key=f"{editor_key}_ot_sat",
    )
    if calculator_question_exists(questionnaire_answers, "overtime", "casual_saturday_overtime_multiplier"):
        updated_answers[("overtime", "casual_saturday_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_saturday_overtime_multiplier",
            label="What casual overtime multiplier applies on Saturday?",
            widget_key=f"{editor_key}_ot_casual_sat",
        )
    updated_answers[("overtime", "sunday_overtime_multiplier")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="overtime",
        question_name="sunday_overtime_multiplier",
        label="What overtime multiplier applies on Sunday? (Enter the total paid rate, for example 2.0 for 200%.)",
        widget_key=f"{editor_key}_ot_sun",
    )
    if calculator_question_exists(questionnaire_answers, "overtime", "casual_sunday_overtime_multiplier"):
        updated_answers[("overtime", "casual_sunday_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_sunday_overtime_multiplier",
            label="What casual overtime multiplier applies on Sunday?",
            widget_key=f"{editor_key}_ot_casual_sun",
        )
    if calculator_question_exists(questionnaire_answers, "overtime", "public_holiday_overtime_multiplier"):
        updated_answers[("overtime", "public_holiday_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="public_holiday_overtime_multiplier",
            label="What non-casual overtime multiplier applies on a public holiday?",
            widget_key=f"{editor_key}_ot_public_holiday",
        )
        updated_answers[("overtime", "casual_public_holiday_overtime_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="overtime",
            question_name="casual_public_holiday_overtime_multiplier",
            label="What casual overtime multiplier applies on a public holiday?",
            widget_key=f"{editor_key}_ot_casual_public_holiday",
        )

    st.subheader("Span Overtime")
    st.caption(
        "The calculator supports a day-worker ordinary-span start and end."
    )
    updated_answers[("span", "day_workers_have_span_overtime")] = render_calculator_question_boolean(
        questionnaire_answers,
        section_name="span",
        question_name="day_workers_have_span_overtime",
        label="Does span overtime apply for day workers?",
        widget_key=f"{editor_key}_span_applies",
    )
    updated_answers[("span", "live_span_cutoff_hour")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="span",
        question_name="live_span_cutoff_hour",
        label="If yes, after what hour do day-worker hours become span overtime?",
        widget_key=f"{editor_key}_span_hour",
    )
    if calculator_question_exists(questionnaire_answers, "span", "live_span_start_hour"):
        updated_answers[("span", "live_span_start_hour")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="span",
            question_name="live_span_start_hour",
            label="Before what hour do day-worker hours become span overtime?",
            widget_key=f"{editor_key}_span_start_hour",
        )
    updated_answers[("span", "ordinary_span_summary")] = render_calculator_question_text(
        questionnaire_answers,
        section_name="span",
        question_name="ordinary_span_summary",
        label="Ordinary span summary",
        widget_key=f"{editor_key}_span_summary",
        height=100,
    )

    st.subheader("Penalties")
    st.caption("Penalty-related fields are split into day treatment and ordinary-hour penalties.")

    st.markdown("**Weekend Treatment**")
    weekend_options = ["overtime", "penalty", "not_applicable", "needs_review", ""]
    updated_answers[("weekend_treatment", "day_saturday_treatment")] = render_calculator_question_select(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="day_saturday_treatment",
        label="For day workers on Saturday, are hours overtime or penalty-based?",
        widget_key=f"{editor_key}_weekend_day_sat_treatment",
        options=weekend_options,
    )
    updated_answers[("weekend_treatment", "day_sunday_treatment")] = render_calculator_question_select(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="day_sunday_treatment",
        label="For day workers on Sunday, are hours overtime or penalty-based?",
        widget_key=f"{editor_key}_weekend_day_sun_treatment",
        options=weekend_options,
    )
    updated_answers[("weekend_treatment", "shift_saturday_treatment")] = render_calculator_question_select(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="shift_saturday_treatment",
        label="For shift workers on Saturday, are hours overtime or penalty-based?",
        widget_key=f"{editor_key}_weekend_shift_sat_treatment",
        options=weekend_options,
    )
    updated_answers[("weekend_treatment", "shift_sunday_treatment")] = render_calculator_question_select(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="shift_sunday_treatment",
        label="For shift workers on Sunday, are hours overtime or penalty-based?",
        widget_key=f"{editor_key}_weekend_shift_sun_treatment",
        options=weekend_options,
    )
    updated_answers[("weekend_treatment", "day_saturday_penalty_loading")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="day_saturday_penalty_loading",
        label="If day-worker Saturday hours are penalty-based, what is the loading above base?",
        widget_key=f"{editor_key}_weekend_day_sat_rate",
    )
    updated_answers[("weekend_treatment", "day_sunday_penalty_loading")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="day_sunday_penalty_loading",
        label="If day-worker Sunday hours are penalty-based, what is the loading above base?",
        widget_key=f"{editor_key}_weekend_day_sun_rate",
    )
    updated_answers[("weekend_treatment", "shift_saturday_penalty_loading")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="shift_saturday_penalty_loading",
        label="If shift-worker Saturday hours are penalty-based, what is the loading above base?",
        widget_key=f"{editor_key}_weekend_shift_sat_rate",
    )
    updated_answers[("weekend_treatment", "shift_sunday_penalty_loading")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="weekend_treatment",
        question_name="shift_sunday_penalty_loading",
        label="If shift-worker Sunday hours are penalty-based, what is the loading above base?",
        widget_key=f"{editor_key}_weekend_shift_sun_rate",
    )

    casual_day_treatment_questions = [
        (
            "casual_day_saturday_penalty_loading",
            "What casual day-worker loading applies on Saturday?",
        ),
        (
            "casual_day_sunday_penalty_loading",
            "What casual day-worker loading applies on Sunday?",
        ),
        (
            "casual_shift_saturday_penalty_loading",
            "What casual shift-worker loading applies on Saturday?",
        ),
        (
            "casual_shift_sunday_penalty_loading",
            "What casual shift-worker loading applies on Sunday?",
        ),
    ]
    for question_name, label in casual_day_treatment_questions:
        if calculator_question_exists(
            questionnaire_answers,
            "weekend_treatment",
            question_name,
        ):
            updated_answers[("weekend_treatment", question_name)] = render_calculator_question_number(
                questionnaire_answers,
                section_name="weekend_treatment",
                question_name=question_name,
                label=label,
                widget_key=f"{editor_key}_{question_name}",
            )

    if calculator_question_exists(
        questionnaire_answers,
        "weekend_treatment",
        "day_public_holiday_treatment",
    ):
        st.markdown("**Public Holiday Treatment**")
        updated_answers[("weekend_treatment", "day_public_holiday_treatment")] = render_calculator_question_select(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="day_public_holiday_treatment",
            label="For day workers on a public holiday, are hours overtime or penalty-based?",
            widget_key=f"{editor_key}_public_holiday_day_treatment",
            options=weekend_options,
        )
        updated_answers[("weekend_treatment", "shift_public_holiday_treatment")] = render_calculator_question_select(
            questionnaire_answers,
            section_name="weekend_treatment",
            question_name="shift_public_holiday_treatment",
            label="For shift workers on a public holiday, are hours overtime or penalty-based?",
            widget_key=f"{editor_key}_public_holiday_shift_treatment",
            options=weekend_options,
        )
        public_holiday_loading_questions = [
            ("day_public_holiday_penalty_loading", "Non-casual day-worker public-holiday loading above base"),
            ("shift_public_holiday_penalty_loading", "Non-casual shift-worker public-holiday loading above base"),
            ("casual_day_public_holiday_penalty_loading", "Casual day-worker public-holiday loading above base"),
            ("casual_shift_public_holiday_penalty_loading", "Casual shift-worker public-holiday loading above base"),
        ]
        for question_name, label in public_holiday_loading_questions:
            updated_answers[("weekend_treatment", question_name)] = render_calculator_question_number(
                questionnaire_answers,
                section_name="weekend_treatment",
                question_name=question_name,
                label=label,
                widget_key=f"{editor_key}_{question_name}",
            )

    st.subheader("Gap Between Shifts")
    updated_answers[("gap_between_shifts", "minimum_break_required")] = render_calculator_question_boolean(
        questionnaire_answers,
        section_name="gap_between_shifts",
        question_name="minimum_break_required",
        label="Is there a minimum break required between shifts?",
        widget_key=f"{editor_key}_gap_required",
    )
    updated_answers[("gap_between_shifts", "standard_minimum_break_hours")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="gap_between_shifts",
        question_name="standard_minimum_break_hours",
        label="If yes, what standard minimum break should be used as the live calculator threshold?",
        widget_key=f"{editor_key}_gap_hours",
    )
    updated_answers[("gap_between_shifts", "breach_penalty_multiplier")] = render_calculator_question_number(
        questionnaire_answers,
        section_name="gap_between_shifts",
        question_name="breach_penalty_multiplier",
        label="If the minimum break is breached, what penalty multiplier loading above base applies?",
        widget_key=f"{editor_key}_gap_penalty",
    )
    if calculator_question_exists(questionnaire_answers, "gap_between_shifts", "casual_breach_penalty_multiplier"):
        updated_answers[("gap_between_shifts", "casual_breach_penalty_multiplier")] = render_calculator_question_number(
            questionnaire_answers,
            section_name="gap_between_shifts",
            question_name="casual_breach_penalty_multiplier",
            label="If the minimum break is breached, what casual loading above base applies?",
            widget_key=f"{editor_key}_gap_casual_penalty",
        )
    updated_answers[("gap_between_shifts", "special_case_thresholds")] = render_calculator_question_json(
        questionnaire_answers,
        section_name="gap_between_shifts",
        question_name="special_case_thresholds",
        label="If different worker groups have different minimum breaks, record the special-case thresholds as JSON",
        widget_key=f"{editor_key}_gap_special_cases",
        height=160,
    )

    st.markdown("**Ordinary-Hour Penalties**")
    updated_answers[("weekday_penalties", "shift_based_penalties")] = render_calculator_penalty_rules_editor(
        questionnaire_answers,
        section_name="weekday_penalties",
        question_name="shift_based_penalties",
        label="Shift-based ordinary-hour penalties",
        widget_key_prefix=f"{editor_key}_weekday_shift_penalties",
    )
    updated_answers[("weekday_penalties", "time_based_penalties")] = render_calculator_penalty_rules_editor(
        questionnaire_answers,
        section_name="weekday_penalties",
        question_name="time_based_penalties",
        label="Time-based ordinary-hour penalties",
        widget_key_prefix=f"{editor_key}_weekday_time_penalties",
    )
    updated_answers[("weekday_penalties", "other_penalty_notes")] = render_calculator_question_text(
        questionnaire_answers,
        section_name="weekday_penalties",
        question_name="other_penalty_notes",
        label="Other ordinary-hour penalty notes",
        widget_key=f"{editor_key}_weekday_penalty_notes",
        height=120,
    )

    with st.expander("Raw questionnaire JSON", expanded=False):
        render_json_expander(
            "Parsed calculator questionnaire JSON",
            loaded_questionnaire,
            key_suffix=f"{panel_key}_{questionnaire_path.stem}",
        )

    save_column, rebuild_column = st.columns(2)
    with save_column:
        if st.button("Save questionnaire and rebuild Python", key=f"{editor_key}_save"):
            updated_questionnaire = json.loads(json.dumps(loaded_questionnaire))

            try:
                apply_calculator_questionnaire_answers(
                    updated_questionnaire,
                    updated_answers,
                )
            except ValueError as exc:
                st.error(
                    f"Questionnaire was not saved because one or more fields are invalid: {exc}"
                )
                return

            rebuild_calculator_python_from_questionnaire(
                award_code=award_code,
                questionnaire_data=updated_questionnaire,
                questionnaire_path=questionnaire_path,
                python_path=python_path,
                save_questionnaire=True,
            )

    with rebuild_column:
        if st.button("Rebuild Python from saved questionnaire", key=f"{editor_key}_rebuild"):
            rebuild_calculator_python_from_questionnaire(
                award_code=award_code,
                questionnaire_data=loaded_questionnaire,
                questionnaire_path=questionnaire_path,
                python_path=python_path,
                save_questionnaire=False,
            )


def rebuild_calculator_python_from_questionnaire(
    *,
    award_code: str,
    questionnaire_data: dict[str, Any],
    questionnaire_path: Path,
    python_path: Path,
    save_questionnaire: bool,
) -> None:
    creation_ruleset_paths = ruleset_artifact_paths_for_award(
        award_code,
        OVERTIME_CREATION_RULESET,
    )
    consequence_ruleset_paths = ruleset_artifact_paths_for_award(
        award_code,
        OVERTIME_CONSEQUENCE_RULESET,
    )
    penalties_ruleset_paths = ruleset_artifact_paths_for_award(
        award_code,
        PENALTIES_RULESET,
    )

    try:
        inputs = load_inputs(
            award_code=award_code,
            creation_json_path=creation_ruleset_paths.revised_json,
            consequence_json_path=consequence_ruleset_paths.revised_json,
            penalties_json_path=penalties_ruleset_paths.revised_json,
            output_path=python_path,
        )
        aligned_questionnaire_data = align_questionnaire_to_calculator_contract(
            questionnaire_data
        )
        normalized_data = normalize_response_data(
            aligned_questionnaire_data,
            award_code=award_code,
        )
    except Exception as exc:
        action = "saved" if save_questionnaire else "rebuilt"
        st.error(f"Calculator Python was not {action} because validation failed: {exc}")
        return

    if inputs.award_title is not None:
        normalized_data["award_title"] = inputs.award_title

    if save_questionnaire:
        write_text_file(
            questionnaire_path,
            json.dumps(aligned_questionnaire_data, indent=2),
        )

    write_python_output(python_path, normalized_data)

    if save_questionnaire:
        st.success(
            "Saved questionnaire JSON and rebuilt calculator Python from the edited responses."
        )
    else:
        st.success("Rebuilt calculator Python from the saved questionnaire JSON.")


def calculator_question_record(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
) -> dict[str, Any]:
    section = questionnaire_answers.get(section_name)
    if not isinstance(section, dict):
        raise ValueError(f"Missing questionnaire section: {section_name}")

    record = section.get(question_name)
    if not isinstance(record, dict):
        raise ValueError(f"Missing questionnaire answer: {section_name}.{question_name}")

    return record


def calculator_question_exists(
    questionnaire_answers: dict[str, Any],
    section_name: str,
    question_name: str,
) -> bool:
    """Return whether a saved questionnaire contains one question."""
    section = questionnaire_answers.get(section_name)
    return isinstance(section, dict) and isinstance(section.get(question_name), dict)


def render_calculator_question_metadata(record: dict[str, Any]) -> None:
    status = str(record.get("status") or "").strip() or "unknown"
    rule_ids = ", ".join(record.get("source_rule_ids", []))
    clauses = ", ".join(record.get("clause_references", []))
    reasoning_summary = str(record.get("reasoning_summary") or "").strip()
    special_case_notes = str(record.get("special_case_notes") or "").strip()

    st.markdown(calculator_question_status_message(status))

    metadata_parts = []
    if rule_ids:
        metadata_parts.append(f"Rule IDs: {rule_ids}")
    if clauses:
        metadata_parts.append(f"Clauses: {clauses}")
    st.caption(" | ".join(metadata_parts))

    if reasoning_summary:
        st.caption(f"Reasoning: {reasoning_summary}")
    if special_case_notes:
        if status == "not_applicable":
            note_label = "Why this field is not used"
        elif status in {"needs_review", "not_found", "defaulted"}:
            note_label = "Review context"
        else:
            note_label = "Rule qualification"
        st.info(f"**{note_label}:** {special_case_notes}")


def calculator_question_status_message(status: str) -> str:
    """Return a clear review status without implying unsupported numeric confidence."""
    normalized_status = status.strip().lower()

    if normalized_status == "derived":
        return ":green[**Status: Derived — supported by the reviewed rules.**]"
    if normalized_status == "not_applicable":
        return ":green[**Status: Not applicable — this field is not used for the selected calculator treatment.**]"
    if normalized_status == "defaulted":
        return ":orange[**Status: Defaulted — confirm this assumption.**]"
    if normalized_status == "needs_review":
        return ":orange[**Status: Needs review — do not treat this as a live calculator rule yet.**]"
    if normalized_status == "not_found":
        return ":red[**Status: Not found — enter or confirm a value before relying on this rule.**]"

    return ":red[**Status: Unknown — review this answer before relying on it.**]"


def calculator_warnings_from_python_text(python_text: str) -> list[str]:
    """Read the explicit review warnings placed at the top of generated Python."""
    warning_lines: list[str] = []
    reading_warnings = False
    warning_headers = {
        "# IMPORTANT: REVIEW REQUIRED BEFORE USING THIS CALCULATOR",
        "# MISSING_FROM_ANALYSIS: review these defaults before use",
        "# MISSING_FROM_ANALYSIS: rules generated using assumptions or defaults",
        "# RULES EXCLUDED FROM THE ANALYSIS",
        "# RULES BUILT WITH ASSUMPTIONS OR DEFAULTS",
    }

    for line in python_text.splitlines():
        if line in warning_headers:
            reading_warnings = True
            continue

        if reading_warnings and line.startswith("# - "):
            warning_lines.append(line.removeprefix("# - "))
            continue

        if reading_warnings and line.startswith(
            (
                "# The analysis did not fully supply",
                "# These rules were outside",
                "# These rules were analysed",
            )
        ):
            continue

        if reading_warnings and not line.strip():
            reading_warnings = False

    return warning_lines


def formatted_ruleset_warning_rule_text(warning: str) -> str:
    """Return the reviewed rule carried by a step 4.1 coverage warning."""
    prefix = (
        "Step 4.1 formatted output may have dropped this reviewed rule instead "
        "of only formatting it: "
    )
    if warning.startswith(prefix):
        return warning.removeprefix(prefix)
    return warning


def render_calculator_ruleset_validation_panel(
    award_code: str,
    calculator_python_path: Path,
) -> None:
    """Render the read-only Screen 13 calculator validity validation."""
    validation_json_path = calculator_rules_validation_json_path_for_award(award_code)
    validation_markdown_path = calculator_rules_validation_markdown_path_for_award(award_code)

    st.subheader("Validate calculator Python")
    st.caption(
        "This check reviews only the Screen 13 calculator Python for valid syntax, "
        "calculator-contract compliance, internal consistency and common-sense "
        "runtime behaviour. It does not assess award alignment or change any artifact."
    )

    if st.button(
        "Run calculator Python validation",
        key=f"validate_calculator_ruleset_{award_code}",
    ):
        try:
            configure_prompt_log(log_path_for_award(award_code))
            with st.spinner("Validating calculator Python..."):
                validate_calculator_python(
                    award_code=award_code,
                    calculator_python_path=calculator_python_path,
                    validation_json_path=validation_json_path,
                    validation_markdown_path=validation_markdown_path,
                )
            st.success("Calculator validation report created.")
        except CalculatorRulesetValidationError as exc:
            st.error(f"Calculator validation failed: {exc}")

    if not validation_json_path.exists():
        return

    validation_data = load_json_or_show_error(validation_json_path)
    if validation_data is None:
        return

    overall_status = str(validation_data.get("overall_status") or "unknown").lower()
    summary = str(validation_data.get("summary") or "").strip()
    if overall_status == "red":
        st.error(f"**Overall status: RED** — {summary}")
    elif overall_status == "amber":
        st.warning(f"**Overall status: AMBER** — {summary}")
    else:
        st.success(f"**Overall status: GREEN** — {summary}")

    findings = validation_data.get("findings", [])
    validation_markdown = read_text_file(validation_markdown_path)
    has_findings = isinstance(findings, list) and bool(findings)
    if has_findings or validation_markdown.exists:
        with st.expander("Validation findings and report", expanded=False):
            if isinstance(findings, list):
                for finding in findings:
                    if not isinstance(finding, dict):
                        continue
                    severity = str(finding.get("severity") or "amber").lower()
                    message = (
                        f"**{finding.get('calculator_item', 'Calculator item')}** — "
                        f"{finding.get('finding', '')}\n\n"
                        f"Recommendation: {finding.get('recommendation', '')}"
                    )
                    if severity == "red":
                        st.error(message)
                    elif severity == "amber":
                        st.warning(message)
                    else:
                        st.success(message)

            if validation_markdown.exists:
                st.markdown("#### Validation report Markdown")
                st.markdown(validation_markdown.text)


def calculator_questions_requiring_review(
    questionnaire_answers: dict[str, Any],
) -> list[str]:
    """Return questionnaire fields whose evidence status needs human attention."""
    review_required_statuses = {"defaulted", "needs_review", "not_found"}
    review_required_questions: list[str] = []

    for section_name, raw_section in questionnaire_answers.items():
        if not isinstance(raw_section, dict):
            continue

        for question_name, raw_record in raw_section.items():
            if not isinstance(raw_record, dict):
                continue

            status = str(raw_record.get("status") or "").strip().lower()
            if status in review_required_statuses:
                review_required_questions.append(f"{section_name}.{question_name}")

    return review_required_questions


def calculator_question_display_name(question_path: str) -> str:
    """Return an audit-friendly label for a questionnaire field path."""
    display_names = {
        "core_hours.day_worker_daily_limit_hours": "Daily ordinary-hours limit — day workers",
        "core_hours.shift_worker_daily_limit_hours": "Daily ordinary-hours limit — shiftworkers",
        "weekend_treatment.day_saturday_penalty_loading": (
            "Saturday ordinary-hours penalty loading — day workers"
        ),
        "weekend_treatment.day_sunday_penalty_loading": (
            "Sunday ordinary-hours penalty loading — day workers"
        ),
        "weekend_treatment.casual_day_saturday_penalty_loading": (
            "Saturday ordinary-hours penalty loading — casual day workers"
        ),
        "weekend_treatment.casual_day_sunday_penalty_loading": (
            "Sunday ordinary-hours penalty loading — casual day workers"
        ),
        "weekend_treatment.shift_public_holiday_treatment": (
            "Public-holiday treatment — shiftworkers"
        ),
        "weekend_treatment.shift_public_holiday_penalty_loading": (
            "Public-holiday ordinary-hours loading — shiftworkers"
        ),
        "gap_between_shifts.breach_penalty_multiplier": (
            "Gap-between-shifts loading — permanent employees"
        ),
        "gap_between_shifts.casual_breach_penalty_multiplier": (
            "Gap-between-shifts loading — casual employees"
        ),
        "weekday_penalties.shift_based_penalties": (
            "Whole-shift ordinary-hours penalties"
        ),
        "weekday_penalties.time_based_penalties": (
            "Time-window ordinary-hours penalties"
        ),
    }
    if question_path in display_names:
        return display_names[question_path]

    section_name, _, question_name = question_path.partition(".")
    readable_question = question_name.replace("_", " ").strip().capitalize()
    readable_section = section_name.replace("_", " ").strip().capitalize()
    return f"{readable_question} ({readable_section})"


def render_calculator_question_number(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key: str,
) -> str:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)
    answer = record.get("answer")
    default_value = "" if answer is None else str(answer)
    return st.text_input(label, value=default_value, key=widget_key).strip()


def render_calculator_question_text(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key: str,
    height: int,
) -> str:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)
    answer = record.get("answer")
    default_value = "" if answer is None else str(answer)
    return st.text_area(label, value=default_value, height=height, key=widget_key)


def render_calculator_question_boolean(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key: str,
) -> str:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)
    answer = record.get("answer")
    option_map = {
        True: "true",
        False: "false",
        None: "",
    }
    options = ["", "true", "false"]
    default_index = options.index(option_map.get(answer, ""))
    return st.selectbox(label, options, index=default_index, key=widget_key)


def render_calculator_question_select(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key: str,
    options: list[str],
) -> str:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)
    answer = record.get("answer")
    normalized_options = list(options)
    if answer not in normalized_options:
        normalized_options.append(answer or "")
    default_index = normalized_options.index(answer or "")
    return st.selectbox(label, normalized_options, index=default_index, key=widget_key)


def render_calculator_question_json(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key: str,
    height: int,
) -> str:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)
    answer = record.get("answer")
    default_value = json.dumps(answer, indent=2)
    return st.text_area(label, value=default_value, height=height, key=widget_key)


def render_extended_overtime_days_question(
    questionnaire_answers: dict[str, Any],
    *,
    widget_key: str,
) -> list[str]:
    """Render the three supported day scopes for extended overtime."""
    record = calculator_question_record(
        questionnaire_answers,
        section_name="overtime",
        question_name="extended_overtime_days",
    )
    render_calculator_question_metadata(record)

    day_scope_to_days = {
        "Weekday": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "Weekday and Saturday": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ],
        "Everyday": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
    }
    stored_days = record.get("answer")
    scopes = list(day_scope_to_days)
    selected_scope = next(
        (scope for scope, days in day_scope_to_days.items() if stored_days == days),
        "Weekday",
    )
    selected_scope = st.selectbox(
        "On which days does extended overtime apply?",
        scopes,
        index=scopes.index(selected_scope),
        key=widget_key,
    )
    return day_scope_to_days[selected_scope]


def render_calculator_penalty_rules_editor(
    questionnaire_answers: dict[str, Any],
    *,
    section_name: str,
    question_name: str,
    label: str,
    widget_key_prefix: str,
) -> list[dict[str, Any]]:
    record = calculator_question_record(
        questionnaire_answers,
        section_name=section_name,
        question_name=question_name,
    )
    render_calculator_question_metadata(record)

    st.markdown(label)

    raw_answer = record.get("answer")
    if not isinstance(raw_answer, list):
        raw_answer = []

    rules_state_key = f"{widget_key_prefix}_rules"
    source_signature_key = f"{widget_key_prefix}_source_signature"
    current_source_signature = json.dumps(raw_answer, sort_keys=True)

    if (
        rules_state_key not in st.session_state
        or st.session_state.get(source_signature_key) != current_source_signature
    ):
        st.session_state[rules_state_key] = [
            raw_rule for raw_rule in raw_answer if isinstance(raw_rule, dict)
        ]
        st.session_state[source_signature_key] = current_source_signature

    if st.button("Add penalty row", key=f"{widget_key_prefix}_add_rule"):
        st.session_state[rules_state_key].append(blank_calculator_penalty_rule())

    rules_to_render = st.session_state[rules_state_key]
    edited_rules: list[dict[str, Any]] = []

    if not rules_to_render:
        st.caption("No live penalty rows were derived for this question.")

    for rule_index, raw_rule in enumerate(rules_to_render, start=1):
        if not isinstance(raw_rule, dict):
            continue

        row_key = f"{widget_key_prefix}_{rule_index}"
        with st.container(border=True):
            title_column, action_column = st.columns([5, 1])
            with title_column:
                st.markdown(f"Rule {rule_index}")
            with action_column:
                if st.button("Delete", key=f"{row_key}_delete"):
                    st.session_state[rules_state_key].pop(rule_index - 1)
                    st.rerun()
            first_column, second_column, third_column = st.columns(3)
            with first_column:
                code_name = st.text_input(
                    "Code name",
                    value=str(raw_rule.get("code_name") or ""),
                    key=f"{row_key}_code_name",
                ).strip()
            with second_column:
                penalty_type = st.selectbox(
                    "Type",
                    ["shift_based", "time_based"],
                    index=["shift_based", "time_based"].index(
                        str(raw_rule.get("type") or "shift_based")
                    ),
                    key=f"{row_key}_type",
                )
            with third_column:
                basis_options = ["start", "end", "duration", "time"]
                raw_basis = str(raw_rule.get("basis") or "start")
                if raw_basis not in basis_options:
                    raw_basis = "start"
                basis = st.selectbox(
                    "Basis",
                    basis_options,
                    index=basis_options.index(raw_basis),
                    key=f"{row_key}_basis",
                )

            fourth_column, fifth_column, sixth_column = st.columns(3)
            with fourth_column:
                start_hour = st.number_input(
                    "Start hour",
                    value=float(raw_rule.get("start_hour") or 0),
                    step=0.5,
                    key=f"{row_key}_start_hour",
                )
            with fifth_column:
                end_hour = st.number_input(
                    "End hour",
                    value=float(raw_rule.get("end_hour") or 0),
                    step=0.5,
                    key=f"{row_key}_end_hour",
                )
            with sixth_column:
                rate = st.number_input(
                    "Rate",
                    value=float(raw_rule.get("rate") or 0),
                    step=0.01,
                    key=f"{row_key}_rate",
                )

            casual_rate_text = st.text_input(
                "Casual rate (leave blank when not derived)",
                value=(
                    ""
                    if raw_rule.get("casual_rate") is None
                    else str(raw_rule.get("casual_rate"))
                ),
                key=f"{row_key}_casual_rate",
            ).strip()
            casual_rate = None if not casual_rate_text else float(casual_rate_text)

            applies_to_options = ["day", "shift"]
            default_applies_to = [
                value
                for value in raw_rule.get("applies_to", [])
                if value in applies_to_options
            ]
            applies_to = st.multiselect(
                "Applies to",
                applies_to_options,
                default=default_applies_to,
                key=f"{row_key}_applies_to",
            )
            day_options = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            days = st.multiselect(
                "Applicable days",
                day_options,
                default=[
                    day_name
                    for day_name in raw_rule.get("days", [])
                    if day_name in day_options
                ],
                key=f"{row_key}_days",
            )
            description = st.text_input(
                "Description",
                value=str(raw_rule.get("description") or ""),
                key=f"{row_key}_description",
            ).strip()

            edited_rules.append(
                {
                    "code_name": code_name,
                    "type": penalty_type,
                    "basis": basis,
                    "start_hour": start_hour,
                    "end_hour": end_hour,
                    "rate": rate,
                    "casual_rate": casual_rate,
                    "description": description,
                    "applies_to": applies_to,
                    "days": days,
                }
            )

    return edited_rules


def blank_calculator_penalty_rule() -> dict[str, Any]:
    return {
        "code_name": "",
        "type": "shift_based",
        "basis": "start",
        "start_hour": 0.0,
        "end_hour": 0.0,
        "rate": 0.0,
        "casual_rate": None,
        "description": "",
        "applies_to": [],
        "days": [],
    }


def apply_calculator_questionnaire_answers(
    questionnaire_data: dict[str, Any],
    updated_answers: dict[tuple[str, str], Any],
) -> None:
    questionnaire_answers = questionnaire_data.get("questionnaire_answers")
    if not isinstance(questionnaire_answers, dict):
        raise ValueError("Questionnaire JSON is missing questionnaire_answers.")

    for (section_name, question_name), raw_value in updated_answers.items():
        record = calculator_question_record(
            questionnaire_answers,
            section_name=section_name,
            question_name=question_name,
        )
        record["answer"] = parse_calculator_question_value(raw_value)


def parse_calculator_question_value(raw_value: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value

    stripped_value = raw_value.strip()
    if stripped_value == "":
        return None
    if stripped_value == "true":
        return True
    if stripped_value == "false":
        return False
    if stripped_value.startswith("[") or stripped_value.startswith("{"):
        try:
            return json.loads(stripped_value)
        except json.JSONDecodeError as exc:
            raise ValueError(str(exc)) from exc

    try:
        if "." in stripped_value:
            return float(stripped_value)
        return int(stripped_value)
    except ValueError:
        return stripped_value


def calculator_python_editor_widget_key(panel_key: str, output_path: Path) -> str:
    return f"{panel_key}_calculator_python_editor_{output_path.stem}"


def calculator_questionnaire_editor_widget_key(panel_key: str, output_path: Path) -> str:
    return f"{panel_key}_calculator_questionnaire_editor_{output_path.stem}"


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

    lines = rendered_markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        if line[3:].strip() in VALIDATION_SECTION_TITLES.values():
            continue
        return "\n".join(lines[index:]).lstrip()

    return rendered_markdown


def candidate_clause_keys(clause_reference: str) -> list[str]:
    """Return progressively broader clause keys for review-screen matching."""
    candidates = [clause_reference]
    simplified = re.sub(
        r"(?:\([a-z0-9]+\))+$",
        "",
        clause_reference,
        flags=re.IGNORECASE,
    )
    if simplified not in candidates:
        candidates.append(simplified)

    dotted_parts = simplified.split(".")
    while len(dotted_parts) > 1:
        dotted_parts = dotted_parts[:-1]
        candidate = ".".join(dotted_parts)
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def load_clause_hover_index(source_clause_classification_file: str | None) -> dict[str, dict[str, str]]:
    """Load the step-2.2 clause-classification artifact into a clause lookup."""
    if not source_clause_classification_file:
        return {}

    path = Path(source_clause_classification_file)
    if not path.exists():
        return {}

    try:
        data = load_json_file(path)
    except Exception:
        return {}

    raw_clauses = data.get("clauses", [])
    if not isinstance(raw_clauses, list):
        return {}

    clause_index: dict[str, dict[str, str]] = {}
    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, dict):
            continue

        clause_number = str(raw_clause.get("clause_number") or "").strip()
        if not clause_number:
            continue

        clause_index[clause_number] = {
            "clause_number": clause_number,
            "classification": str(raw_clause.get("classification") or "").strip(),
            "explanation": str(raw_clause.get("explanation") or "").strip(),
            "clause_text": str(raw_clause.get("clause_text") or "").strip(),
        }

    return clause_index


def clause_hover_text(
    clause_reference: str,
    clause_index: dict[str, dict[str, str]],
) -> str | None:
    """Return hover text for one clause reference when available."""
    for candidate in candidate_clause_keys(clause_reference):
        clause_record = clause_index.get(candidate)
        if clause_record is None:
            continue

        parts = [f"Clause {clause_record['clause_number']}"]
        classification = clause_record.get("classification", "")
        if classification:
            parts.append(f"Classification: {classification}")
        explanation = clause_record.get("explanation", "")
        if explanation:
            parts.append(f"Explanation: {explanation}")
        clause_text = clause_record.get("clause_text", "")
        if clause_text:
            parts.append(clause_text)

        return "\n\n".join(parts).strip()

    return None


def html_title_attribute(text: str) -> str:
    """Escape text for use in an HTML title attribute."""
    return escape(text, quote=True).replace("\n", "&#10;")


def clause_references_in_text(text: str) -> list[str]:
    """Extract clause references from one review string in first-seen order."""
    references: list[str] = []

    for match in CLAUSE_REFERENCE_PATTERN.finditer(text):
        clause_reference = match.group(0)
        if clause_reference not in references:
            references.append(clause_reference)

    return references


def render_text_with_clause_hover(
    text: str,
    clause_index: dict[str, dict[str, str]],
    *,
    bullet_prefix: str | None = None,
) -> None:
    """Render one review line with hoverable clause references."""
    rendered_parts: list[str] = []
    last_index = 0

    for match in CLAUSE_REFERENCE_PATTERN.finditer(text):
        clause_reference = match.group(0)
        rendered_parts.append(escape(text[last_index:match.start()]))
        hover_text = clause_hover_text(clause_reference, clause_index)
        if hover_text:
            rendered_parts.append(
                f'<span title="{html_title_attribute(hover_text)}"><code>{escape(clause_reference)}</code></span>'
            )
        else:
            rendered_parts.append(f"<code>{escape(clause_reference)}</code>")
        last_index = match.end()

    rendered_parts.append(escape(text[last_index:]))
    rendered_html = "".join(rendered_parts)

    if bullet_prefix:
        rendered_html = f"{escape(bullet_prefix)} {rendered_html}"

    st.markdown(rendered_html, unsafe_allow_html=True)


def render_clause_reference_badges(
    clause_references: list[str],
    clause_index: dict[str, dict[str, str]],
) -> None:
    """Render hoverable clause-reference badges for one structured rule."""
    badge_html: list[str] = []

    for clause_reference in clause_references:
        hover_text = clause_hover_text(clause_reference, clause_index)
        base_style = (
            "display:inline-block;margin:0 0.35rem 0.35rem 0;padding:0.15rem 0.45rem;"
            "border:1px solid rgba(49, 51, 63, 0.2);border-radius:999px;"
        )
        if hover_text:
            badge_html.append(
                f'<span title="{html_title_attribute(hover_text)}" style="{base_style}"><code>'
                f"{escape(clause_reference)}</code></span>"
            )
        else:
            badge_html.append(
                f'<span style="{base_style}"><code>{escape(clause_reference)}</code></span>'
            )

    if badge_html:
        st.markdown("".join(badge_html), unsafe_allow_html=True)


def render_clause_source_details(
    clause_references: list[str],
    clause_index: dict[str, dict[str, str]],
    *,
    label_prefix: str,
) -> None:
    """Render explicit source-clause detail expanders for one warning or rule."""
    unique_references: list[str] = []
    for clause_reference in clause_references:
        if clause_reference not in unique_references:
            unique_references.append(clause_reference)

    for clause_reference in unique_references:
        hover_text = clause_hover_text(clause_reference, clause_index)
        if not hover_text:
            continue
        with st.expander(f"{label_prefix} {clause_reference}", expanded=False):
            st.text(hover_text)


def format_validation_warning_for_display(warning: str) -> str:
    """Normalize older warning text into the current reviewer-friendly wording."""
    coverage_loss_match = re.fullmatch(
        r"Original step 3\.4 clause (.+) was present before review but is not referenced after review\.",
        warning,
    )
    if coverage_loss_match:
        clause_number = coverage_loss_match.group(1)
        return (
            f"The earlier draft cited clause {clause_number}, but the final reviewed "
            "ruleset no longer cites it. Check whether that rule or clause reference "
            "was intentionally removed during the review phase."
        )

    direct_match = re.fullmatch(
        r"Shortlisted clause ([^ ]+) from step 3\.2 is not referenced by any step 3\.4 rule\.",
        warning,
    )
    if direct_match:
        clause_number = direct_match.group(1)
        return (
            f"Clause {clause_number} was shortlisted as potentially relevant to the selected ruleset, "
            "but no rule in this ruleset currently represents it."
        )

    pre_review_match = re.fullmatch(
        r"Clause (.+) was identified as relevant to (.+), but it is not present in the step 3\.4 ruleset\.",
        warning,
    )
    if pre_review_match:
        clause_number = pre_review_match.group(1)
        ruleset_subject_label = pre_review_match.group(2)
        return (
            f"Clause {clause_number} was identified as relevant to {ruleset_subject_label}, but it is "
            "not present in the draft ruleset before review."
        )

    merged_match = re.fullmatch(
        r"Shortlisted clause ([^ ]+) from step 3\.2 is not referenced by any merged expert-comparison rule\.",
        warning,
    )
    if merged_match:
        clause_number = merged_match.group(1)
        return (
            f"Clause {clause_number} was shortlisted as potentially relevant to the selected ruleset, "
            "and it is still not represented in the combined ruleset after expert comparison."
        )

    removed_rule_match = re.fullmatch(
        r"The review removed original rule '([^']+)' from the revised ruleset\. Original clause references: (.+)\.",
        warning,
    )
    if removed_rule_match:
        rule_id = removed_rule_match.group(1)
        clause_references = removed_rule_match.group(2)
        return (
            f"The review removed original rule `{rule_id}` from the revised ruleset. "
            f"It previously relied on clause references {clause_references}. Check whether "
            "that removal was intentional and whether any payroll coverage was lost."
        )

    rejected_new_rule_match = re.fullmatch(
        r"The review rejected evaluator-proposed new rule '([^']+)'\.",
        warning,
    )
    if rejected_new_rule_match:
        rule_id = rejected_new_rule_match.group(1)
        return (
            f"The review rejected evaluator-proposed new rule `{rule_id}`. Check whether "
            "the evaluator had identified missing coverage that should still be added manually."
        )

    return warning


def render_validation_warning_sections(validation_warnings: list[str]) -> None:
    """Render validation warnings in reviewer-friendly sections."""
    categorized_warnings = categorize_validation_warnings(validation_warnings)

    high_impact_warnings = categorized_warnings[HIGH_IMPACT_VALIDATION_SECTION]
    if high_impact_warnings:
        st.markdown(f"##### {VALIDATION_SECTION_TITLES[HIGH_IMPACT_VALIDATION_SECTION]}")
        for warning in high_impact_warnings:
            st.write(f"- {format_validation_warning_for_display(str(warning))}")

    review_note_warnings = categorized_warnings[REVIEW_NOTES_VALIDATION_SECTION]
    if review_note_warnings:
        with st.expander(
            VALIDATION_SECTION_TITLES[REVIEW_NOTES_VALIDATION_SECTION],
            expanded=False,
        ):
            for warning in review_note_warnings:
                st.write(f"- {format_validation_warning_for_display(str(warning))}")

    hidden_diagnostic_warnings = categorized_warnings[
        HIDDEN_DIAGNOSTIC_VALIDATION_SECTION
    ]
    if hidden_diagnostic_warnings:
        with st.expander(
            VALIDATION_SECTION_TITLES[HIDDEN_DIAGNOSTIC_VALIDATION_SECTION],
            expanded=False,
        ):
            for warning in hidden_diagnostic_warnings:
                st.write(f"- {format_validation_warning_for_display(str(warning))}")


def render_validation_warning_sections_with_hover(
    validation_warnings: list[str],
    clause_index: dict[str, dict[str, str]],
) -> None:
    """Render validation warnings with source-clause detail for the combined step-3.1 screen."""
    categorized_warnings = categorize_validation_warnings(validation_warnings)

    high_impact_warnings = categorized_warnings[HIGH_IMPACT_VALIDATION_SECTION]
    if high_impact_warnings:
        st.markdown(f"##### {VALIDATION_SECTION_TITLES[HIGH_IMPACT_VALIDATION_SECTION]}")
        for warning in high_impact_warnings:
            display_warning = format_validation_warning_for_display(str(warning))
            st.write(f"- {display_warning}")
            render_clause_source_details(
                clause_references_in_text(display_warning),
                clause_index,
                label_prefix="Source clause",
            )

    review_note_warnings = categorized_warnings[REVIEW_NOTES_VALIDATION_SECTION]
    if review_note_warnings:
        with st.expander(
            VALIDATION_SECTION_TITLES[REVIEW_NOTES_VALIDATION_SECTION],
            expanded=False,
        ):
            for warning in review_note_warnings:
                display_warning = format_validation_warning_for_display(str(warning))
                st.write(f"- {display_warning}")
                render_clause_source_details(
                    clause_references_in_text(display_warning),
                    clause_index,
                    label_prefix="Source clause",
                )

    hidden_diagnostic_warnings = categorized_warnings[
        HIDDEN_DIAGNOSTIC_VALIDATION_SECTION
    ]
    if hidden_diagnostic_warnings:
        with st.expander(
            VALIDATION_SECTION_TITLES[HIDDEN_DIAGNOSTIC_VALIDATION_SECTION],
            expanded=False,
        ):
            for warning in hidden_diagnostic_warnings:
                display_warning = format_validation_warning_for_display(str(warning))
                st.write(f"- {display_warning}")
                render_clause_source_details(
                    clause_references_in_text(display_warning),
                    clause_index,
                    label_prefix="Source clause",
                )


def render_overtime_rules_json(
    json_path: Path,
    *,
    source_markdown_path: Path | None = None,
    panel_key: str,
    enable_clause_hover: bool = False,
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
    clause_index = load_clause_hover_index(
        str(rules_data.get("source_clause_classification_file") or "")
    ) if enable_clause_hover else {}

    if rendered_markdown:
        st.markdown("#### Markdown view")
        st.markdown(rendered_markdown)

    if isinstance(validation_warnings, list) and validation_warnings:
        with st.expander("Validation notes", expanded=True):
            if enable_clause_hover:
                render_validation_warning_sections_with_hover(
                    [str(warning) for warning in validation_warnings],
                    clause_index,
                )
            else:
                render_validation_warning_sections(
                    [str(warning) for warning in validation_warnings]
                )

    if not isinstance(rules, list) or not rules:
        st.warning("No structured overtime rules were found in this JSON artifact.")
        render_json_expander(
            "Structured overtime rules JSON",
            rules_data,
            key_suffix=f"{panel_key}_{json_path}",
        )
        return

    with st.expander("Rule-by-rule breakdown", expanded=False):
        for rule in rules:
            if not isinstance(rule, dict):
                continue

            rule_id = str(rule.get("rule_id", ""))
            section_heading = str(rule.get("section_heading", ""))
            raw_clause_references = rule.get("clause_references", [])
            clause_references = [
                str(reference).strip()
                for reference in raw_clause_references
                if str(reference).strip()
            ] if isinstance(raw_clause_references, list) else []
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
                st.write("**Clause references:**")
                if enable_clause_hover:
                    render_clause_reference_badges(clause_references, clause_index)
                    render_clause_source_details(
                        clause_references,
                        clause_index,
                        label_prefix="Source clause",
                    )
                else:
                    st.write(", ".join(clause_references))
            st.markdown(rule.get("rule_markdown", ""))
            plain_text = str(rule.get("rule_plain_text", "")).strip()
            if plain_text:
                st.caption(plain_text)
            st.divider()

    render_json_expander(
        "Structured overtime rules JSON",
        rules_data,
        key_suffix=f"{panel_key}_{json_path}",
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
    ruleset_key: str,
) -> None:
    st.markdown(f"### {heading}")

    supports_ruleset_cycle = ruleset_key in RULESET_SEQUENCE
    if supports_ruleset_cycle:
        previous_column, next_column, subset_column, layout_column, button_column = st.columns(
            5
        )
    else:
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

    if supports_ruleset_cycle:
        with subset_column:
            next_ruleset = next_ruleset_key(ruleset_key)
            next_ruleset_label = RULESET_OPTIONS_BY_KEY[next_ruleset]
            if st.button(
                f"Next subset: {next_ruleset_label}",
                key=f"{panel_key}_ruleset_next",
                on_click=move_ruleset_selection,
                args=(next_ruleset,),
                use_container_width=True,
            ):
                pass

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
            refresh_panel(panel_key, heading, artifact_paths, ruleset_key)


def move_screen_selection(panel_key: str, direction: int) -> None:
    current_screen = st.session_state.get(panel_key, SCREEN_OPTIONS[0])
    current_index = SCREEN_OPTIONS.index(current_screen)

    if direction < 0:
        updated_index = previous_index(current_index, len(SCREEN_OPTIONS))
    else:
        updated_index = next_index(current_index, len(SCREEN_OPTIONS))

    st.session_state[panel_key] = SCREEN_OPTIONS[updated_index]
    sync_layout_widgets_from_state()


RULESET_OPTIONS_BY_KEY = {
    value: key for key, value in RULESET_OPTIONS.items()
}


def next_ruleset_key(current_ruleset_key: str) -> str:
    current_index = RULESET_SEQUENCE.index(current_ruleset_key)
    next_index_value = current_index + 1
    if next_index_value >= len(RULESET_SEQUENCE):
        return RULESET_SEQUENCE[0]
    return RULESET_SEQUENCE[next_index_value]


def move_ruleset_selection(next_ruleset_key_value: str) -> None:
    next_ruleset_label = RULESET_OPTIONS_BY_KEY[next_ruleset_key_value]
    st.session_state["step3_ruleset"] = next_ruleset_key_value
    st.session_state["step3_ruleset_label"] = next_ruleset_label


def expand_panel_to_single_view(panel_key: str) -> None:
    if st.session_state.get("layout_mode") == "Side by side":
        save_current_side_by_side_layout()

    st.session_state["screen_one"] = st.session_state[panel_key]
    st.session_state["screen_two"] = "None"
    st.session_state["layout_mode"] = "Single expanded"
    sync_layout_widgets_from_state()


def restore_side_by_side_view() -> None:
    current_screen = st.session_state.get("screen_one")

    if current_screen in SCREEN_OPTIONS:
        st.session_state["screen_one"] = current_screen
        st.session_state["screen_two"] = default_second_screen_for(current_screen)
    else:
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


def default_second_screen_for(screen_name: str) -> str:
    current_index = SCREEN_OPTIONS.index(screen_name)

    next_index_value = current_index + 1
    if next_index_value < len(SCREEN_OPTIONS):
        return SCREEN_OPTIONS[next_index_value]

    previous_index_value = current_index - 1
    if previous_index_value >= 0:
        return SCREEN_OPTIONS[previous_index_value]

    return SCREEN_ORIGINAL_OVERTIME


def refresh_panel(
    panel_key: str,
    screen_name: str,
    artifact_paths: Any,
    ruleset_key: str,
) -> None:
    if screen_name == SCREEN_HUMAN_REVIEW:
        ruleset_artifacts = ruleset_artifact_paths_for_award(
            award_code_for_artifact_paths(artifact_paths),
            ruleset_key,
        )
        editor_key = manual_ruleset_editor_widget_key(
            panel_key,
            ruleset_artifacts.manual_ruleset_markdown,
        )
        st.session_state.pop(editor_key, None)

    if screen_name == SCREEN_CALCULATOR_PYTHON:
        calculator_python_path = calculator_rules_python_path_for_award(
            award_code_for_artifact_paths(artifact_paths)
        )
        editor_key = calculator_python_editor_widget_key(
            panel_key,
            calculator_python_path,
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
        clear_pipeline_run_status(prefix)
        if not deleted_paths:
            st.info("No matching non-archive processed files were found.")
            return

        st.success(f"Deleted {len(deleted_paths)} processed files.")
        st.rerun()


def render_pipeline_run_controls(
    selected_award_code: str,
    controls_disabled: bool,
) -> None:
    st.header("Pipeline runs")
    st.caption(
        "Run controls live here, while the selector above controls which ruleset you are viewing."
    )
    current_status = normalized_status_for_award(selected_award_code)
    run_is_active = bool(
        current_status and current_status.get("state") in {"starting", "running"}
    )

    select_all_run_rulesets = st.checkbox(
        "Select all subsets",
        value=True,
        key="step3_run_select_all",
    )
    run_selection_disabled = controls_disabled or run_is_active or select_all_run_rulesets
    selected_run_labels = st.multiselect(
        "Step 3 subsets to run",
        list(STEP3_RUN_RULESET_OPTIONS),
        default=(
            list(STEP3_RUN_RULESET_OPTIONS)
            if select_all_run_rulesets
            else st.session_state.get(
                "step3_run_ruleset_labels",
                [next(iter(STEP3_RUN_RULESET_OPTIONS))],
            )
        ),
        key="step3_run_ruleset_labels",
        disabled=run_selection_disabled,
    )
    if select_all_run_rulesets:
        selected_run_labels = list(STEP3_RUN_RULESET_OPTIONS)
    selected_run_ruleset_keys = [
        STEP3_RUN_RULESET_OPTIONS[selected_run_label]
        for selected_run_label in selected_run_labels
    ]
    if not selected_run_ruleset_keys:
        st.warning("Select at least one Step 3 subset to run.")

    run_controls_disabled = controls_disabled or run_is_active
    if not selected_run_ruleset_keys:
        run_controls_disabled = True

    full_run_key = f"run_full_{selected_award_code}"
    if st.button(
        "Run active pipeline",
        key=full_run_key,
        use_container_width=True,
        disabled=run_controls_disabled,
    ):
        execute_pipeline_run(
            selected_award_code,
            step=None,
            ruleset_keys=selected_run_ruleset_keys,
        )

    step_one_column, step_two_column = st.columns(2, gap="small")
    step_three_column, step_three_b_column = st.columns(2, gap="small")
    step_four_column, step_five_b_column = st.columns(2, gap="small")

    with step_one_column:
        if st.button(
            f"1. {PIPELINE_STEP_LABELS['1']}",
            key=f"run_step_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="1")

    with step_two_column:
        if st.button(
            f"2.1. {PIPELINE_STEP_LABELS['2.1']}",
            key=f"run_step_2_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="2.1")

    with step_three_column:
        if st.button(
            f"2.2. {PIPELINE_STEP_LABELS['2.2']}",
            key=f"run_step_2_2_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(
                selected_award_code,
                step="2.2",
                ruleset_keys=selected_run_ruleset_keys,
            )

    with step_three_b_column:
        if st.button(
            f"3.1. {PIPELINE_STEP_LABELS['3.1']}",
            key=f"run_step_3_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(
                selected_award_code,
                step="3.1",
                ruleset_keys=selected_run_ruleset_keys,
            )

    with step_four_column:
        if st.button(
            f"3.2. {PIPELINE_STEP_LABELS['3.2']}",
            key=f"run_step_3_2_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(
                selected_award_code,
                step="3.2",
                ruleset_keys=selected_run_ruleset_keys,
            )

    with step_five_b_column:
        if st.button(
            f"4.1. {PIPELINE_STEP_LABELS['4.1']}",
            key=f"run_step_4_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(
                selected_award_code,
                step="4.1",
                ruleset_keys=selected_run_ruleset_keys,
            )

    extra_column_left, extra_column_right = st.columns(2, gap="small")

    with extra_column_left:
        if st.button(
            f"5.1. {PIPELINE_STEP_LABELS['5.1']}",
            key=f"run_step_5_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(
                selected_award_code,
                step="5.1",
                ruleset_keys=selected_run_ruleset_keys,
            )

    with extra_column_right:
        if st.button(
            f"6.1. {PIPELINE_STEP_LABELS['6.1']}",
            key=f"run_step_6_1_{selected_award_code}",
            use_container_width=True,
            disabled=run_controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="6.1")

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

    warnings = current_status.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        with st.expander("Pipeline warnings", expanded=True):
            for warning in warnings:
                st.write(f"- {warning}")

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
    ruleset_keys: list[str] | None = None,
) -> None:
    try:
        start_background_pipeline_run(
            selected_award_code,
            step,
            ruleset_keys=ruleset_keys,
        )
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
    """Load the step 5.1 validation summary when a step 5.1 run just completed."""
    if step != "5.1":
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
        "noted_rule_count": validation_data.get("noted_rule_count", 0),
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
    pipeline_warnings: list[str] = []

    try:
        with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
            if step is None:
                if source_record["source_type"] == SOURCE_TYPE_LOCAL_PDF:
                    run_pdf_step_1(paths, award_code, source_record)
                    for selected_step in ("2.1", "2.2", "3.1", "3.2"):
                        run_selected_step(paths, selected_step)
                else:
                    run_default_pipeline(paths)
            elif step == "1" and source_record["source_type"] == SOURCE_TYPE_LOCAL_PDF:
                run_pdf_step_1(paths, award_code, source_record)
            elif step == "4.1":
                summarize_overtime_entitlements(
                    interpretation_path=artifact_paths.revised_overtime_interpretation,
                    output_path=artifact_paths.overtime_entitlements,
                    validation_warnings_output=pipeline_warnings,
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
        "warnings": pipeline_warnings,
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
        unique_widget_key = json_expander_widget_key(
            label=label,
            rendered_json=rendered_json,
            key_suffix=key_suffix,
        )
        st.text_area(
            label,
            value=rendered_json,
            height=widget_height,
            disabled=True,
            key=unique_widget_key,
        )


def json_expander_widget_key(
    *,
    label: str,
    rendered_json: str,
    key_suffix: str = "",
) -> str:
    digest_source = f"{label}\n{key_suffix}\n{rendered_json}".encode("utf-8")
    rendered_digest = hashlib.sha1(digest_source).hexdigest()
    if key_suffix:
        return f"{label}_{key_suffix}_{rendered_digest}_json_view"

    return f"{label}_{rendered_digest}_json_view"


def bool_label(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def render_validation_summary(artifact_paths: Any) -> None:
    validation_data = load_optional_json_file(artifact_paths.core_overtime_validation_json)
    if validation_data is None:
        st.info("No step 5.1 validation report was found for this output yet.")
        return

    overall_status = str(validation_data.get("overall_status", "unknown"))
    passed_count = int(validation_data.get("passed_rule_count", 0))
    failed_count = int(validation_data.get("failed_rule_count", 0))
    noted_count = int(validation_data.get("noted_rule_count", 0))
    unresolved_count = int(validation_data.get("unresolved_rule_count", 0))

    if overall_status == "passed":
        st.success("Step 5.1 validation passed.")
    elif overall_status == "passed_with_notes":
        st.warning("Step 5.1 validation passed with documented exclusions.")
    elif overall_status == "unresolved":
        st.warning("Step 5.1 validation completed with unresolved coverage checks.")
    else:
        st.warning("Step 5.1 validation found coverage issues.")

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Passed rules", passed_count)
    metric_two.metric("Failed rules", failed_count)
    metric_three.metric("Documented exclusions", noted_count)
    metric_four.metric("Unresolved rules", unresolved_count)

    validation_report = read_text_file(artifact_paths.core_overtime_validation_markdown)
    if validation_report.exists:
        with st.expander("Step 5.1 validation report", expanded=False):
            st.markdown(validation_report.text)


def render_ruleset_validation_summary(ruleset_artifacts: Any) -> None:
    validation_data = load_optional_json_file(
        ruleset_artifacts.pseudocode_validation_json
    )
    if validation_data is None:
        st.info("No step 5.1 validation report was found for this output yet.")
        return

    overall_status = str(validation_data.get("overall_status", "unknown"))
    passed_count = int(validation_data.get("passed_rule_count", 0))
    failed_count = int(validation_data.get("failed_rule_count", 0))
    noted_count = int(validation_data.get("noted_rule_count", 0))
    unresolved_count = int(validation_data.get("unresolved_rule_count", 0))

    if overall_status == "passed":
        st.success("Step 5.1 validation passed.")
    elif overall_status == "passed_with_notes":
        st.warning("Step 5.1 validation passed with documented exclusions.")
    elif overall_status == "unresolved":
        st.warning("Step 5.1 validation completed with unresolved coverage checks.")
    else:
        st.warning("Step 5.1 validation found coverage issues.")

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Passed rules", passed_count)
    metric_two.metric("Failed rules", failed_count)
    metric_three.metric("Documented exclusions", noted_count)
    metric_four.metric("Unresolved rules", unresolved_count)

    validation_report = read_text_file(ruleset_artifacts.pseudocode_validation_markdown)
    if validation_report.exists:
        with st.expander("Step 5.1 validation report", expanded=False):
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
