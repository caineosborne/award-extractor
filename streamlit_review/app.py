import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from streamlit_review.output_data import (
    artifact_paths_for_award,
    clamp_index,
    discover_award_codes,
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
    read_text_file,
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

SCREEN_OPTIONS = [
    SCREEN_L1_PAYMENT,
    SCREEN_L2_PAYMENT,
    SCREEN_OVERTIME_CLASSIFICATION,
    SCREEN_ORIGINAL_OVERTIME,
    SCREEN_REVIEW_FEEDBACK,
    SCREEN_REVISED_OVERTIME,
    SCREEN_MANUAL_4B_EDITOR,
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


def main() -> None:
    st.set_page_config(
        page_title="Award Output Review",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Award Output Review")

    award_codes = discover_award_codes()
    if not award_codes:
        st.error("No payment classification outputs were found under data/processed.")
        return

    apply_review_styles()

    selected_award_code = render_sidebar(award_codes)
    artifact_paths = artifact_paths_for_award(selected_award_code)

    st.caption(f"Reviewing generated outputs for `{selected_award_code}`.")

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

        selected_award_code = st.selectbox(
            "Award code",
            award_codes,
            index=0,
            key="award_code",
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

    return selected_award_code


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
    }

    renderer = renderers[screen_name]
    renderer(artifact_paths, panel_key)


def render_l1_payment_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_L1_PAYMENT)
    render_file_caption(artifact_paths.payment_classification)

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
    render_panel_heading(SCREEN_L2_PAYMENT)
    render_file_caption(artifact_paths.payment_classification)

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
    render_panel_heading(SCREEN_OVERTIME_CLASSIFICATION)
    render_file_caption(artifact_paths.overtime_clause_classification)

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
    render_panel_heading(SCREEN_ORIGINAL_OVERTIME)
    render_markdown_file(artifact_paths.original_overtime_interpretation)


def render_review_feedback_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_REVIEW_FEEDBACK)

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
    render_panel_heading(SCREEN_REVISED_OVERTIME)
    render_markdown_file(artifact_paths.revised_overtime_interpretation)


def render_manual_4b_editor_screen(artifact_paths: Any, panel_key: str) -> None:
    render_panel_heading(SCREEN_MANUAL_4B_EDITOR)

    source_path = source_path_for_manual_4b_editor(artifact_paths)
    source_content = read_text_file(source_path)

    st.caption(
        "Editor source: "
        f"`{format_path_for_display(source_path)}`"
    )
    st.caption(
        "Save target: "
        f"`{format_path_for_display(artifact_paths.manual_4b_overtime_interpretation)}`"
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


def render_markdown_file(path: Path) -> None:
    render_file_caption(path)
    file_content = read_text_file(path)

    if not file_content.exists:
        render_missing_file(path)
        return

    st.markdown(file_content.text)


def render_missing_file(path: Path) -> None:
    st.warning(f"File not found: `{format_path_for_display(path)}`")


def render_file_caption(path: Path) -> None:
    st.caption(f"Source: `{format_path_for_display(path)}`")


def render_panel_heading(heading: str) -> None:
    st.markdown(f"### {heading}")


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
            margin-bottom: 0.25rem !important;
        }
        h3 {
            font-size: 1rem !important;
            margin-top: 0 !important;
            margin-bottom: 0.2rem !important;
        }
        h4 {
            font-size: 0.94rem !important;
            margin-top: 0.55rem !important;
            margin-bottom: 0.2rem !important;
        }
        p, li {
            font-size: 0.9rem;
            line-height: 1.35;
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
            font-size: 0.72rem;
            margin-bottom: 0.15rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.35rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.35rem;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
