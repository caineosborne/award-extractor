from __future__ import annotations

import argparse
from pathlib import Path

from src.common.active_pipeline_paths import (
    default_award_url_for_code,
    preferred_5b_source_path_for_interpretation,
    normalize_award_code,
)
from src.common.output_naming import (
    ACTIVE_PIPELINE_STEP_CHOICES,
    DEFAULT_ACTIVE_PIPELINE_STEPS,
    normalize_output_suffix,
    output_stem_for_award,
)
from src.common.pipeline_context import (
    ActivePipelineContext,
    build_active_pipeline_context,
)
from src.step_1_1_fetch.run import fetch_award_source
from src.step_1_2_parse_award.run import write_html_outputs_for_paths
from src.script_3_interpret_overtime import DEFAULT_EXPERT_RUN_COUNT
from src.step_2_1_classify_payments.run import classify_payments
from src.step_3_1_generate_ruleset.run import (
    generate_ruleset_from_clause_classification,
)
from src.step_3_2_review_ruleset.run import review_ruleset
from src.step_4_1_format_ruleset.run import summarize_overtime_entitlements
from src.step_5_1_generate_pseudocode.run import (
    generate_core_overtime_pseudocode,
)
from src.step_2_2_classify_overtime_clauses.run import (
    run_step_2_1 as run_overtime_clause_classification_step,
)

STEP_CHOICES = ACTIVE_PIPELINE_STEP_CHOICES
DEFAULT_PIPELINE_STEPS = DEFAULT_ACTIVE_PIPELINE_STEPS


class AwardPipelineError(RuntimeError):
    """Raised when the wrapper cannot resolve the requested pipeline state."""

ActivePipelinePaths = ActivePipelineContext


def argparse_award_code(value: str) -> str:
    """Adapt award code validation for argparse error reporting."""
    try:
        return normalize_award_code(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def normalize_suffix(value: str | None) -> str | None:
    """Normalize an optional filename suffix used for pipeline outputs."""
    try:
        return normalize_output_suffix(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_paths(award_code: str, suffix: str | None, url: str) -> ActivePipelinePaths:
    """Build all active-step artifact paths for one pipeline run."""
    return build_active_pipeline_context(
        award_code=award_code,
        suffix=suffix,
        url=url,
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
    result = fetch_award_source(paths.url)
    write_html_outputs_for_paths(
        main_content=result.main_content,
        award=result.award,
        raw_html_path=paths.raw_html_path,
        award_json_path=paths.award_json_path,
    )


def run_step_2_1(paths: ActivePipelinePaths) -> None:
    """Run step 2.1 payment clause classification."""
    require_existing(paths.award_json_path, "2.1", "1")
    classify_payments(
        award_path=paths.award_json_path,
        output_path=paths.classification_path,
    )


def run_step_2_2(paths: ActivePipelinePaths) -> None:
    """Run step 2.2 overtime clause classification."""
    require_existing(paths.classification_path, "2.2", "2.1")
    run_overtime_clause_classification_step(
        classification_path=paths.classification_path,
        output_path=paths.overtime_clause_classification_path,
    )


def run_step_3(paths: ActivePipelinePaths) -> None:
    """Run step 3 overtime interpretation generation."""
    require_existing(paths.classification_path, "3", "2.1")
    require_existing(paths.overtime_clause_classification_path, "3", "2.2")
    generate_ruleset_from_clause_classification(
        classification_path=paths.classification_path,
        output_path=paths.interpretation_path,
        classification_output_path=paths.overtime_clause_classification_path,
        expert_run_count=DEFAULT_EXPERT_RUN_COUNT,
        ruleset_key="overtime_creation",
    )


def run_step_3b(paths: ActivePipelinePaths) -> None:
    """Run step 3B one-pass review of the interpretation output."""
    require_existing(paths.classification_path, "3b", "2.1")
    require_existing(paths.overtime_clause_classification_path, "3b", "3")
    require_existing(paths.interpretation_path, "3b", "3")
    review_ruleset(
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


def run_step_4(paths: ActivePipelinePaths) -> None:
    """Run step 4 formatted overtime guide generation."""
    require_existing(paths.revised_interpretation_path, "4", "3b")
    summarize_overtime_entitlements(
        interpretation_path=paths.revised_interpretation_path,
    )


STEP_RUNNERS = {
    "1": run_step_1,
    "2.1": run_step_2_1,
    "2.2": run_step_2_2,
    "3": run_step_3,
    "3b": run_step_3b,
    "4": run_step_4,
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
