from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from src.award_pipeline import (
    AwardPipelineError,
    build_paths,
    run_default_pipeline,
    run_selected_step,
)
from src.common.active_pipeline_paths import (
    creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation,
    revised_output_path_for_interpretation,
    ruleset_clause_classification_output_path_for_classification,
    ruleset_output_path_for_classification,
)
from src.common.award_sources import (
    SOURCE_TYPE_FAIR_WORK_HTML,
    SOURCE_TYPE_LOCAL_PDF,
    source_record_for_award,
)
from src.common.overtime_rulesets import overtime_ruleset_config
from src.step_3_1_generate_ruleset.run import (
    generate_ruleset_from_clause_classification as generate_overtime_ruleset,
)
from src.step_3_2_review_ruleset.run import review_ruleset as review_overtime_interpretation
from src.step_1_2_parse_award.run import (
    extract_pdf_award_source as extract_pdf_to_award,
    write_pdf_step_outputs as write_pdf_outputs,
)
from src.step_4_1_format_ruleset.run import summarize_overtime_entitlements
from src.step_5_1_generate_pseudocode.run import generate_core_overtime_pseudocode
from streamlit_review.output_data import (
    artifact_paths_for_award,
    load_json_file,
    ruleset_artifact_paths_for_award,
    source_path_for_ruleset_core_overtime_pseudocode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_RUN_DIR = PROJECT_ROOT / "data" / "processed" / "_streamlit_pipeline_runs"

PIPELINE_STEP_LABELS = {
    "1": "Retrieve award",
    "2.1": "Classify clauses",
    "2.2": "Classify overtime clauses",
    "3.1": "Generate overtime ruleset",
    "3.2": "Review overtime ruleset",
    "4.1": "Format overtime guide",
    "5.1": "Generate pseudocode",
}


@dataclass(frozen=True)
class PipelinePlannedStep:
    step_id: str
    label: str
    runner_kind: str


class LiveLogWriter:
    """Write captured output to both a memory buffer and the persisted run log."""

    def __init__(self, log_path: Path, buffer: StringIO):
        self.log_path = log_path
        self.buffer = buffer
        self.log_file = log_path.open("a", encoding="utf-8")

    def write(self, text: str) -> int:
        self.buffer.write(text)
        self.log_file.write(text)
        self.log_file.flush()
        return len(text)

    def flush(self) -> None:
        self.log_file.flush()

    def close(self) -> None:
        self.log_file.close()


def pipeline_run_label(step: str | None, ruleset_key: str | None = None) -> str:
    """Return the human-readable label for one pipeline run."""
    if ruleset_key:
        ruleset_name = overtime_ruleset_config(ruleset_key).display_name.lower()
        if step is None:
            return f"{ruleset_name} pipeline run"
        if step == "3.1":
            return f"Generate {ruleset_name} ruleset"
        if step == "3.2":
            return f"Review {ruleset_name} ruleset"
        if step == "4.1":
            return f"Format {ruleset_name} ruleset"
        if step == "5.1":
            return f"Generate {ruleset_name} pseudocode"
    if step is None:
        return "Active pipeline run"

    return PIPELINE_STEP_LABELS[step]


def ensure_pipeline_run_dir() -> Path:
    """Create the status directory when needed."""
    PIPELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    return PIPELINE_RUN_DIR


def status_path_for_award(award_code: str) -> Path:
    """Return the status JSON path for one award code."""
    return ensure_pipeline_run_dir() / f"{award_code}_status.json"


def log_path_for_award(award_code: str) -> Path:
    """Return the text log path for one award code."""
    return ensure_pipeline_run_dir() / f"{award_code}.log"


def write_status(status: dict[str, Any]) -> None:
    """Write one status record atomically."""
    status_path = status_path_for_award(str(status["award_code"]))
    temporary_path = status_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    temporary_path.replace(status_path)


def read_status(award_code: str) -> dict[str, Any] | None:
    """Read the latest status record for one award code."""
    status_path = status_path_for_award(award_code)
    if not status_path.exists():
        return None

    return load_json_file(status_path)


def process_is_running(pid: int) -> bool:
    """Return True when the stored process id still exists."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    return True


def normalized_status_for_award(award_code: str) -> dict[str, Any] | None:
    """Return the latest run status and mark stale runs as errors."""
    status = read_status(award_code)
    if status is None:
        return None

    state = str(status.get("state", "unknown"))
    pid = status.get("pid")

    if state == "running" and isinstance(pid, int) and not process_is_running(pid):
        finished_at = time.time()
        status["state"] = "error"
        status["message"] = "Background run stopped before it wrote a final status."
        status["finished_at"] = finished_at
        started_at = status.get("started_at")
        if isinstance(started_at, (int, float)):
            status["duration_seconds"] = finished_at - started_at
        write_status(status)

    return status


def combine_pipeline_logs(stdout_text: str, stderr_text: str) -> str:
    """Merge stdout and stderr into one readable log."""
    sections: list[str] = []

    if stdout_text.strip():
        sections.append(stdout_text.strip())

    if stderr_text.strip():
        sections.append(stderr_text.strip())

    return "\n\n".join(sections)


def progress_value(completed_steps: int, total_steps: int) -> float:
    """Return the persisted progress fraction for one run."""
    if total_steps <= 0:
        return 0.0

    return min(max(completed_steps / total_steps, 0.0), 1.0)


def pipeline_steps_for_run(source_type: str, step: str | None) -> list[PipelinePlannedStep]:
    """Return the planned execution steps for one requested run."""
    if step is None:
        if source_type == SOURCE_TYPE_LOCAL_PDF:
            return [
                PipelinePlannedStep("1", PIPELINE_STEP_LABELS["1"], "pdf_step_1"),
                PipelinePlannedStep("2.1", PIPELINE_STEP_LABELS["2.1"], "selected_step"),
                PipelinePlannedStep("2.2", PIPELINE_STEP_LABELS["2.2"], "selected_step"),
                PipelinePlannedStep("3.1", PIPELINE_STEP_LABELS["3.1"], "selected_step"),
                PipelinePlannedStep("3.2", PIPELINE_STEP_LABELS["3.2"], "selected_step"),
                PipelinePlannedStep("4.1", PIPELINE_STEP_LABELS["4.1"], "formatter_step"),
                PipelinePlannedStep("5.1", PIPELINE_STEP_LABELS["5.1"], "selected_step"),
            ]

        return [
            PipelinePlannedStep("1", PIPELINE_STEP_LABELS["1"], "selected_step"),
            PipelinePlannedStep("2.1", PIPELINE_STEP_LABELS["2.1"], "selected_step"),
            PipelinePlannedStep("2.2", PIPELINE_STEP_LABELS["2.2"], "selected_step"),
            PipelinePlannedStep("3.1", PIPELINE_STEP_LABELS["3.1"], "selected_step"),
            PipelinePlannedStep("3.2", PIPELINE_STEP_LABELS["3.2"], "selected_step"),
            PipelinePlannedStep("4.1", PIPELINE_STEP_LABELS["4.1"], "formatter_step"),
            PipelinePlannedStep("5.1", PIPELINE_STEP_LABELS["5.1"], "selected_step"),
        ]

    if step == "1" and source_type == SOURCE_TYPE_LOCAL_PDF:
        return [PipelinePlannedStep("1", PIPELINE_STEP_LABELS["1"], "pdf_step_1")]

    if step == "4.1":
        return [PipelinePlannedStep("4.1", PIPELINE_STEP_LABELS["4.1"], "formatter_step")]

    return [PipelinePlannedStep(step, PIPELINE_STEP_LABELS[step], "selected_step")]


def load_5b_validation_summary(paths: Any, step: str | None) -> dict[str, Any] | None:
    """Load the step 5B validation summary when available."""
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
        "unresolved_rule_count": validation_data.get("unresolved_rule_count", 0),
    }


def run_pipeline_for_award(
    award_code: str,
    step: str | None,
    *,
    ruleset_key: str | None = None,
    status_callback: Any | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Run one pipeline step or the default flow and capture its outputs."""
    source_record = source_record_for_award(award_code)
    if source_record["source_type"] == SOURCE_TYPE_FAIR_WORK_HTML:
        url = str(source_record["source_url"])
    else:
        url = ""
    paths = build_paths(award_code, suffix=None, url=url)
    artifact_paths = artifact_paths_for_award(award_code)
    planned_steps = pipeline_steps_for_run(str(source_record["source_type"]), step)
    output_buffer = StringIO()
    error_buffer = StringIO()
    started_at = time.perf_counter()
    active_step: PipelinePlannedStep | None = None

    output_writer: Any = output_buffer
    error_writer: Any = error_buffer
    live_output_writer: LiveLogWriter | None = None
    live_error_writer: LiveLogWriter | None = None

    if log_path is not None:
        live_output_writer = LiveLogWriter(log_path, output_buffer)
        live_error_writer = LiveLogWriter(log_path, error_buffer)
        output_writer = live_output_writer
        error_writer = live_error_writer

    try:
        with redirect_stdout(output_writer), redirect_stderr(error_writer):
            for step_index, planned_step in enumerate(planned_steps, start=1):
                active_step = planned_step

                if status_callback is not None:
                    status_callback(
                        {
                            "completed_steps": step_index - 1,
                            "total_steps": len(planned_steps),
                            "progress_fraction": progress_value(
                                step_index - 1,
                                len(planned_steps),
                            ),
                            "current_step": planned_step.step_id,
                            "current_step_label": planned_step.label,
                            "message": (
                                f"Step {step_index} of {len(planned_steps)}: "
                                f"{planned_step.label} for {award_code}."
                            ),
                        }
                    )

                print(
                    f"Starting step {step_index} of {len(planned_steps)}: "
                    f"{planned_step.label}"
                )

                if planned_step.runner_kind == "pdf_step_1":
                    run_pdf_step_1(paths, award_code, source_record)
                elif planned_step.runner_kind == "formatter_step":
                    if ruleset_key is not None:
                        ruleset_artifacts = ruleset_artifact_paths_for_award(
                            award_code,
                            ruleset_key,
                        )
                        summarize_overtime_entitlements(
                            interpretation_path=ruleset_artifacts.revised_markdown,
                            output_path=ruleset_artifacts.formatted_markdown,
                        )
                        print(
                            "Formatted overtime guide saved to "
                            f"{ruleset_artifacts.formatted_markdown}"
                        )
                    else:
                        summarize_overtime_entitlements(
                            interpretation_path=artifact_paths.revised_overtime_interpretation,
                            output_path=artifact_paths.overtime_entitlements,
                        )
                        print(
                            "Formatted overtime guide saved to "
                            f"{artifact_paths.overtime_entitlements}"
                        )
                else:
                    if planned_step.step_id == "3.1" and ruleset_key is not None:
                        generate_overtime_ruleset(
                            classification_path=paths.classification_path,
                            ruleset_key=ruleset_key,
                        )
                    elif planned_step.step_id == "3.2" and ruleset_key is not None:
                        interpretation_path = ruleset_output_path_for_classification(
                            paths.classification_path,
                            ruleset_key,
                        )
                        review_overtime_interpretation(
                            interpretation_path=interpretation_path,
                            classification_path=paths.classification_path,
                            overtime_clause_classification_path=ruleset_clause_classification_output_path_for_classification(
                                paths.classification_path,
                                ruleset_key,
                            ),
                            feedback_output_path=evaluator_feedback_path_for_interpretation(
                                interpretation_path
                            ),
                            creator_response_output_path=creator_response_path_for_interpretation(
                                interpretation_path
                            ),
                            revised_output_path=revised_output_path_for_interpretation(
                                interpretation_path
                            ),
                            ruleset_key=ruleset_key,
                        )
                    elif planned_step.step_id == "5.1" and ruleset_key is not None:
                        ruleset_artifacts = ruleset_artifact_paths_for_award(
                            award_code,
                            ruleset_key,
                        )
                        generate_core_overtime_pseudocode(
                            summary_path=source_path_for_ruleset_core_overtime_pseudocode(
                                ruleset_artifacts
                            ),
                            output_path=ruleset_artifacts.pseudocode_markdown,
                        )
                        print(
                            "Core overtime pseudocode saved to "
                            f"{ruleset_artifacts.pseudocode_markdown}"
                        )
                    else:
                        run_selected_step(paths, planned_step.step_id)

                print(
                    f"Completed step {step_index} of {len(planned_steps)}: "
                    f"{planned_step.label}"
                )

        if status_callback is not None:
            status_callback(
                {
                    "completed_steps": len(planned_steps),
                    "total_steps": len(planned_steps),
                    "progress_fraction": 1.0,
                    "current_step": None,
                    "current_step_label": None,
                    "message": f"{pipeline_run_label(step, ruleset_key)} finished for {award_code}.",
                }
            )
    except Exception as exc:
        traceback.print_exc(file=error_buffer)
        combined_log = combine_pipeline_logs(output_buffer.getvalue(), error_buffer.getvalue())
        if isinstance(exc, AwardPipelineError):
            return {
                "success": False,
                "duration_seconds": time.perf_counter() - started_at,
                "log": combined_log,
                "completed_steps": max(
                    (planned_steps.index(active_step) if active_step else 0),
                    0,
                ),
                "total_steps": len(planned_steps),
                "progress_fraction": progress_value(
                    max((planned_steps.index(active_step) if active_step else 0), 0),
                    len(planned_steps),
                ),
                "failed_step": active_step.step_id if active_step else None,
                "failed_step_label": active_step.label if active_step else None,
            }

        return {
            "success": False,
            "duration_seconds": time.perf_counter() - started_at,
            "log": combined_log,
            "completed_steps": max(
                (planned_steps.index(active_step) if active_step else 0),
                0,
            ),
            "total_steps": len(planned_steps),
            "progress_fraction": progress_value(
                max((planned_steps.index(active_step) if active_step else 0), 0),
                len(planned_steps),
            ),
            "failed_step": active_step.step_id if active_step else None,
            "failed_step_label": active_step.label if active_step else None,
        }
    finally:
        if live_output_writer is not None:
            live_output_writer.close()
        if live_error_writer is not None:
            live_error_writer.close()

    return {
        "success": True,
        "duration_seconds": time.perf_counter() - started_at,
        "log": combine_pipeline_logs(output_buffer.getvalue(), error_buffer.getvalue()),
        "validation_summary": load_5b_validation_summary(paths, step),
        "completed_steps": len(planned_steps),
        "total_steps": len(planned_steps),
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


def start_background_pipeline_run(
    award_code: str,
    step: str | None,
    *,
    ruleset_key: str | None = None,
) -> dict[str, Any]:
    """Start one background pipeline process for the selected award code."""
    current_status = normalized_status_for_award(award_code)
    if current_status is not None and current_status.get("state") in {"starting", "running"}:
        raise RuntimeError(f"A pipeline run is already in progress for {award_code}.")

    run_id = str(int(time.time() * 1000))
    started_at = time.time()
    initial_status = {
        "award_code": award_code,
        "step": step,
        "run_id": run_id,
        "state": "starting",
        "message": f"{pipeline_run_label(step, ruleset_key)} is starting for {award_code}.",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "pid": None,
        "log_path": str(log_path_for_award(award_code)),
        "validation_summary": None,
        "completed_steps": 0,
        "total_steps": None,
        "progress_fraction": 0.0,
        "current_step": None,
        "current_step_label": None,
        "ruleset_key": ruleset_key,
    }
    write_status(initial_status)
    log_path_for_award(award_code).write_text("", encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "streamlit_review.run_pipeline_background",
        "--award-code",
        award_code,
        "--run-id",
        run_id,
    ]
    if step is not None:
        command.extend(["--step", step])
    if ruleset_key is not None:
        command.extend(["--ruleset-key", ruleset_key])

    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    initial_status["pid"] = process.pid
    initial_status["state"] = "running"
    initial_status["message"] = (
        f"{pipeline_run_label(step, ruleset_key)} is running for {award_code}."
    )
    write_status(initial_status)

    return initial_status
