"""Tests for Streamlit background-run log persistence."""

from io import StringIO

from streamlit_review.pipeline_runs import LiveLogWriter


def test_live_log_writer_appends_to_an_existing_run_log(tmp_path):
    log_path = tmp_path / "MA000018.log"
    log_path.write_text("previous run\n", encoding="utf-8")

    output = StringIO()
    writer = LiveLogWriter(log_path, output)
    writer.write("current run\n")
    writer.close()

    assert log_path.read_text(encoding="utf-8") == "previous run\ncurrent run\n"
