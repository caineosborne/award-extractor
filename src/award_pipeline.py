from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from src.common.active_pipeline_paths import (
    PROJECT_ROOT,
    default_award_url_for_code,
    interpretation_output_path_for_classification,
    preferred_5b_source_path_for_interpretation,
    normalize_award_code,
    overtime_clause_classification_output_path_for_classification,
    revised_output_path_for_interpretation,
)
from src.script_1_fetch_award import fetch_and_extract_award, write_step_1_outputs
from src.script_2_classify_payments import classify_award, output_path_for_award
from src.script_3_interpret_overtime import generate_overtime_interpretation
from src.script_3_interpret_overtime import DEFAULT_EXPERT_RUN_COUNT
from src.script_3b_review_overtime_interpretation import review_overtime_interpretation
from src.script_5b_generate_overtime_pseudocode import (
    generate_core_overtime_pseudocode,
    output_path_for_summary,
)
from src.script_5b_validate_overtime_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
)


STEP_CHOICES = ("1", "2", "3", "3b", "5b")
DEFAULT_PIPELINE_STEPS = ("1", "2", "3", "3b")


class AwardPipelineError(RuntimeError):
    """Raised when the wrapper cannot resolve the requested pipeline state."""


@dataclass(frozen=True)
class ActivePipelinePaths:
    award_code: str
    suffix: str | None
    output_stem: str
    url: str
    raw_html_path: Path
    award_json_path: Path
    classification_path: Path
    overtime_clause_classification_path: Path
    interpretation_path: Path
    evaluator_feedback_path: Path
    creator_response_path: Path
    revised_interpretation_path: Path
    core_overtime_pseudocode_path: Path
    core_overtime_validation_json_path: Path
    core_overtime_validation_markdown_path: Path


def argparse_award_code(value: str) -> str:
    """Adapt award code validation for argparse error reporting."""
    try:
        return normalize_award_code(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def normalize_suffix(value: str | None) -> str | None:
    """Normalize an optional filename suffix used for pipeline outputs."""
    if value is None:
        return None

    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    suffix = suffix.strip("._-")
    if not suffix:
        raise argparse.ArgumentTypeError("suffix must contain at least one letter or digit")
    return suffix


def output_stem_for_award(award_code: str, suffix: str | None) -> str:
    """Build the shared filename stem for all active pipeline artifacts."""
    if suffix:
        return f"{award_code}_{suffix}"
    return award_code


def build_paths(award_code: str, suffix: str | None, url: str) -> ActivePipelinePaths:
    """Build all active-step artifact paths for one pipeline run."""
    output_stem = output_stem_for_award(award_code, suffix)
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = processed_root / output_stem
    raw_html_path = award_dir / "raw" / f"{output_stem}.html"
    award_json_path = award_dir / f"{output_stem}.json"

    classification_path = output_path_for_award(award_json_path)
    overtime_clause_classification_path = overtime_clause_classification_output_path_for_classification(
        classification_path
    )
    interpretation_path = interpretation_output_path_for_classification(classification_path)
    evaluator_feedback_path = interpretation_path.parent / "feedback" / (
        f"{interpretation_path.stem}_evaluator_feedback.md"
    )
    creator_response_path = interpretation_path.parent / "feedback" / (
        f"{interpretation_path.stem}_creator_response.md"
    )
    revised_interpretation_path = revised_output_path_for_interpretation(interpretation_path)
    core_overtime_pseudocode_path = output_path_for_summary(revised_interpretation_path)
    core_overtime_validation_json_path = validation_json_path_for_pseudocode(
        core_overtime_pseudocode_path
    )
    core_overtime_validation_markdown_path = validation_markdown_path_for_pseudocode(
        core_overtime_pseudocode_path
    )

    return ActivePipelinePaths(
        award_code=award_code,
        suffix=suffix,
        output_stem=output_stem,
        url=url,
        raw_html_path=raw_html_path,
        award_json_path=award_json_path,
        classification_path=classification_path,
        overtime_clause_classification_path=overtime_clause_classification_path,
        interpretation_path=interpretation_path,
        evaluator_feedback_path=evaluator_feedback_path,
        creator_response_path=creator_response_path,
        revised_interpretation_path=revised_interpretation_path,
        core_overtime_pseudocode_path=core_overtime_pseudocode_path,
        core_overtime_validation_json_path=core_overtime_validation_json_path,
        core_overtime_validation_markdown_path=core_overtime_validation_markdown_path,
    )


def require_existing(path: Path, step_name: str, prior_step: str) -> None:
    """Ensure a required upstream artifact exists before running a step."""
    if not path.exists():
        raise AwardPipelineError(
            f"Missing required file for step {step_name}: {path}. "
            f"Run step {prior_step} first."
        )


def run_step_1(paths: ActivePipelinePaths) -> None:
    """Run step 1 and write the fetched award outputs."""
    main_content, award = fetch_and_extract_award(paths.url)
    write_step_1_outputs(
        url=paths.url,
        main_content=main_content,
        award=award,
        raw_dir=paths.raw_html_path.parent,
        processed_dir=paths.award_json_path.parent.parent,
    )


def run_step_2(paths: ActivePipelinePaths) -> None:
    """Run step 2 payment clause classification."""
    require_existing(paths.award_json_path, "2", "1")
    classify_award(
        award_path=paths.award_json_path,
        output_path=paths.classification_path,
    )


def run_step_3(paths: ActivePipelinePaths) -> None:
    """Run step 3 overtime interpretation generation."""
    require_existing(paths.classification_path, "3", "2")
    generate_overtime_interpretation(
        classification_path=paths.classification_path,
        classification_output_path=paths.overtime_clause_classification_path,
        output_path=paths.interpretation_path,
        expert_run_count=DEFAULT_EXPERT_RUN_COUNT,
    )


def run_step_3b(paths: ActivePipelinePaths) -> None:
    """Run step 3B one-pass review of the interpretation output."""
    require_existing(paths.classification_path, "3b", "2")
    require_existing(paths.overtime_clause_classification_path, "3b", "3")
    require_existing(paths.interpretation_path, "3b", "3")
    review_overtime_interpretation(
        interpretation_path=paths.interpretation_path,
        classification_path=paths.classification_path,
        overtime_clause_classification_path=paths.overtime_clause_classification_path,
        feedback_output_path=paths.evaluator_feedback_path,
        creator_response_output_path=paths.creator_response_path,
        revised_output_path=paths.revised_interpretation_path,
    )


def run_step_5b(paths: ActivePipelinePaths) -> None:
    """Run step 5B core overtime pseudocode generation."""
    require_existing(paths.revised_interpretation_path, "5b", "3b")
    source_path = preferred_5b_source_path_for_interpretation(paths.revised_interpretation_path)
    generate_core_overtime_pseudocode(
        summary_path=source_path,
        output_path=paths.core_overtime_pseudocode_path,
    )
    print(f"Core overtime pseudocode saved to {paths.core_overtime_pseudocode_path}")
    print(
        "5B validation JSON saved to "
        f"{paths.core_overtime_validation_json_path}"
    )
    print(
        "5B validation markdown saved to "
        f"{paths.core_overtime_validation_markdown_path}"
    )


STEP_RUNNERS = {
    "1": run_step_1,
    "2": run_step_2,
    "3": run_step_3,
    "3b": run_step_3b,
    "5b": run_step_5b,
}


def run_default_pipeline(paths: ActivePipelinePaths) -> None:
    """Run the active pipeline end to end through step 3B."""
    for step in DEFAULT_PIPELINE_STEPS:
        STEP_RUNNERS[step](paths)


def run_selected_step(paths: ActivePipelinePaths, step: str) -> None:
    """Run one selected active pipeline step."""
    try:
        step_runner = STEP_RUNNERS[step]
    except KeyError as exc:
        raise AwardPipelineError(f"Unknown step: {step}") from exc

    step_runner(paths)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the active pipeline wrapper."""
    parser = argparse.ArgumentParser(
        description="Run the active award extraction pipeline through step 3B."
    )
    parser.add_argument(
        "award_code",
        type=argparse_award_code,
        help="Award code such as MA000120.",
    )
    parser.add_argument(
        "step",
        nargs="?",
        choices=STEP_CHOICES,
        help="Optional step to run. If omitted, the pipeline runs through 3B.",
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
    """Run the active pipeline CLI through either one step or the default flow."""
    args = parse_args(argv)
    suffix = normalize_suffix(args.suffix)
    url = args.url or default_award_url_for_code(args.award_code)
    paths = build_paths(args.award_code, suffix, url)

    if args.step is None:
        run_default_pipeline(paths)
        return

    run_selected_step(paths, args.step)


if __name__ == "__main__":
    main()
