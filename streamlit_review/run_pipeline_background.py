from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from streamlit_review.pipeline_runs import (
    log_path_for_award,
    pipeline_run_label,
    run_pipeline_for_award,
    write_status,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for one background run."""
    parser = argparse.ArgumentParser(description="Run one award pipeline job in the background.")
    parser.add_argument("--award-code", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step", default=None)
    parser.add_argument("--ruleset-key", default=None)
    return parser.parse_args()


def main() -> None:
    """Run the selected pipeline job and persist the final status."""
    args = parse_args()
    started_at = time.time()

    running_status = {
        "award_code": args.award_code,
        "step": args.step,
        "run_id": args.run_id,
        "state": "running",
        "message": f"{pipeline_run_label(args.step, args.ruleset_key)} is running for {args.award_code}.",
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "pid": os.getpid(),
        "log_path": str(log_path_for_award(args.award_code)),
        "validation_summary": None,
        "completed_steps": 0,
        "total_steps": None,
        "progress_fraction": 0.0,
        "current_step": None,
        "current_step_label": None,
        "ruleset_key": args.ruleset_key,
    }
    write_status(running_status)

    try:
        def write_progress_status(progress_update: dict[str, object]) -> None:
            write_status(
                {
                    **running_status,
                    **progress_update,
                    "state": "running",
                    "finished_at": None,
                    "duration_seconds": None,
                }
            )

        result = run_pipeline_for_award(
            args.award_code,
            args.step,
            ruleset_key=args.ruleset_key,
            status_callback=write_progress_status,
            log_path=log_path_for_award(args.award_code),
        )
    except Exception:
        log_text = traceback.format_exc()
        log_path_for_award(args.award_code).write_text(log_text, encoding="utf-8")
        finished_at = time.time()
        write_status(
            {
                **running_status,
                "state": "error",
                "message": f"{pipeline_run_label(args.step, args.ruleset_key)} failed for {args.award_code}.",
                "finished_at": finished_at,
                "duration_seconds": finished_at - started_at,
            }
        )
        return

    log_path_for_award(args.award_code).write_text(result["log"], encoding="utf-8")

    finished_at = time.time()
    final_status = {
        **running_status,
        "finished_at": finished_at,
        "duration_seconds": finished_at - started_at,
        "validation_summary": result.get("validation_summary"),
        "completed_steps": result.get("completed_steps"),
        "total_steps": result.get("total_steps"),
        "progress_fraction": (
            1.0 if result["success"] else result.get("progress_fraction", 0.0)
        ),
        "current_step": None,
        "current_step_label": None,
    }

    if result["success"]:
        validation_summary = result.get("validation_summary")
        if validation_summary and validation_summary["overall_status"] != "passed":
            final_status["state"] = "warning"
            final_status["message"] = (
                f"{pipeline_run_label(args.step, args.ruleset_key)} completed for {args.award_code} in "
                f"{final_status['duration_seconds']:.1f}s with validation issues "
                f"({validation_summary['overall_status']})."
            )
        else:
            final_status["state"] = "success"
            final_status["message"] = (
                f"{pipeline_run_label(args.step, args.ruleset_key)} completed for {args.award_code} in "
                f"{final_status['duration_seconds']:.1f}s."
            )
    else:
        final_status["state"] = "error"
        failed_step_label = result.get("failed_step_label")
        completed_steps = result.get("completed_steps")
        total_steps = result.get("total_steps")
        if failed_step_label and isinstance(completed_steps, int) and isinstance(total_steps, int):
            final_status["message"] = (
                f"{pipeline_run_label(args.step, args.ruleset_key)} failed for {args.award_code} at "
                f"step {completed_steps + 1} of {total_steps}: {failed_step_label}."
            )
        else:
            final_status["message"] = (
                f"{pipeline_run_label(args.step, args.ruleset_key)} failed for {args.award_code}."
            )

    write_status(final_status)


if __name__ == "__main__":
    main()
