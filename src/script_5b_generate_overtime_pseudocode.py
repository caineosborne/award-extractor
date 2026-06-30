"""Step 5B core overtime pseudocode generator.

Prompt ownership:
- Uses `src/prompts/core_overtime_pseudocode.py`.

Validation dependency:
- Uses `src/script_5b_validate_overtime_pseudocode.py` for deterministic coverage checks.
"""

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.common.active_pipeline_paths import looks_like_path
from src.common.llm_io import extract_response_text
from src.common.output_paths import award_output_dir, write_text_with_archive
from src.common.overtime_rules import (
    OVERTIME_RULE_SCHEMA_VERSION,
    build_rule_inventory_from_rules,
    json_output_path_for_markdown,
    load_rules_artifact,
    rules_from_markdown_fallback,
)
from src.common.overtime_rulesets import (
    OVERTIME_CONSEQUENCE_RULESET,
    OVERTIME_CREATION_RULESET,
    infer_overtime_ruleset_key_from_path,
)
from src.common.rule_inventory import RuleInventory
from src.prompts.core_overtime_pseudocode import (
    PSEUDOCODE_FIELDS as PROMPT_PSEUDOCODE_FIELDS,
    build_messages as prompt_build_messages,
    build_repair_messages as prompt_build_repair_messages,
)
from src.script_5b_validate_overtime_pseudocode import (
    validation_json_path_for_pseudocode,
    validation_markdown_path_for_pseudocode,
    validate_overtime_pseudocode_against_inventory,
    write_validation_artifacts,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERTIME_SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "MA000018"
    / "MA000018_overtime_interpretation_revised.md"
)
DEFAULT_MODEL = "gpt-5.4-mini"
MAX_VALIDATION_REPAIR_ATTEMPTS = 1
RULESET_CHOICES = (
    OVERTIME_CREATION_RULESET,
    OVERTIME_CONSEQUENCE_RULESET,
)

PSEUDOCODE_FIELDS = PROMPT_PSEUDOCODE_FIELDS
build_messages = prompt_build_messages
build_repair_messages = prompt_build_repair_messages

class CoreOvertimePseudocodeError(RuntimeError):
    """Base exception for core overtime pseudocode failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise CoreOvertimePseudocodeError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def entitlement_path_for_award(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_entitlements.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        return award_dir / f"{award_code}_overtime_creation_ruleset_overtime_entitlements.md"
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        return award_dir / f"{award_code}_overtime_consequence_ruleset_overtime_entitlements.md"
    return award_dir / f"{award_code}_overtime_entitlements.md"


def fallback_source_paths_for_path(path: Path) -> list[Path]:
    stem = path.stem

    if stem.endswith("_overtime_interpretation_4b"):
        base_stem = stem.removesuffix("_overtime_interpretation_4b")
        return [
            path,
            path.with_name(f"{base_stem}_overtime_entitlements.md"),
            path.with_name(f"{base_stem}_overtime_interpretation_revised.md"),
            path.with_name(f"{base_stem}_overtime_interpretation.md"),
        ]

    if stem.endswith("_overtime_creation_ruleset_revised"):
        base_stem = stem.removesuffix("_overtime_creation_ruleset_revised")
        return [
            path.with_name(f"{base_stem}_overtime_creation_ruleset_overtime_entitlements.md"),
            path,
            path.with_name(f"{base_stem}_overtime_creation_ruleset.md"),
        ]

    if stem.endswith("_overtime_consequence_ruleset_revised"):
        base_stem = stem.removesuffix("_overtime_consequence_ruleset_revised")
        return [
            path.with_name(
                f"{base_stem}_overtime_consequence_ruleset_overtime_entitlements.md"
            ),
            path,
            path.with_name(f"{base_stem}_overtime_consequence_ruleset.md"),
        ]

    if stem.endswith("_overtime_creation_ruleset_overtime_entitlements"):
        base_stem = stem.removesuffix("_overtime_creation_ruleset_overtime_entitlements")
        return [
            path,
            path.with_name(f"{base_stem}_overtime_creation_ruleset_revised.md"),
            path.with_name(f"{base_stem}_overtime_creation_ruleset.md"),
        ]

    if stem.endswith("_overtime_consequence_ruleset_overtime_entitlements"):
        base_stem = stem.removesuffix(
            "_overtime_consequence_ruleset_overtime_entitlements"
        )
        return [
            path,
            path.with_name(f"{base_stem}_overtime_consequence_ruleset_revised.md"),
            path.with_name(f"{base_stem}_overtime_consequence_ruleset.md"),
        ]

    if stem.endswith("_overtime_entitlements"):
        base_stem = stem.removesuffix("_overtime_entitlements")
        award_dir = award_output_dir(path)
        return [
            path,
            award_dir / f"{base_stem}_overtime_interpretation_revised.md",
            award_dir / f"{base_stem}_overtime_interpretation.md",
        ]

    if stem.endswith("_overtime_interpretation_revised"):
        base_stem = stem.removesuffix("_overtime_interpretation_revised")
        return [
            path,
            path.with_name(f"{base_stem}_overtime_interpretation.md"),
        ]

    return [path]


def select_overtime_interpretation_path(
    source_path: Path | str = DEFAULT_OVERTIME_SUMMARY_PATH,
    ruleset_key: str | None = None,
) -> Path:
    selected_source = str(source_path)
    if looks_like_path(selected_source):
        candidate_paths = fallback_source_paths_for_path(Path(selected_source))
    else:
        candidate_paths = [default_overtime_interpretation_path(selected_source, ruleset_key)]

    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path

    raise CoreOvertimePseudocodeError(
        f"Overtime interpretation markdown not found. Checked: "
        + ", ".join(str(path) for path in candidate_paths)
    )


def default_overtime_interpretation_path(
    award_code: str,
    ruleset_key: str | None = None,
) -> Path:
    processed_root = PROJECT_ROOT / "data" / "processed"
    award_dir = award_output_dir(processed_root / f"{award_code}_overtime_interpretation.md")
    if ruleset_key == OVERTIME_CREATION_RULESET:
        entitlement_path = entitlement_path_for_award(award_code, ruleset_key)
        if entitlement_path.exists():
            return entitlement_path
        revised_path = award_dir / f"{award_code}_overtime_creation_ruleset_revised.md"
        if revised_path.exists():
            return revised_path
        return award_dir / f"{award_code}_overtime_creation_ruleset.md"
    if ruleset_key == OVERTIME_CONSEQUENCE_RULESET:
        entitlement_path = entitlement_path_for_award(award_code, ruleset_key)
        if entitlement_path.exists():
            return entitlement_path
        revised_path = award_dir / f"{award_code}_overtime_consequence_ruleset_revised.md"
        if revised_path.exists():
            return revised_path
        return award_dir / f"{award_code}_overtime_consequence_ruleset.md"
    manual_4b_path = award_dir / f"{award_code}_overtime_interpretation_4b.md"
    if manual_4b_path.exists():
        return manual_4b_path

    entitlement_path = entitlement_path_for_award(award_code)
    if entitlement_path.exists():
        return entitlement_path

    revised_path = award_dir / f"{award_code}_overtime_interpretation_revised.md"
    if revised_path.exists():
        return revised_path

    return award_dir / f"{award_code}_overtime_interpretation.md"


def source_stage_for_path(path: Path) -> str:
    stem = path.stem

    if stem.endswith("_overtime_interpretation_4b"):
        return "4b"
    if stem.endswith("_overtime_creation_ruleset_overtime_entitlements"):
        return "4a"
    if stem.endswith("_overtime_consequence_ruleset_overtime_entitlements"):
        return "4a"
    if stem.endswith("_overtime_entitlements"):
        return "4a"
    if stem.endswith("_overtime_creation_ruleset_revised"):
        return "3b"
    if stem.endswith("_overtime_consequence_ruleset_revised"):
        return "3b"
    if stem.endswith("_overtime_interpretation_revised"):
        return "3b"
    return "3"


def load_overtime_interpretation(source_path: Path | str) -> str:
    path = select_overtime_interpretation_path(source_path)
    if not path.exists():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown not found: {path}"
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation markdown is empty: {path}"
        )
    return text


def load_overtime_rules(source_path: Path | str) -> dict[str, Any]:
    path = select_overtime_interpretation_path(source_path)
    json_path = json_output_path_for_markdown(path)
    if not json_path.exists():
        markdown_text = load_overtime_interpretation(path)
        return {
            "schema_version": OVERTIME_RULE_SCHEMA_VERSION,
            "rendered_markdown": markdown_text,
            "rules": rules_from_markdown_fallback(markdown_text, source_path=path),
        }
    try:
        return load_rules_artifact(
            json_path,
            expected_schema_version=OVERTIME_RULE_SCHEMA_VERSION,
        )
    except ValueError as exc:
        raise CoreOvertimePseudocodeError(
            f"Overtime interpretation rules JSON is invalid: {json_path}"
        ) from exc


def first_top_level_bullets(markdown: str, count: int = 5) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- "):
            if current:
                selected.append("\n".join(current))
                if len(selected) == count:
                    break
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)

    if len(selected) < count and current:
        selected.append("\n".join(current))

    if len(selected) < count:
        raise CoreOvertimePseudocodeError(
            f"Expected at least {count} top-level bullets, found {len(selected)}."
        )

    return "\n".join(selected[:count])


def overtime_rule_bullets(markdown: str) -> str:
    selected: list[str] = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.startswith("- Overtime - "):
            if current:
                selected.append("\n".join(current))
            current = [line]
            continue

        if current and (line.startswith("  ") or not line.strip()):
            current.append(line)
            continue

        if current and line.startswith("- "):
            selected.append("\n".join(current))
            current = []

    if current:
        selected.append("\n".join(current))

    if not selected:
        raise CoreOvertimePseudocodeError(
            "Expected at least one top-level 'Overtime - ' entitlement bullet."
        )

    return "\n".join(selected)


def output_path_for_summary(summary_path: Path | str) -> Path:
    path = Path(summary_path)
    stem = path.stem
    if stem.endswith("_overtime_creation_ruleset_overtime_entitlements"):
        stem = stem.removesuffix("_overtime_creation_ruleset_overtime_entitlements")
        return path.with_name(f"{stem}_overtime_creation_ruleset_core_overtime_pseudocode.md")
    elif stem.endswith("_overtime_consequence_ruleset_overtime_entitlements"):
        stem = stem.removesuffix("_overtime_consequence_ruleset_overtime_entitlements")
        return path.with_name(
            f"{stem}_overtime_consequence_ruleset_core_overtime_pseudocode.md"
        )
    elif stem.endswith("_overtime_creation_ruleset_revised"):
        stem = stem.removesuffix("_overtime_creation_ruleset_revised")
        return path.with_name(f"{stem}_overtime_creation_ruleset_core_overtime_pseudocode.md")
    elif stem.endswith("_overtime_consequence_ruleset_revised"):
        stem = stem.removesuffix("_overtime_consequence_ruleset_revised")
        return path.with_name(
            f"{stem}_overtime_consequence_ruleset_core_overtime_pseudocode.md"
        )
    if stem.endswith("_overtime_interpretation_4b"):
        stem = stem.removesuffix("_overtime_interpretation_4b")
    elif stem.endswith("_overtime_entitlements"):
        stem = stem.removesuffix("_overtime_entitlements")
    elif stem.endswith("_overtime_interpretation_revised"):
        stem = stem.removesuffix("_overtime_interpretation_revised")
    elif stem.endswith("_overtime_interpretation"):
        stem = stem.removesuffix("_overtime_interpretation")
    return award_output_dir(path) / f"{stem}_core_overtime_pseudocode.md"


def request_pseudocode_output(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    try:
        response = client.responses.create(
            model=model,
            input=messages,
        )
    except Exception as exc:
        raise CoreOvertimePseudocodeError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise CoreOvertimePseudocodeError("OpenAI response did not include output text.")

    if output_text.endswith("\n"):
        return output_text
    return output_text + "\n"


def generate_core_overtime_pseudocode(
    summary_path: Path | str = DEFAULT_OVERTIME_SUMMARY_PATH,
    output_path: Path | str | None = None,
    model: str | None = None,
    client: Any | None = None,
    ruleset_key: str | None = None,
) -> str:
    selected_model = model or os.getenv("CORE_OVERTIME_PSEUDOCODE_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = select_overtime_interpretation_path(summary_path, ruleset_key)
    try:
        effective_ruleset_key = ruleset_key or infer_overtime_ruleset_key_from_path(
            source_path
        )
    except ValueError:
        effective_ruleset_key = OVERTIME_CREATION_RULESET
    rules_artifact = load_overtime_rules(source_path)
    summary_text = str(rules_artifact["rendered_markdown"])
    source_inventory = build_rule_inventory_from_rules(
        rules_artifact["rules"],
        source_path=source_path,
        inventory_name="reviewed_overtime_rules",
        source_stage=source_stage_for_path(source_path),
        domain="overtime",
    )

    destination = Path(output_path) if output_path else output_path_for_summary(source_path)
    output_text = request_pseudocode_output(
        client=client,
        model=selected_model,
        messages=build_messages(
            str(source_path),
            summary_text,
            source_inventory,
            effective_ruleset_key,
        ),
    )

    repair_attempts = 0

    while True:
        write_text_with_archive(destination, output_text)
        validation_report = validate_overtime_pseudocode_against_inventory(
            source_inventory,
            output_text,
            target_path=destination,
        )
        validation_markdown = write_validation_artifacts(
            validation_report,
            json_path=validation_json_path_for_pseudocode(destination),
            markdown_path=validation_markdown_path_for_pseudocode(destination),
        )[1].read_text(encoding="utf-8")

        needs_repair = (
            validation_report.failed_rule_count > 0
            and repair_attempts < MAX_VALIDATION_REPAIR_ATTEMPTS
        )
        if not needs_repair:
            return output_text

        repair_attempts += 1
        output_text = request_pseudocode_output(
            client=client,
            model=selected_model,
            messages=build_repair_messages(
                source_file=str(source_path),
                overtime_summary_markdown=summary_text,
                source_inventory=source_inventory,
                initial_pseudocode_markdown=output_text,
                validation_report_markdown=validation_markdown,
                ruleset_key=effective_ruleset_key,
            ),
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate core ordinary/overtime pseudocode from an overtime entitlement summary."
    )
    parser.add_argument(
        "summary_path",
        nargs="?",
        default=str(default_overtime_interpretation_path("MA000018")),
        help=(
            "Award code or path to an overtime interpretation markdown file. "
            "When an award code is provided, use the 4B file when present, otherwise 4A, then the revised overtime interpretation."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown core overtime pseudocode output.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to CORE_OVERTIME_PSEUDOCODE_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--ruleset-key",
        choices=RULESET_CHOICES,
        default=None,
        help="Optional ruleset key when resolving an award code input.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    selected_source_path = select_overtime_interpretation_path(
        args.summary_path,
        args.ruleset_key,
    )
    generate_core_overtime_pseudocode(
        summary_path=args.summary_path,
        output_path=args.output_path,
        model=args.model,
        ruleset_key=args.ruleset_key,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_summary(selected_source_path)
    )
    print(f"Core overtime pseudocode saved to {destination}")
    print(
        "Validation report saved to "
        f"{validation_markdown_path_for_pseudocode(destination)}"
    )


if __name__ == "__main__":
    main()
