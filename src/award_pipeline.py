from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.output_paths import (
    FETCH_AWARD_DIR,
    timestamped_archive_path,
    write_text_with_archive,
)
from src.script_1_fetch_award import build_section_index, extract_award, fetch, iter_heading_rows
from src.script_2_classify_payments import classify_award, output_path_for_award
from src.script_3_interpret_overtime import (
    generate_overtime_interpretation,
    output_path_for_classification as interpretation_path_for_classification,
)
from src.script_3b_review_overtime_interpretation import (
    creator_response_path_for_interpretation,
    evaluator_feedback_path_for_interpretation,
    revised_output_path_for_interpretation,
    review_overtime_interpretation,
)
from src.script_4a_summarize_overtime import (
    output_path_for_interpretation as entitlements_path_for_interpretation,
    summarize_overtime_entitlements,
)
from src.script_5b_generate_overtime_pseudocode import (
    generate_core_overtime_pseudocode,
    output_path_for_summary as pseudocode_path_for_summary,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AWARD_URL_TEMPLATE = "https://awards.fairwork.gov.au/{award_code}.html"
STEP_CHOICES = ("1", "2", "3", "3b", "4a", "5b")
DEFAULT_PIPELINE_STEPS = ("1", "2", "3", "3b", "4a")


class AwardPipelineError(RuntimeError):
    """Raised when the wrapper cannot resolve the requested pipeline state."""


@dataclass(frozen=True)
class AwardPipelinePaths:
    award_code: str
    suffix: str | None
    output_stem: str
    url: str
    raw_html_path: Path
    award_json_path: Path
    section_index_path: Path
    heading_csv_path: Path
    classification_path: Path
    interpretation_path: Path
    revised_interpretation_path: Path
    evaluator_feedback_path: Path
    creator_response_path: Path
    entitlements_path: Path
    pseudocode_path: Path


@dataclass(frozen=True)
class PipelineRequirement:
    paths: tuple[Path, ...]
    prior_step: str
    description: str


def normalize_award_code(value: str) -> str:
    award_code = value.strip().upper()
    if not re.fullmatch(r"MA\d{6}", award_code):
        raise argparse.ArgumentTypeError(
            "award code must look like MA000120"
        )
    return award_code


def normalize_suffix(value: str | None) -> str | None:
    if value is None:
        return None

    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    suffix = suffix.strip("._-")
    if not suffix:
        raise argparse.ArgumentTypeError("suffix must contain at least one letter or digit")
    return suffix


def default_url_for_award_code(award_code: str) -> str:
    return DEFAULT_AWARD_URL_TEMPLATE.format(award_code=award_code)


def output_stem_for_award(award_code: str, suffix: str | None) -> str:
    if suffix:
        return f"{award_code}_{suffix}"
    return award_code


def build_paths(award_code: str, suffix: str | None, url: str) -> AwardPipelinePaths:
    output_stem = output_stem_for_award(award_code, suffix)
    fetch_dir = PROJECT_ROOT / "data" / "processed" / FETCH_AWARD_DIR
    raw_html_path = fetch_dir / "raw" / f"{output_stem}.html"
    award_json_path = fetch_dir / f"{output_stem}.json"
    section_index_path = fetch_dir / f"{output_stem}_sections.json"
    heading_csv_path = fetch_dir / f"{output_stem}.csv"

    classification_path = output_path_for_award(award_json_path)
    interpretation_path = interpretation_path_for_classification(classification_path)
    revised_interpretation_path = revised_output_path_for_interpretation(interpretation_path)
    evaluator_feedback_path = evaluator_feedback_path_for_interpretation(interpretation_path)
    creator_response_path = creator_response_path_for_interpretation(interpretation_path)
    entitlements_path = entitlements_path_for_interpretation(interpretation_path)
    pseudocode_path = pseudocode_path_for_summary(entitlements_path)

    return AwardPipelinePaths(
        award_code=award_code,
        suffix=suffix,
        output_stem=output_stem,
        url=url,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
        section_index_path=section_index_path,
        heading_csv_path=heading_csv_path,
        classification_path=classification_path,
        interpretation_path=interpretation_path,
        revised_interpretation_path=revised_interpretation_path,
        evaluator_feedback_path=evaluator_feedback_path,
        creator_response_path=creator_response_path,
        entitlements_path=entitlements_path,
        pseudocode_path=pseudocode_path,
    )


def require_existing(path: Path, step_name: str, prior_step: str) -> None:
    if not path.exists():
        raise AwardPipelineError(
            f"Missing required file for step {step_name}: {path}. "
            f"Run step {prior_step} first."
        )


def require_any_existing(paths: tuple[Path, ...], step_name: str, prior_step: str) -> Path:
    for path in paths:
        if path.exists():
            return path

    joined_paths = ", ".join(str(path) for path in paths)
    raise AwardPipelineError(
        f"Missing required file for step {step_name}: {joined_paths}. "
        f"Run step {prior_step} first."
    )


def write_fetched_award_outputs(
    url: str,
    raw_html_path: Path,
    award_json_path: Path,
    section_index_path: Path,
    heading_csv_path: Path,
) -> None:
    soup = fetch(url)
    main_content = soup.find(id="mainContent")
    if main_content is None:
        raise AwardPipelineError("Could not find element with id='mainContent'.")

    award = extract_award(main_content)
    timestamp = datetime.now()

    raw_html_path.parent.mkdir(parents=True, exist_ok=True)
    raw_html_path.write_text(str(main_content), encoding="utf-8")

    write_text_with_archive(
        award_json_path,
        json.dumps(award, indent=2, ensure_ascii=False),
        timestamp,
    )
    write_text_with_archive(
        section_index_path,
        json.dumps(build_section_index(award), indent=2, ensure_ascii=False),
        timestamp,
    )

    heading_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with heading_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["PartHeading", "L1", "L2", "L3"])
        writer.writeheader()
        writer.writerows(iter_heading_rows(award))

    archive_csv_path = timestamped_archive_path(heading_csv_path, timestamp)
    archive_csv_path.parent.mkdir(parents=True, exist_ok=True)
    archive_csv_path.write_text(heading_csv_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Raw HTML saved to {raw_html_path}")
    print(f"Processed JSON saved to {award_json_path}")
    print(f"Section index JSON saved to {section_index_path}")
    print(f"Heading CSV saved to {heading_csv_path}")


def run_step_1(paths: AwardPipelinePaths) -> None:
    write_fetched_award_outputs(
        url=paths.url,
        raw_html_path=paths.raw_html_path,
        award_json_path=paths.award_json_path,
        section_index_path=paths.section_index_path,
        heading_csv_path=paths.heading_csv_path,
    )


def run_step_2(paths: AwardPipelinePaths) -> None:
    require_existing(paths.award_json_path, "2", "1")
    classify_award(
        award_path=paths.award_json_path,
        output_path=paths.classification_path,
    )


def run_step_3(paths: AwardPipelinePaths) -> None:
    require_existing(paths.classification_path, "3", "2")
    generate_overtime_interpretation(
        classification_path=paths.classification_path,
        output_path=paths.interpretation_path,
    )


def run_step_3b(paths: AwardPipelinePaths) -> None:
    require_existing(paths.classification_path, "3b", "2")
    require_existing(paths.interpretation_path, "3b", "3")
    review_overtime_interpretation(
        interpretation_path=paths.interpretation_path,
        classification_path=paths.classification_path,
        feedback_output_path=paths.evaluator_feedback_path,
        creator_response_output_path=paths.creator_response_path,
        revised_output_path=paths.revised_interpretation_path,
    )


def interpretation_source_for_step_4a(paths: AwardPipelinePaths) -> Path:
    if paths.revised_interpretation_path.exists():
        return paths.revised_interpretation_path
    if paths.interpretation_path.exists():
        return paths.interpretation_path

    raise AwardPipelineError(
        f"Missing required file for step 4a: {paths.interpretation_path} "
        f"or {paths.revised_interpretation_path}. Run step 3 first."
    )


def run_step_4a(paths: AwardPipelinePaths) -> None:
    interpretation_path = interpretation_source_for_step_4a(paths)
    summarize_overtime_entitlements(
        interpretation_path=interpretation_path,
        output_path=paths.entitlements_path,
    )


def run_step_5b(paths: AwardPipelinePaths) -> None:
    require_existing(paths.entitlements_path, "5b", "4a")
    generate_core_overtime_pseudocode(
        summary_path=paths.entitlements_path,
        output_path=paths.pseudocode_path,
    )


def run_default_pipeline(paths: AwardPipelinePaths) -> None:
    run_step_1(paths)
    run_step_2(paths)
    run_step_3(paths)
    run_step_3b(paths)
    run_step_4a(paths)


def run_selected_step(paths: AwardPipelinePaths, step: str) -> None:
    if step == "1":
        run_step_1(paths)
        return
    if step == "2":
        run_step_2(paths)
        return
    if step == "3":
        run_step_3(paths)
        return
    if step == "3b":
        run_step_3b(paths)
        return
    if step == "4a":
        run_step_4a(paths)
        return
    if step == "5b":
        run_step_5b(paths)
        return

    raise AwardPipelineError(f"Unknown step: {step}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the award extraction pipeline from an award code."
    )
    parser.add_argument(
        "award_code",
        type=normalize_award_code,
        help="Award code such as MA000120.",
    )
    parser.add_argument(
        "step",
        nargs="?",
        choices=STEP_CHOICES,
        help="Optional step to run. If omitted, the pipeline runs through 4A.",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Optional filename suffix, for example test or draft.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Optional award URL. Defaults to the Fair Work award page for the award code.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    suffix = normalize_suffix(args.suffix)
    url = args.url or default_url_for_award_code(args.award_code)
    paths = build_paths(args.award_code, suffix, url)

    if args.step is None:
        run_default_pipeline(paths)
        return

    run_selected_step(paths, args.step)
