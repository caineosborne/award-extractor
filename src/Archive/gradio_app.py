import os
from pathlib import Path

import gradio as gr

from src.Archive.award_interpreter import (
    DEFAULT_MODEL,
    DEFAULT_SECTIONS_PATH,
    AwardInterpreterError,
    interpret_clause,
    lookup_clause_text,
)


CSS = """
.gradio-container {
    height: 100vh !important;
    overflow: hidden !important;
}

.app-shell {
    height: calc(100vh - 32px);
    display: grid !important;
    grid-template-rows: minmax(150px, 25fr) minmax(140px, 25fr) minmax(260px, 50fr);
    gap: 12px;
    overflow: hidden;
}

.input-section,
.clause-section,
.response-section {
    min-height: 0;
    overflow-y: auto !important;
}

.input-section textarea,
.clause-section textarea {
    min-height: 0 !important;
    resize: none !important;
    overflow-y: auto !important;
}

.input-section textarea {
    height: 105px !important;
}

.clause-section textarea {
    height: 120px !important;
}

.response-section {
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    padding: 14px 18px;
    background: var(--background-fill-primary);
}

.response-section .prose {
    max-width: none !important;
}

.response-section pre {
    white-space: pre-wrap !important;
    overflow-x: auto;
}

.response-section h2:first-child {
    margin-top: 0;
}

#response-label {
    margin: 0 0 8px;
    color: var(--body-text-color-subdued);
    font-size: var(--text-md);
    font-weight: 600;
}

#response-output {
    height: calc(100% - 32px);
    overflow-y: auto !important;
}

.run-row {
    align-items: end;
}
"""


def run_interpretation(
    clause_reference: str,
    comments: str,
    sections_path: str,
    model: str,
) -> tuple[str, str]:
    if not clause_reference or not clause_reference.strip():
        return "", "Enter a clause reference."

    resolved_sections_path = Path(sections_path).expanduser() if sections_path else DEFAULT_SECTIONS_PATH
    selected_model = model.strip() or os.getenv("AWARD_INTERPRETER_MODEL", DEFAULT_MODEL)

    try:
        clause_text = lookup_clause_text(clause_reference, resolved_sections_path)
    except AwardInterpreterError as exc:
        return "", f"Lookup failed: {exc}"

    try:
        llm_response = interpret_clause(
            clause_reference=clause_reference,
            guidelines=comments,
            sections_path=resolved_sections_path,
            model=selected_model,
        )
    except AwardInterpreterError as exc:
        return clause_text, f"LLM request failed: {exc}"

    return clause_text, llm_response


with gr.Blocks(fill_height=True, title="Award Clause Interpreter") as demo:
    with gr.Column(elem_classes=["app-shell"]):
        with gr.Row(elem_classes=["run-row", "input-section"]):
            clause_input = gr.Textbox(
                label="Clause",
                placeholder="For example: 24.1",
                lines=4,
                max_lines=6,
            )
            comments_input = gr.Textbox(
                label="Additional comments",
                placeholder="Optional guidance for the interpretation",
                lines=4,
                max_lines=6,
            )
            run_button = gr.Button("Run", variant="primary")

        with gr.Group(elem_classes=["clause-section"]):
            clause_output = gr.Textbox(
                label="Clause text",
                lines=6,
                max_lines=8,
                interactive=False,
            )

        with gr.Group(elem_classes=["response-section"]):
            gr.Markdown("LLM response", elem_id="response-label", padding=False)
            response_output = gr.Markdown(
                "",
                elem_id="response-output",
                line_breaks=True,
                padding=False,
            )

        with gr.Accordion("Settings", open=False):
            sections_path_input = gr.Textbox(
                label="Sections JSON",
                value=str(DEFAULT_SECTIONS_PATH),
            )
            model_input = gr.Textbox(
                label="Model",
                value=os.getenv("AWARD_INTERPRETER_MODEL", DEFAULT_MODEL),
            )

    run_button.click(
        fn=run_interpretation,
        inputs=[clause_input, comments_input, sections_path_input, model_input],
        outputs=[clause_output, response_output],
    )


if __name__ == "__main__":
    demo.launch(css=CSS)
