import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.Overtime_System_Prompt import OVERTIME_ENTITLEMENT_SYSTEM_PROMPT
from src.output_paths import (
    OVERTIME_ENTITLEMENTS_DIR,
    OVERTIME_INTERPRETATIONS_DIR,
    path_in_category,
    write_text_with_archive,
)
from src.payment_clause_classifier import extract_response_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERPRETATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / OVERTIME_INTERPRETATIONS_DIR
    / "MA000018_overtime_interpretation.md"
)
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "resources" / "overtime_example.md"
DEFAULT_MODEL = "gpt-5.4-mini"


class OvertimeEntitlementSummaryError(RuntimeError):
    """Base exception for overtime entitlement summary failures."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise OvertimeEntitlementSummaryError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_overtime_interpretation(interpretation_path: Path | str) -> str:
    path = Path(interpretation_path)
    if not path.exists():
        raise OvertimeEntitlementSummaryError(
            f"Overtime interpretation markdown not found: {path}"
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeEntitlementSummaryError(
            f"Overtime interpretation markdown is empty: {path}"
        )
    return text


def load_reference_template(template_path: Path | str) -> str:
    path = Path(template_path)
    if not path.exists():
        raise OvertimeEntitlementSummaryError(f"Reference template markdown not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise OvertimeEntitlementSummaryError(f"Reference template markdown is empty: {path}")
    return text


def output_path_for_interpretation(interpretation_path: Path | str) -> Path:
    path = Path(interpretation_path)
    stem = path.stem
    if stem.endswith("_overtime_interpretation"):
        stem = stem.removesuffix("_overtime_interpretation")
    return path_in_category(
        path,
        OVERTIME_ENTITLEMENTS_DIR,
        f"{stem}_overtime_entitlements.md",
    )


def output_path_for_classification(classification_path: Path | str) -> Path:
    """Return the entitlement output path for a classification path.

    Existing callers use this helper to plan downstream artifact locations before
    the interpretation file exists.
    """
    path = Path(classification_path)
    stem = path.stem
    if stem.endswith("_payment_classification"):
        stem = stem.removesuffix("_payment_classification")
    return path_in_category(
        path,
        OVERTIME_ENTITLEMENTS_DIR,
        f"{stem}_overtime_entitlements.md",
    )


def build_messages(
    source_file: str,
    interpretation_markdown: str,
    template_file: str,
    template_markdown: str,
) -> list[dict[str, str]]:
    user_prompt = (
        f"Source overtime interpretation working document: {source_file}\n\n"
        "Use this markdown template as the reference example for structure, formatting, "
        "wording style, and level of detail only. Do not copy its award-specific facts, "
        "clause references, rates, assumptions, employee categories, or rule outcomes. "
        "Generate the output from the source interpretation document.\n\n"
        f"Reference template: {template_file}\n\n"
        "```markdown\n"
        f"{template_markdown}\n"
        "```\n\n"
        "Overtime interpretation working document to convert:\n"
        "```markdown\n"
        f"{interpretation_markdown}"
        "\n```"
    )
    return [
        {"role": "system", "content": OVERTIME_ENTITLEMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def summarize_overtime_entitlements(
    interpretation_path: Path | str = DEFAULT_INTERPRETATION_PATH,
    output_path: Path | str | None = None,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    selected_model = model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)
    if client is None:
        load_environment()
        client = OpenAI()

    source_path = Path(interpretation_path)
    interpretation_text = load_overtime_interpretation(source_path)
    selected_template_path = Path(template_path)
    template_text = load_reference_template(selected_template_path)

    try:
        response = client.responses.create(
            model=selected_model,
            input=build_messages(
                str(source_path),
                interpretation_text,
                str(selected_template_path),
                template_text,
            ),
        )
    except Exception as exc:
        raise OvertimeEntitlementSummaryError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeEntitlementSummaryError("OpenAI response did not include output text.")

    destination = Path(output_path) if output_path else output_path_for_interpretation(source_path)
    write_text_with_archive(destination, output_text)
    return output_text


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise reviewer-facing overtime entitlements from an interpretation document."
    )
    parser.add_argument(
        "interpretation_path",
        nargs="?",
        default=str(DEFAULT_INTERPRETATION_PATH),
        help=(
            "Path to an overtime interpretation markdown file, for example "
            "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path for the markdown overtime entitlement summary.",
    )
    parser.add_argument(
        "--template-path",
        default=str(DEFAULT_TEMPLATE_PATH),
        help=(
            "Optional markdown template used as a style and structure reference. "
            f"Defaults to {DEFAULT_TEMPLATE_PATH}."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to OVERTIME_ENTITLEMENT_SUMMARY_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    summarize_overtime_entitlements(
        interpretation_path=args.interpretation_path,
        output_path=args.output_path,
        template_path=args.template_path,
        model=args.model,
    )
    destination = (
        Path(args.output_path)
        if args.output_path
        else output_path_for_interpretation(args.interpretation_path)
    )
    print(f"Overtime entitlement summary saved to {destination}")


if __name__ == "__main__":
    main()
