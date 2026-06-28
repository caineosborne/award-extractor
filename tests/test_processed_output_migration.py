import json
from pathlib import Path

from src.migrate_processed_outputs_to_award_first import migrate_processed_outputs


def test_migration_moves_legacy_files_into_award_folders_and_rewrites_paths(tmp_path):
    project_root = tmp_path
    processed_root = project_root / "data" / "processed"

    fetch_dir = processed_root / "1_fetch_award"
    payment_dir = processed_root / "2_payment_clause_identifier"
    interpretation_dir = processed_root / "3_overtime_interpretations"
    entitlements_dir = processed_root / "4a_overtime_entitlements"
    pseudocode_dir = processed_root / "5b_generate_overtime_pseudocode"

    (fetch_dir / "raw").mkdir(parents=True)
    (interpretation_dir / "feedback").mkdir(parents=True)
    fetch_dir.mkdir(parents=True, exist_ok=True)
    payment_dir.mkdir(parents=True, exist_ok=True)
    entitlements_dir.mkdir(parents=True, exist_ok=True)
    pseudocode_dir.mkdir(parents=True, exist_ok=True)

    legacy_fetch_json = fetch_dir / "MA000018.json"
    legacy_fetch_json.write_text('{"award": true}', encoding="utf-8")
    (fetch_dir / "raw" / "MA000018.html").write_text("<html></html>", encoding="utf-8")
    (fetch_dir / "MA000018_sections.json").write_text('{"sections": []}', encoding="utf-8")
    (fetch_dir / "MA000018.csv").write_text("PartHeading,L1\n", encoding="utf-8")

    old_fetch_reference = str(legacy_fetch_json)
    old_classification_reference = str(payment_dir / "MA000018_payment_classification.json")
    old_interpretation_reference = str(
        interpretation_dir / "MA000018_overtime_interpretation_revised.md"
    )
    old_target_reference = str(
        pseudocode_dir / "MA000018_core_overtime_pseudocode.md"
    )

    (payment_dir / "MA000018_payment_classification.json").write_text(
        json.dumps({"source_file": old_fetch_reference}, indent=2),
        encoding="utf-8",
    )
    (interpretation_dir / "MA000018_overtime_clause_classification.json").write_text(
        json.dumps({"source_classification_file": old_classification_reference}, indent=2),
        encoding="utf-8",
    )
    (interpretation_dir / "MA000018_overtime_interpretation_revised.md").write_text(
        "# revised interpretation",
        encoding="utf-8",
    )
    (interpretation_dir / "feedback" / "MA000018_overtime_interpretation_evaluator_feedback.md").write_text(
        f"Based on {old_classification_reference}",
        encoding="utf-8",
    )
    (entitlements_dir / "MA000018_overtime_entitlements.md").write_text(
        f"Source: {old_interpretation_reference}",
        encoding="utf-8",
    )
    (pseudocode_dir / "MA000018_core_overtime_pseudocode_validation.md").write_text(
        f"Source path: {old_interpretation_reference}\nTarget path: {old_target_reference}",
        encoding="utf-8",
    )
    (pseudocode_dir / "MA000018_core_overtime_pseudocode.md").write_text(
        "# pseudocode",
        encoding="utf-8",
    )

    result = migrate_processed_outputs(
        processed_root=processed_root,
        project_root=project_root,
    )

    award_dir = processed_root / "MA000018"

    assert result["moved_file_count"] == 11
    assert (award_dir / "MA000018.json").exists()
    assert (award_dir / "raw" / "MA000018.html").exists()
    assert (award_dir / "supporting" / "MA000018_sections.json").exists()
    assert (award_dir / "supporting" / "MA000018.csv").exists()
    assert (award_dir / "MA000018_payment_classification.json").exists()
    assert (award_dir / "MA000018_overtime_clause_classification.json").exists()
    assert (award_dir / "MA000018_overtime_interpretation_revised.md").exists()
    assert (
        award_dir
        / "feedback"
        / "MA000018_overtime_interpretation_evaluator_feedback.md"
    ).exists()
    assert (award_dir / "MA000018_overtime_entitlements.md").exists()
    assert (award_dir / "MA000018_core_overtime_pseudocode_validation.md").exists()

    assert not legacy_fetch_json.exists()
    assert not (payment_dir / "MA000018_payment_classification.json").exists()
    assert not (
        interpretation_dir / "feedback" / "MA000018_overtime_interpretation_evaluator_feedback.md"
    ).exists()

    new_fetch_reference = str(award_dir / "MA000018.json")
    new_classification_reference = str(award_dir / "MA000018_payment_classification.json")
    new_interpretation_reference = str(award_dir / "MA000018_overtime_interpretation_revised.md")
    new_target_reference = str(award_dir / "MA000018_core_overtime_pseudocode.md")

    classification_text = (award_dir / "MA000018_payment_classification.json").read_text(
        encoding="utf-8"
    )
    validation_text = (award_dir / "MA000018_core_overtime_pseudocode_validation.md").read_text(
        encoding="utf-8"
    )

    assert old_fetch_reference not in classification_text
    assert new_fetch_reference in classification_text
    assert old_classification_reference not in validation_text
    assert old_interpretation_reference not in validation_text
    assert old_target_reference not in validation_text
    assert new_interpretation_reference in validation_text
    assert new_target_reference in validation_text


def test_migration_moves_legacy_archives_to_matching_award_archive_locations(tmp_path):
    project_root = tmp_path
    processed_root = project_root / "data" / "processed"

    fetch_archive_dir = processed_root / "1_fetch_award" / "archive"
    interpretation_archive_dir = processed_root / "3_overtime_interpretations" / "archive"
    pseudocode_archive_dir = processed_root / "5b_generate_overtime_pseudocode" / "archive"

    fetch_archive_dir.mkdir(parents=True)
    interpretation_archive_dir.mkdir(parents=True)
    pseudocode_archive_dir.mkdir(parents=True)

    (fetch_archive_dir / "MA000018_20260624_090028.json").write_text("{}", encoding="utf-8")
    (fetch_archive_dir / "MA000018_sections_20260624_090028.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (interpretation_archive_dir / "MA000018_overtime_interpretation_20260624_133840.md").write_text(
        "# old",
        encoding="utf-8",
    )
    (pseudocode_archive_dir / "MA000018_core_overtime_pseudocode_validation_20260624_150729.md").write_text(
        "# old validation",
        encoding="utf-8",
    )

    migrate_processed_outputs(
        processed_root=processed_root,
        project_root=project_root,
    )

    award_dir = processed_root / "MA000018"

    assert (award_dir / "archive" / "MA000018_20260624_090028.json").exists()
    assert (
        award_dir / "supporting" / "archive" / "MA000018_sections_20260624_090028.json"
    ).exists()
    assert (
        award_dir / "archive" / "MA000018_overtime_interpretation_20260624_133840.md"
    ).exists()
    assert (
        award_dir
        / "archive"
        / "MA000018_core_overtime_pseudocode_validation_20260624_150729.md"
    ).exists()


def test_migration_normalizes_stray_output_set_directories(tmp_path):
    project_root = tmp_path
    processed_root = project_root / "data" / "processed"

    stray_dir = processed_root / "MA000120_overtime_entitlements_final"
    stray_dir.mkdir(parents=True)
    stray_file = stray_dir / "archive" / "MA000120_overtime_entitlements_final_20260619_155506.md"
    stray_file.parent.mkdir(parents=True)
    stray_file.write_text("# final", encoding="utf-8")

    excluded_dir = processed_root / "EBA-Woolworths-2024-F_excluded"
    excluded_dir.mkdir(parents=True, exist_ok=True)
    excluded_file = (
        excluded_dir
        / "supporting"
        / "EBA-Woolworths-2024-F_excluded_sections.json"
    )
    excluded_file.parent.mkdir(parents=True)
    excluded_file.write_text("{}", encoding="utf-8")

    result = migrate_processed_outputs(
        processed_root=processed_root,
        project_root=project_root,
    )

    assert result["moved_file_count"] == 2
    assert (
        processed_root
        / "MA000120"
        / "archive"
        / "MA000120_overtime_entitlements_final_20260619_155506.md"
    ).exists()
    assert (
        processed_root
        / "EBA-Woolworths-2024-F"
        / "supporting"
        / "EBA-Woolworths-2024-F_excluded_sections.json"
    ).exists()
