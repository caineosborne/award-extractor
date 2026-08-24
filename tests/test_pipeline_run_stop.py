import json
import signal

import pytest

from streamlit_review import pipeline_runs
from streamlit_review import app as streamlit_app


def active_status(pid: int = 4321) -> dict[str, object]:
    return {
        "award_code": "MA000120",
        "step": None,
        "run_id": "run-1",
        "state": "running",
        "message": "Pipeline is running.",
        "started_at": 100.0,
        "finished_at": None,
        "duration_seconds": None,
        "pid": pid,
        "completed_steps": 2,
        "total_steps": 8,
        "progress_fraction": 0.25,
        "current_step": "3.1",
        "current_step_label": "Generate ruleset",
    }


def test_stop_background_pipeline_run_stops_isolated_process_group(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(pipeline_runs, "PIPELINE_RUN_DIR", tmp_path)
    pipeline_runs.write_status(active_status())

    process_checks = iter([True, False, False])
    monkeypatch.setattr(
        pipeline_runs,
        "process_is_running",
        lambda _pid: next(process_checks),
    )
    monkeypatch.setattr(pipeline_runs.os, "getpgid", lambda pid: pid)
    sent_signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        pipeline_runs.os,
        "killpg",
        lambda process_group_id, sent_signal: sent_signals.append(
            (process_group_id, sent_signal)
        ),
    )
    monkeypatch.setattr(pipeline_runs.time, "time", lambda: 125.0)

    stopped_status = pipeline_runs.stop_background_pipeline_run("MA000120")

    assert sent_signals == [(4321, signal.SIGTERM)]
    assert stopped_status["state"] == "stopped"
    assert stopped_status["duration_seconds"] == 25.0
    assert stopped_status["current_step"] is None
    assert "Files already written were kept" in stopped_status["message"]

    persisted_status = json.loads(
        pipeline_runs.status_path_for_award("MA000120").read_text(encoding="utf-8")
    )
    assert persisted_status["state"] == "stopped"
    assert "stopped by the user" in pipeline_runs.log_path_for_award(
        "MA000120"
    ).read_text(encoding="utf-8")


def test_stop_background_pipeline_run_refuses_unexpected_process_group(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(pipeline_runs, "PIPELINE_RUN_DIR", tmp_path)
    pipeline_runs.write_status(active_status())
    monkeypatch.setattr(pipeline_runs, "process_is_running", lambda _pid: True)
    monkeypatch.setattr(pipeline_runs.os, "getpgid", lambda _pid: 9999)
    monkeypatch.setattr(
        pipeline_runs.os,
        "killpg",
        lambda *_args: pytest.fail("An unrelated process group must not be signalled."),
    )

    with pytest.raises(RuntimeError, match="not an isolated background run"):
        pipeline_runs.stop_background_pipeline_run("MA000120")


def test_stop_background_pipeline_run_requires_an_active_run(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline_runs, "PIPELINE_RUN_DIR", tmp_path)
    status = active_status()
    status["state"] = "success"
    pipeline_runs.write_status(status)

    with pytest.raises(RuntimeError, match="No active pipeline run"):
        pipeline_runs.stop_background_pipeline_run("MA000120")


def test_active_run_status_panel_shows_working_stop_button(monkeypatch, tmp_path):
    class DummyColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    stop_calls: list[str] = []
    button_calls: list[dict[str, object]] = []

    def fake_button(label: str, **kwargs) -> bool:
        button_calls.append({"label": label, **kwargs})
        return kwargs.get("key") == "stop_pipeline_run_MA000120"

    monkeypatch.setattr(streamlit_app.st, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "error", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app.st,
        "columns",
        lambda count, gap="small": tuple(DummyColumn() for _ in range(count)),
    )
    monkeypatch.setattr(streamlit_app.st, "button", fake_button)
    monkeypatch.setattr(streamlit_app.st, "rerun", lambda: None)
    monkeypatch.setattr(
        streamlit_app,
        "stop_background_pipeline_run",
        lambda award_code: stop_calls.append(award_code),
    )
    monkeypatch.setattr(
        streamlit_app,
        "log_path_for_award",
        lambda _award_code: tmp_path / "missing.log",
    )
    monkeypatch.setattr(streamlit_app.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "code", lambda *_args, **_kwargs: None)

    streamlit_app.render_pipeline_run_status("MA000120", active_status())

    stop_button = next(
        call for call in button_calls if call["label"] == "Stop pipeline run"
    )
    assert stop_button["type"] == "primary"
    assert stop_calls == ["MA000120"]
