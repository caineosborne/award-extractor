from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from src.common.active_pipeline_paths import (
    creator_response_path_for_interpretation,
    default_award_url_for_code,
    evaluator_feedback_path_for_interpretation,
    preferred_5b_source_path_for_interpretation,
    revised_output_path_for_interpretation,
    ruleset_clause_classification_output_path_for_classification,
    ruleset_output_path_for_classification,
    normalize_award_code,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
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
from src.step_1_1_fetch.run import fetch_award_source as run_step_1_1_fetch
from src.step_1_2_parse_award.run import (
    write_html_outputs_for_paths as run_step_1_2_parse_award,
)
from src.step_2_1_classify_payments.run import classify_payments as run_step_2_1_classify
from src.step_2_2_classify_overtime_clauses.run import (
    run_step_2_2 as run_step_2_2_classify_overtime_clauses,
)
from src.step_3_1_generate_ruleset.core import DEFAULT_EXPERT_RUN_COUNT
from src.step_3_1_generate_ruleset.run import (
    generate_ruleset_from_clause_classification as run_step_3_1_generate_ruleset,
)
from src.step_3_2_review_ruleset.run import review_ruleset as run_step_3_2_review_ruleset
from src.step_4_1_format_ruleset import output_path_for_interpretation
from src.step_4_1_format_ruleset.run import (
    summarize_overtime_entitlements as run_step_4_1_format_ruleset,
)
from src.step_5_1_generate_pseudocode.deterministic import output_path_for_summary
from src.step_5_1_generate_pseudocode.run import (
    generate_core_overtime_pseudocode as run_step_5_1_generate_pseudocode,
)

STEP_CHOICES = ACTIVE_PIPELINE_STEP_CHOICES
DEFAULT_PIPELINE_STEPS = DEFAULT_ACTIVE_PIPELINE_STEPS
RULESET_SPECIFIC_STEPS = ("3.1", "3.2", "4.1", "5.1")
SHARED_PIPELINE_STEPS = ("1", "2.1", "2.2")
RULESET_SUBSET_TO_KEY = {
    "1": OVERTIME_CREATION_RULESET,
    "2": OVERTIME_CONSEQUENCE_RULESET,
}
RULESET_SUBSET_CHOICES = tuple(RULESET_SUBSET_TO_KEY.keys())
CLI_DEFAULT_RULESET_KEYS = tuple(RULESET_SUBSET_TO_KEY.values())


class AwardPipelineError(RuntimeError):
    """Raised when the wrapper cannot resolve the requested pipeline state."""

ActivePipelinePaths = ActivePipelineContext


@dataclass(frozen=True)
class RulesetStepPaths:
    """Artifact paths for one explicit ruleset run."""

    clause_classification_path: Path
    interpretation_path: Path
    evaluator_feedback_path: Path
    creator_response_path: Path
    revised_interpretation_path: Path
    formatted_ruleset_path: Path
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
    try:
        return normalize_output_suffix(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def deduplicate_preserving_order(values: list[str]) -> list[str]:
    """Return one list with duplicates removed and order preserved."""
    unique_values: list[str] = []

    for value in values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values


def resolve_cli_ruleset_keys(subset_ids: list[str] | None) -> list[str]:
    """Resolve CLI subset ids into the explicit ruleset keys to run."""
    if subset_ids is None:
        return list(CLI_DEFAULT_RULESET_KEYS)

    ruleset_keys = [RULESET_SUBSET_TO_KEY[subset_id] for subset_id in subset_ids]
    return deduplicate_preserving_order(ruleset_keys)


def build_ruleset_step_paths(
    paths: ActivePipelinePaths,
    ruleset_key: str,
) -> RulesetStepPaths:
    """Build the explicit artifact paths for one ruleset-specific run."""
    interpretation_path = ruleset_output_path_for_classification(
        paths.classification_path,
        ruleset_key,
    )
    revised_interpretation_path = revised_output_path_for_interpretation(
        interpretation_path
    )
    core_overtime_pseudocode_path = output_path_for_summary(revised_interpretation_path)

    return RulesetStepPaths(
        clause_classification_path=ruleset_clause_classification_output_path_for_classification(
            paths.classification_path,
            ruleset_key,
        ),
        interpretation_path=interpretation_path,
        evaluator_feedback_path=evaluator_feedback_path_for_interpretation(
            interpretation_path
        ),
        creator_response_path=creator_response_path_for_interpretation(
            interpretation_path
        ),
        revised_interpretation_path=revised_interpretation_path,
        formatted_ruleset_path=output_path_for_interpretation(
            revised_interpretation_path
        ),
        core_overtime_pseudocode_path=core_overtime_pseudocode_path,
        core_overtime_validation_json_path=core_overtime_pseudocode_path.with_name(
            f"{core_overtime_pseudocode_path.stem}_validation.json"
        ),
        core_overtime_validation_markdown_path=core_overtime_pseudocode_path.with_name(
            f"{core_overtime_pseudocode_path.stem}_validation.md"
        ),
    )


def ruleset_manual_4b_path(revised_interpretation_path: Path) -> Path:
    """Return the ruleset-specific manual 4B path for one revised ruleset file."""
    stem = revised_interpretation_path.stem
    if stem.endswith("_revised"):
        stem = stem.removesuffix("_revised")
    return revised_interpretation_path.with_name(f"{stem}_4b.md")


def preferred_ruleset_step_5_source_path(ruleset_paths: RulesetStepPaths) -> Path:
    """Return the preferred step 5.1 source for one explicit ruleset."""
    manual_4b_path = ruleset_manual_4b_path(ruleset_paths.revised_interpretation_path)
    if manual_4b_path.exists():
        return manual_4b_path

    if ruleset_paths.formatted_ruleset_path.exists():
        return ruleset_paths.formatted_ruleset_path

    revised_json_path = ruleset_paths.revised_interpretation_path.with_suffix(".json")
    if revised_json_path.exists():
        return revised_json_path

    return ruleset_paths.revised_interpretation_path


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
    result = run_step_1_1_fetch(paths.url)
    run_step_1_2_parse_award(
        main_content=result.main_content,
        award=result.award,
        raw_html_path=paths.raw_html_path,
        award_json_path=paths.award_json_path,
    )


def run_step_2_1(paths: ActivePipelinePaths) -> None:
    """Run step 2.1 payment clause classification."""
    require_existing(paths.award_json_path, "2.1", "1")
    run_step_2_1_classify(
        award_path=paths.award_json_path,
        output_path=paths.classification_path,
    )


def run_step_2_2(paths: ActivePipelinePaths) -> None:
    """Run step 2.2 overtime clause classification."""
    require_existing(paths.classification_path, "2.2", "2.1")
    run_step_2_2_classify_overtime_clauses(
        classification_path=paths.classification_path,
        output_path=paths.overtime_clause_classification_path,
    )


def run_step_3_1(
    paths: ActivePipelinePaths,
    ruleset_key: str | None = None,
) -> None:
    """Run step 3.1 ruleset generation."""
    require_existing(paths.classification_path, "3.1", "2.1")
    if ruleset_key is None:
        clause_classification_path = paths.overtime_clause_classification_path
        interpretation_path = paths.interpretation_path
        active_ruleset_key = OVERTIME_CREATION_RULESET
    else:
        ruleset_paths = build_ruleset_step_paths(paths, ruleset_key)
        clause_classification_path = ruleset_paths.clause_classification_path
        interpretation_path = ruleset_paths.interpretation_path
        active_ruleset_key = ruleset_key

    require_existing(clause_classification_path, "3.1", "2.2")
    run_step_3_1_generate_ruleset(
        classification_path=paths.classification_path,
        output_path=interpretation_path,
        classification_output_path=clause_classification_path,
        expert_run_count=DEFAULT_EXPERT_RUN_COUNT,
        ruleset_key=active_ruleset_key,
    )


def run_step_3_2(
    paths: ActivePipelinePaths,
    ruleset_key: str | None = None,
) -> None:
    """Run step 3.2 one-pass review of the interpretation output."""
    require_existing(paths.classification_path, "3.2", "2.1")
    if ruleset_key is None:
        clause_classification_path = paths.overtime_clause_classification_path
        interpretation_path = paths.interpretation_path
        feedback_output_path = paths.evaluator_feedback_path
        creator_response_output_path = paths.creator_response_path
        revised_output_path = paths.revised_interpretation_path
        active_ruleset_key = None
    else:
        ruleset_paths = build_ruleset_step_paths(paths, ruleset_key)
        clause_classification_path = ruleset_paths.clause_classification_path
        interpretation_path = ruleset_paths.interpretation_path
        feedback_output_path = ruleset_paths.evaluator_feedback_path
        creator_response_output_path = ruleset_paths.creator_response_path
        revised_output_path = ruleset_paths.revised_interpretation_path
        active_ruleset_key = ruleset_key

    require_existing(clause_classification_path, "3.2", "3.1")
    require_existing(interpretation_path, "3.2", "3.1")
    if active_ruleset_key is None:
        run_step_3_2_review_ruleset(
            interpretation_path=interpretation_path,
            classification_path=paths.classification_path,
            overtime_clause_classification_path=clause_classification_path,
            feedback_output_path=feedback_output_path,
            creator_response_output_path=creator_response_output_path,
            revised_output_path=revised_output_path,
        )
        return

    run_step_3_2_review_ruleset(
        interpretation_path=interpretation_path,
        classification_path=paths.classification_path,
        overtime_clause_classification_path=clause_classification_path,
        feedback_output_path=feedback_output_path,
        creator_response_output_path=creator_response_output_path,
        revised_output_path=revised_output_path,
        ruleset_key=active_ruleset_key,
    )


def run_step_5_1(
    paths: ActivePipelinePaths,
    ruleset_key: str | None = None,
) -> None:
    """Run step 5.1 core overtime pseudocode generation."""
    if ruleset_key is None:
        revised_interpretation_path = paths.revised_interpretation_path
        core_overtime_pseudocode_path = paths.core_overtime_pseudocode_path
        core_overtime_validation_json_path = paths.core_overtime_validation_json_path
        core_overtime_validation_markdown_path = (
            paths.core_overtime_validation_markdown_path
        )
        source_path = preferred_5b_source_path_for_interpretation(
            revised_interpretation_path
        )
    else:
        ruleset_paths = build_ruleset_step_paths(paths, ruleset_key)
        revised_interpretation_path = ruleset_paths.revised_interpretation_path
        core_overtime_pseudocode_path = ruleset_paths.core_overtime_pseudocode_path
        core_overtime_validation_json_path = (
            ruleset_paths.core_overtime_validation_json_path
        )
        core_overtime_validation_markdown_path = (
            ruleset_paths.core_overtime_validation_markdown_path
        )
        source_path = preferred_ruleset_step_5_source_path(ruleset_paths)

    require_existing(revised_interpretation_path, "5.1", "3.2")
    if ruleset_key is None:
        run_step_5_1_generate_pseudocode(
            summary_path=source_path,
            output_path=core_overtime_pseudocode_path,
        )
    else:
        run_step_5_1_generate_pseudocode(
            summary_path=source_path,
            output_path=core_overtime_pseudocode_path,
            ruleset_key=ruleset_key,
        )
    print(f"Core overtime pseudocode saved to {core_overtime_pseudocode_path}")
    print(
        "Step 5.1 validation JSON saved to "
        f"{core_overtime_validation_json_path}"
    )
    print(
        "Step 5.1 validation markdown saved to "
        f"{core_overtime_validation_markdown_path}"
    )


def run_step_4_1(
    paths: ActivePipelinePaths,
    ruleset_key: str | None = None,
) -> None:
    """Run step 4.1 formatted ruleset generation."""
    if ruleset_key is None:
        revised_interpretation_path = paths.revised_interpretation_path
        formatted_ruleset_path = None
        active_ruleset_key = None
    else:
        ruleset_paths = build_ruleset_step_paths(paths, ruleset_key)
        revised_interpretation_path = ruleset_paths.revised_interpretation_path
        formatted_ruleset_path = ruleset_paths.formatted_ruleset_path
        active_ruleset_key = ruleset_key

    require_existing(revised_interpretation_path, "4.1", "3.2")
    if active_ruleset_key is None:
        run_step_4_1_format_ruleset(
            interpretation_path=revised_interpretation_path,
        )
        return

    run_step_4_1_format_ruleset(
        interpretation_path=revised_interpretation_path,
        output_path=formatted_ruleset_path,
        ruleset_key=active_ruleset_key,
    )


STEP_RUNNERS = {
    "1": run_step_1,
    "2.1": run_step_2_1,
    "2.2": run_step_2_2,
    "3.1": run_step_3_1,
    "3.2": run_step_3_2,
    "4.1": run_step_4_1,
    "5.1": run_step_5_1,
}


def run_default_pipeline(
    paths: ActivePipelinePaths,
    ruleset_keys: list[str] | None = None,
) -> None:
    """Run the active pipeline end to end through step 5.1."""
    if ruleset_keys is None:
        for step in DEFAULT_PIPELINE_STEPS:
            STEP_RUNNERS[step](paths)
        return

    for step in SHARED_PIPELINE_STEPS:
        STEP_RUNNERS[step](paths)

    for ruleset_key in deduplicate_preserving_order(ruleset_keys):
        for step in RULESET_SPECIFIC_STEPS:
            STEP_RUNNERS[step](paths, ruleset_key)


def run_selected_ruleset_steps(
    paths: ActivePipelinePaths,
    step: str,
    ruleset_keys: list[str],
) -> None:
    """Run one ruleset-specific step for each selected ruleset."""
    for ruleset_key in deduplicate_preserving_order(ruleset_keys):
        STEP_RUNNERS[step](paths, ruleset_key)


def run_selected_step(
    paths: ActivePipelinePaths,
    step: str,
    ruleset_keys: list[str] | None = None,
) -> None:
    """Run one selected active pipeline step."""
    if step in RULESET_SPECIFIC_STEPS and ruleset_keys is not None:
        run_selected_ruleset_steps(paths, step, ruleset_keys)
        return

    try:
        step_runner = STEP_RUNNERS[step]
    except KeyError as exc:
        raise AwardPipelineError(f"Unknown step: {step}") from exc

    step_runner(paths)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the active pipeline wrapper."""
    parser = argparse.ArgumentParser(
        description="Run the active award extraction pipeline through step 5.1."
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
        help="Optional step to run. If omitted, the pipeline runs through 5.1.",
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
    parser.add_argument(
        "--subset",
        nargs="+",
        choices=RULESET_SUBSET_CHOICES,
        default=None,
        help=(
            "Optional ruleset subset ids to run. "
            "Use 1 for overtime creation, 2 for overtime consequence. "
            "If omitted, the CLI runs all configured rulesets."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the active pipeline CLI through either one step or the default flow."""
    args = parse_args(argv)
    suffix = normalize_suffix(args.suffix)
    url = args.url or default_award_url_for_code(args.award_code)
    paths = build_paths(args.award_code, suffix, url)
    selected_ruleset_keys = resolve_cli_ruleset_keys(args.subset)

    if args.step is None:
        run_default_pipeline(paths, selected_ruleset_keys)
        return

    run_selected_step(paths, args.step, selected_ruleset_keys)


if __name__ == "__main__":
    main()
