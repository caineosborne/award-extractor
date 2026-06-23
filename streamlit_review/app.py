import json
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
from src.common.active_pipeline_paths import default_award_url_for_code, normalize_award_code
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
    source_path_for_core_overtime_pseudocode,
    source_path_for_manual_4b_editor,
    write_text_file_with_archive,
)


SCREEN_L1_PAYMENT = "1. L1 payment classification"
SCREEN_L2_PAYMENT = "2. L2 payment categories"
SCREEN_OVERTIME_CLASSIFICATION = "3. Overtime clause classification"
SCREEN_ORIGINAL_OVERTIME = "4. Original overtime extraction"
SCREEN_REVIEW_FEEDBACK = "5. Review feedback and commentary"
SCREEN_REVISED_OVERTIME = "6. Updated overtime extraction"
SCREEN_MANUAL_4B_EDITOR = "7. 4B manual overtime editor"
SCREEN_CORE_OVERTIME_PSEUDOCODE = "8. 5B core overtime pseudocode"

SCREEN_OPTIONS = [
    SCREEN_L1_PAYMENT,
    SCREEN_L2_PAYMENT,
    SCREEN_OVERTIME_CLASSIFICATION,
    SCREEN_ORIGINAL_OVERTIME,
    SCREEN_REVIEW_FEEDBACK,
    SCREEN_REVISED_OVERTIME,
    SCREEN_MANUAL_4B_EDITOR,
    SCREEN_CORE_OVERTIME_PSEUDOCODE,
]

COMPARISON_PRESETS = {
    "L2 categories + original extraction": (
        SCREEN_L2_PAYMENT,
        SCREEN_ORIGINAL_OVERTIME,
    ),
    "Original + updated extraction": (
        SCREEN_ORIGINAL_OVERTIME,
        SCREEN_REVISED_OVERTIME,
    ),
    "Overtime classification + original extraction": (
        SCREEN_OVERTIME_CLASSIFICATION,
        SCREEN_ORIGINAL_OVERTIME,
    ),
}

PIPELINE_STEP_LABELS = {
    "1": "Retrieve award",
    "2": "Classify clauses",
    "3": "Generate overtime",
    "3b": "Review overtime",
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
    validated_award_code, validation_error = validate_award_code_input(selected_award_code)

    if validation_error is not None:
        st.error(validation_error)
        return

    artifact_paths = artifact_paths_for_award(validated_award_code)

    st.caption(f"Reviewing generated outputs for `{validated_award_code}`.")

    screen_one = st.session_state["screen_one"]
    screen_two = st.session_state["screen_two"]
    layout_mode = st.session_state["layout_mode"]

    render_screens(
        screen_one=screen_one,
        screen_two=screen_two,
        layout_mode=layout_mode,
        artifact_paths=artifact_paths,
    )


def render_sidebar(award_codes: list[str]) -> str:
    with st.sidebar:
        st.header("Review controls")

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

        selected_award_code = st.session_state["award_code"].strip().upper()
        _, validation_error = validate_award_code_input(selected_award_code)
        if validation_error is not None:
            st.warning(validation_error)

        st.divider()
        render_pipeline_run_controls(
            selected_award_code=selected_award_code,
            controls_disabled=validation_error is not None,
        )

        st.divider()
        st.caption("Quick comparisons")

        for preset_label, screens in COMPARISON_PRESETS.items():
            if st.button(preset_label, use_container_width=True):
                st.session_state["screen_one"] = screens[0]
                st.session_state["screen_two"] = screens[1]
                st.session_state["layout_mode"] = "Side by side"

        st.caption("Single screen shortcuts")

        if st.button("Original overtime classification", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_ORIGINAL_OVERTIME
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"

        if st.button("Final overtime classification", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_REVISED_OVERTIME
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"

        if st.button("4B manual editor", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_MANUAL_4B_EDITOR
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"

        if st.button("5B core overtime pseudocode", use_container_width=True):
            st.session_state["screen_one"] = SCREEN_CORE_OVERTIME_PSEUDOCODE
            st.session_state["screen_two"] = "None"
            st.session_state["layout_mode"] = "Single expanded"

        st.divider()

        if "screen_one" not in st.session_state:
            st.session_state["screen_one"] = SCREEN_L2_PAYMENT
        if "screen_two" not in st.session_state:
            st.session_state["screen_two"] = SCREEN_ORIGINAL_OVERTIME
        if "layout_mode" not in st.session_state:
            st.session_state["layout_mode"] = "Side by side"

        st.selectbox("First screen", SCREEN_OPTIONS, key="screen_one")
        st.selectbox(
            "Second screen",
            ["None"] + SCREEN_OPTIONS,
            key="screen_two",
        )
        st.radio(
            "Layout",
            ["Side by side", "Single expanded"],
            horizontal=False,
            key="layout_mode",
        )

        st.divider()
        render_processed_file_cleanup_controls()

    return selected_award_code


def available_award_code_index(award_codes: list[str], selected_award_code: str) -> int:
    normalized_award_code = selected_award_code.strip().upper()

    if normalized_award_code in award_codes:
        return award_codes.index(normalized_award_code)

    return 0


def copy_available_award_code_to_input() -> None:
    st.session_state["award_code"] = st.session_state["available_award_code"]


def validate_award_code_input(value: str) -> tuple[str | None, str | None]:
    selected_award_code = value.strip().upper()
    if not selected_award_code:
        return None, "Enter an award code to review or run."

    try:
        normalized_award_code = normalize_award_code(selected_award_code)
    except ValueError:
        return None, "Award code must look like `MA000002`."

    return normalized_award_code, None


def render_screens(
    screen_one: str,
    screen_two: str,
    layout_mode: str,
    artifact_paths: Any,
) -> None:
    if layout_mode == "Single expanded" or screen_two == "None":
        with st.container(height=790, border=True):
            render_screen(screen_one, artifact_paths, panel_key="screen_one")
        return

    left_column, right_column = st.columns(2, gap="medium")

    with left_column:
        with st.container(height=790, border=True):
            render_screen(screen_one, artifact_paths, panel_key="screen_one")

    with right_column:
        with st.container(height=790, border=True):
            render_screen(screen_two, artifact_paths, panel_key="screen_two")


def render_screen(screen_name: str, artifact_paths: Any, panel_key: str) -> None:
    renderers: dict[str, Callable[[Any, str], None]] = {
        SCREEN_L1_PAYMENT: render_l1_payment_screen,
        SCREEN_L2_PAYMENT: render_l2_payment_screen,
        SCREEN_OVERTIME_CLASSIFICATION: render_overtime_classification_screen,
        SCREEN_ORIGINAL_OVERTIME: render_original_overtime_screen,
        SCREEN_REVIEW_FEEDBACK: render_review_feedback_screen,
        SCREEN_REVISED_OVERTIME: render_revised_overtime_screen,
        SCREEN_MANUAL_4B_EDITOR: render_manual_4b_editor_screen,
        SCREEN_CORE_OVERTIME_PSEUDOCODE: render_core_overtime_pseudocode_screen,
    }

    renderer = renderers[screen_name]
    renderer(artifact_paths, panel_key)


def render_l1_payment_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_L1_PAYMENT, panel_key, artifact_paths)
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
    render_json_expander("Selected L1 JSON", record)


def render_l2_payment_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_L2_PAYMENT, panel_key, artifact_paths)
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
    render_json_expander("Selected L2 JSON", record)


def render_overtime_classification_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_OVERTIME_CLASSIFICATION, panel_key, artifact_paths)
    render_file_details(artifact_paths.overtime_clause_classification)

    overtime_classification = load_json_or_show_error(
        artifact_paths.overtime_clause_classification
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
    render_json_expander("Selected overtime classification JSON", record)


def overtime_clause_text_widget_key(panel_key: str, selected_clause_key: str) -> str:
    return f"{panel_key}_overtime_clause_text_{selected_clause_key}"


def render_original_overtime_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_ORIGINAL_OVERTIME, panel_key, artifact_paths)
    render_markdown_file(artifact_paths.original_overtime_interpretation)


def render_review_feedback_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_REVIEW_FEEDBACK, panel_key, artifact_paths)

    if artifact_paths.agentic_review_conversation.exists():
        st.markdown("#### Agentic review conversation")
        render_markdown_file(artifact_paths.agentic_review_conversation)

        has_legacy_feedback = artifact_paths.evaluator_feedback.exists()
        has_legacy_creator_response = artifact_paths.creator_response.exists()
        if has_legacy_feedback or has_legacy_creator_response:
            st.divider()

        if has_legacy_feedback:
            st.markdown("#### Legacy evaluator feedback")
            render_markdown_file(artifact_paths.evaluator_feedback)

        if has_legacy_feedback and has_legacy_creator_response:
            st.divider()

        if has_legacy_creator_response:
            st.markdown("#### Legacy creator commentary")
            render_markdown_file(artifact_paths.creator_response)
        return

    st.markdown("#### Agentic review conversation")
    render_markdown_file(artifact_paths.agentic_review_conversation)

    st.divider()

    st.markdown("#### Evaluator feedback")
    render_markdown_file(artifact_paths.evaluator_feedback)

    st.divider()

    st.markdown("#### Creator commentary")
    render_markdown_file(artifact_paths.creator_response)


def render_revised_overtime_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_REVISED_OVERTIME, panel_key, artifact_paths)
    render_markdown_file(artifact_paths.revised_overtime_interpretation)


def render_manual_4b_editor_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_MANUAL_4B_EDITOR, panel_key, artifact_paths)

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
        "4B overtime interpretation markdown",
        value=source_content.text,
        height=610,
        label_visibility="collapsed",
        key=editor_key,
    )

    if st.button("Save updated version", key=f"{editor_key}_save"):
        if not edited_markdown.strip():
            st.error("The edited overtime interpretation is empty. Nothing was saved.")
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


def render_core_overtime_pseudocode_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_CORE_OVERTIME_PSEUDOCODE, panel_key, artifact_paths)
    render_markdown_file(
        artifact_paths.core_overtime_pseudocode,
        source_path=source_path_for_core_overtime_pseudocode(artifact_paths),
    )


def manual_4b_editor_widget_key(panel_key: str, output_path: Path) -> str:
    return f"{panel_key}_manual_4b_editor_{output_path.stem}"


def render_key_navigation(
    label: str,
    keys: list[str],
    state_key: str,
) -> str | None:
    if not keys:
        return None

    current_index = clamp_index(st.session_state.get(state_key, 0), len(keys))
    st.session_state[state_key] = current_index

    previous_column, selector_column, next_column = st.columns([1, 3, 1])

    with previous_column:
        st.button(
            "Previous",
            key=f"{state_key}_previous",
            on_click=move_selected_index,
            args=(state_key, len(keys), -1),
            use_container_width=True,
        )

    with selector_column:
        selected_key = st.selectbox(
            f"{label} selector for {state_key}",
            keys,
            index=current_index,
            label_visibility="collapsed",
        )
        st.session_state[state_key] = keys.index(selected_key)

    with next_column:
        st.button(
            "Next",
            key=f"{state_key}_next",
            on_click=move_selected_index,
            args=(state_key, len(keys), 1),
            use_container_width=True,
        )

    return keys[st.session_state[state_key]]


def move_selected_index(
    state_key: str,
    item_count: int,
    direction: int,
) -> None:
    if item_count == 0:
        return

    current_index = clamp_index(st.session_state.get(state_key, 0), item_count)

    if direction < 0:
        updated_index = previous_index(current_index, item_count)
    else:
        updated_index = next_index(current_index, item_count)

    st.session_state[state_key] = updated_index


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


def render_panel_heading(heading: str, panel_key: str, artifact_paths: Any) -> None:
    heading_column, button_column = st.columns([5, 1])

    with heading_column:
        st.markdown(f"### {heading}")

    with button_column:
        st.markdown('<div class="review-refresh-button">', unsafe_allow_html=True)
        if st.button("Refresh", key=f"{panel_key}_refresh", use_container_width=True):
            refresh_panel(panel_key, heading, artifact_paths)
        st.markdown("</div>", unsafe_allow_html=True)


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
) -> None:
    st.header("Pipeline runs")
    st.caption(
        "Runs the existing pipeline for the selected award code using the same workflow as `src/award_pipeline.py`."
    )

    full_run_key = f"run_full_{selected_award_code}"
    if st.button(
        "Run full pipeline",
        key=full_run_key,
        use_container_width=True,
        disabled=controls_disabled,
    ):
        execute_pipeline_run(selected_award_code, step=None)

    step_one_column, step_two_column = st.columns(2, gap="small")
    step_three_column, step_three_b_column = st.columns(2, gap="small")
    step_five_b_column, _ = st.columns(2, gap="small")

    with step_one_column:
        if st.button(
            PIPELINE_STEP_LABELS["1"],
            key=f"run_step_1_{selected_award_code}",
            use_container_width=True,
            disabled=controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="1")

    with step_two_column:
        if st.button(
            PIPELINE_STEP_LABELS["2"],
            key=f"run_step_2_{selected_award_code}",
            use_container_width=True,
            disabled=controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="2")

    with step_three_column:
        if st.button(
            PIPELINE_STEP_LABELS["3"],
            key=f"run_step_3_{selected_award_code}",
            use_container_width=True,
            disabled=controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="3")

    with step_three_b_column:
        if st.button(
            PIPELINE_STEP_LABELS["3b"],
            key=f"run_step_3b_{selected_award_code}",
            use_container_width=True,
            disabled=controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="3b")

    with step_five_b_column:
        if st.button(
            PIPELINE_STEP_LABELS["5b"],
            key=f"run_step_5b_{selected_award_code}",
            use_container_width=True,
            disabled=controls_disabled,
        ):
            execute_pipeline_run(selected_award_code, step="5b")

    status_message = st.session_state.get("pipeline_run_status_message")
    status_kind = st.session_state.get("pipeline_run_status_kind")
    status_award_code = st.session_state.get("pipeline_run_award_code")
    status_log = st.session_state.get("pipeline_run_log")

    if status_award_code != selected_award_code:
        return

    if status_kind == "success" and status_message:
        st.success(status_message)
    elif status_kind == "error" and status_message:
        st.error(status_message)

    if status_log:
        with st.expander("Pipeline run log", expanded=False):
            st.code(status_log, language="text")


def execute_pipeline_run(selected_award_code: str, step: str | None) -> None:
    run_label = pipeline_run_label(step)

    with st.spinner(f"{run_label} for {selected_award_code}..."):
        run_result = run_pipeline_for_award(selected_award_code, step)

    st.session_state["pipeline_run_award_code"] = selected_award_code
    st.session_state["pipeline_run_log"] = run_result["log"]

    if run_result["success"]:
        st.session_state["pipeline_run_status_kind"] = "success"
        st.session_state["pipeline_run_status_message"] = (
            f"{run_label} completed for {selected_award_code} in {run_result['duration_seconds']:.1f}s."
        )
    else:
        st.session_state["pipeline_run_status_kind"] = "error"
        st.session_state["pipeline_run_status_message"] = (
            f"{run_label} failed for {selected_award_code}."
        )

    st.rerun()


def pipeline_run_label(step: str | None) -> str:
    if step is None:
        return "Full pipeline run"

    return PIPELINE_STEP_LABELS[step]


def run_pipeline_for_award(award_code: str, step: str | None) -> dict[str, Any]:
    url = default_award_url_for_code(award_code)
    paths = build_paths(award_code, suffix=None, url=url)
    output_buffer = StringIO()
    error_buffer = StringIO()
    started_at = time.perf_counter()

    try:
        with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
            if step is None:
                run_default_pipeline(paths)
            else:
                run_selected_step(paths, step)
    except Exception as exc:
        traceback.print_exc(file=error_buffer)
        combined_log = combine_pipeline_logs(output_buffer.getvalue(), error_buffer.getvalue())
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
    }


def combine_pipeline_logs(stdout_text: str, stderr_text: str) -> str:
    sections: list[str] = []

    if stdout_text.strip():
        sections.append(stdout_text.strip())

    if stderr_text.strip():
        sections.append(stderr_text.strip())

    return "\n\n".join(sections)


def render_json_expander(label: str, value: dict[str, Any]) -> None:
    with st.expander(label, expanded=False):
        st.code(json.dumps(value, indent=2, ensure_ascii=False), language="json")


def bool_label(value: Any) -> str:
    return "Yes" if bool(value) else "No"


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
