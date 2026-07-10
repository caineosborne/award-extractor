from pathlib import Path

from src.common.prompt_logging import configure_prompt_log, log_llm_prompt


def test_log_llm_prompt_appends_heading_and_raw_messages(tmp_path: Path):
    log_path = tmp_path / "MAxxx120.log"

    log_llm_prompt(
        "1.2 Overtime Creation",
        [
            {"role": "system", "content": "System instructions"},
            {"role": "user", "content": "Award clause text"},
        ],
        log_path=log_path,
    )
    log_llm_prompt(
        "5.1 Overtime Creation Pseudocode Repair",
        [{"role": "user", "content": "Repair instructions"}],
        log_path=log_path,
    )

    logged_text = log_path.read_text(encoding="utf-8")

    assert "1.2 Overtime Creation" in logged_text
    assert "--- SYSTEM ---" in logged_text
    assert "System instructions" in logged_text
    assert "Award clause text" in logged_text
    assert "5.1 Overtime Creation Pseudocode Repair" in logged_text
    assert logged_text.index("1.2 Overtime Creation") < logged_text.index(
        "5.1 Overtime Creation Pseudocode Repair"
    )


def test_pipeline_log_path_uses_output_folder_and_output_stem(tmp_path: Path):
    log_path = tmp_path / "MA000120" / "MA000120.log"

    configure_prompt_log(log_path)
    log_llm_prompt("2.1 Payment Classification", [{"role": "user", "content": "Prompt"}])

    assert log_path.read_text(encoding="utf-8").endswith("Prompt\n")
