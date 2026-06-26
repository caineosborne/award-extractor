from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
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
from src.common.active_pipeline_paths import default_award_url_for_code
from src.script_4a_summarize_overtime import summarize_overtime_entitlements
from streamlit_review.output_data import artifact_paths_for_award, load_json_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_RUN_DIR = PROJECT_ROOT / "data" / "processed" / "_streamlit_pipeline_runs"

PIPELINE_STEP_LABELS = {
    "1": "Retrieve award",
    "2": "Classify clauses",
    "3": "Generate overtime",
    "3b": "Review overtime",
    "4": "Format overtime guide",
    "5b": "Generate pseudocode",
}


def pipeline_run_label(step: str | None) -> str:
    """Return the human-readable label for one pipeline run."""
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


def load_5b_validation_summary(paths: Any, step: str | None) -> dict[str, Any] | None:
    """Load the step 5B validation summary when available."""
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
    """Run one pipeline step or the default flow and capture its outputs."""
    url = default_award_url_for_code(award_code)
    paths = build_paths(award_code, suffix=None, url=url)
    artifact_paths = artifact_paths_for_award(award_code)
    output_buffer = StringIO()
    error_buffer = StringIO()
    started_at = time.perf_counter()

    try:
        with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
            if step is None:
                run_default_pipeline(paths)
            elif step == "4":
                summarize_overtime_entitlements(
                    interpretation_path=artifact_paths.revised_overtime_interpretation,
                    output_path=artifact_paths.overtime_entitlements,
                )
                print(f"Formatted overtime guide saved to {artifact_paths.overtime_entitlements}")
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
        "validation_summary": load_5b_validation_summary(paths, step),
    }


def start_background_pipeline_run(award_code: str, step: str | None) -> dict[str, Any]:
    """Start one background pipeline process for the selected award code."""
    current_status = normalized_status_for_award(award_code)
    if current_status is not None and current_status.get("state") == "running":
        raise RuntimeError(f"A pipeline run is already in progress for {award_code}.")

    run_id = str(int(time.time() * 1000))
    started_at = time.time()
    initial_status = {
        "award_code": award_code,
        "step": step,
        "run_id": run_id,
        "state": "starting",
        "message": f"{pipeline_run_label(step)} is starting for {award_code}.",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "pid": None,
        "log_path": str(log_path_for_award(award_code)),
        "validation_summary": None,
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
    initial_status["message"] = f"{pipeline_run_label(step)} is running for {award_code}."
    write_status(initial_status)

    return initial_status
