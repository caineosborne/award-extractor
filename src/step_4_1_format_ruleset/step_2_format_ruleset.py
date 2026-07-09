"""Step 4.1 stage 2: request and write the formatted ruleset."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.common.llm_io import extract_response_text
from src.common.output_paths import write_text_output
from src.common.pipeline_runtime import load_openai_environment
from src.prompts.step_4_1_format_ruleset import build_messages

from .schema import DEFAULT_MODEL, OvertimeEntitlementSummaryError
from .step_1_load_inputs import strip_wrapping_markdown_fence


def load_openai_client() -> OpenAI:
    """Load the OpenAI environment and return the step 4.1 client."""
    load_openai_environment(
        env_path=Path(__file__).resolve().parents[2] / ".env",
        error_type=OvertimeEntitlementSummaryError,
    )
    return OpenAI()


def resolve_model(model: str | None) -> str:
    """Resolve the configured step 4.1 model."""
    return model or os.getenv("OVERTIME_ENTITLEMENT_SUMMARY_MODEL", DEFAULT_MODEL)


def request_formatted_ruleset(
    *,
    client: Any,
    model: str,
    interpretation_path: Path,
    interpretation_markdown: str,
    template_path: Path,
    template_markdown: str,
    ruleset_key: str,
) -> str:
    """Request the formatted overtime guide from the model."""
    response = client.responses.create(
        model=model,
        input=build_messages(
            interpretation_path,
            interpretation_markdown,
            template_path,
            template_markdown,
            ruleset_key,
        ),
    )
    output_text = extract_response_text(response)
    if not output_text:
        raise OvertimeEntitlementSummaryError("OpenAI response did not include output text.")
    return output_text


def normalize_rule_text(text: str) -> str:
    """Normalize one rule string for comparison."""
    normalized_text = text.lower()
    normalized_text = normalized_text.replace("‑", "-")
    normalized_text = normalized_text.replace("–", "-")
    normalized_text = normalized_text.replace("—", "-")
    normalized_text = re.sub(r"\s+", " ", normalized_text)
    return normalized_text.strip()


def extract_markdown_bullets(markdown: str) -> list[str]:
    """Return the top-level markdown bullets from one ruleset."""
    bullets: list[str] = []

    for line in markdown.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("- "):
            bullets.append(stripped_line[2:].strip())

    return bullets


def extract_clause_references(rule_text: str) -> set[str]:
    """Return normalized clause references from one rule bullet."""
    clause_blocks = re.findall(r"\[([^\]]+)\]", rule_text)
    clause_references: set[str] = set()

    for clause_block in clause_blocks:
        for raw_clause in clause_block.split(","):
            clause_text = raw_clause.strip()
            if clause_text:
                clause_references.add(clause_text)

    return clause_references


def extract_significant_tokens(rule_text: str) -> set[str]:
    """Return meaningful tokens that should stay represented after formatting."""
    text_without_clause_blocks = re.sub(r"\[[^\]]+\]", " ", rule_text)
    normalized_text = normalize_rule_text(text_without_clause_blocks)
    raw_tokens = re.findall(r"\d+(?:\.\d+)?|[a-z]+", normalized_text)
    stopwords = {
        "a",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "if",
        "in",
        "is",
        "it",
        "may",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "under",
        "where",
        "whether",
        "which",
        "with",
        "worked",
        "work",
    }
    tokens: set[str] = set()

    for token in raw_tokens:
        if token.isdigit():
            tokens.add(token)
            continue

        if len(token) >= 4 and token not in stopwords:
            tokens.add(token)

    return tokens


def rule_is_represented_in_output(source_rule: str, formatted_rules: list[str]) -> bool:
    """Return whether one reviewed rule remains materially represented after formatting."""
    source_clauses = extract_clause_references(source_rule)
    source_tokens = extract_significant_tokens(source_rule)

    for formatted_rule in formatted_rules:
        formatted_clauses = extract_clause_references(formatted_rule)
        if source_clauses and source_clauses.isdisjoint(formatted_clauses):
            continue

        formatted_tokens = extract_significant_tokens(formatted_rule)
        if not source_tokens:
            return True

        shared_tokens = source_tokens & formatted_tokens
        overlap_ratio = len(shared_tokens) / len(source_tokens)

        if overlap_ratio >= 0.5:
            return True

    return False


def validate_formatted_ruleset_coverage(
    *,
    reviewed_ruleset_markdown: str,
    formatted_ruleset_markdown: str,
) -> list[str]:
    """Return warnings when step 4.1 appears to drop reviewed rules."""
    reviewed_rules = extract_markdown_bullets(reviewed_ruleset_markdown)
    formatted_rules = extract_markdown_bullets(formatted_ruleset_markdown)
    missing_rules: list[str] = []

    for reviewed_rule in reviewed_rules:
        if not rule_is_represented_in_output(reviewed_rule, formatted_rules):
            missing_rules.append(reviewed_rule)

    return [
        "Step 4.1 formatted output may have dropped this reviewed rule instead of only formatting it: "
        f"{rule}"
        for rule in missing_rules
    ]


def write_formatted_output(destination: Path, output_text: str) -> str:
    """Clean and write the formatted ruleset output."""
    cleaned_output = strip_wrapping_markdown_fence(output_text)
    write_text_output(destination, cleaned_output)
    return cleaned_output


def write_formatted_ruleset_metadata(
    *,
    destination: Path,
    source_path: Path,
    rendered_markdown: str,
    validation_warnings: list[str],
) -> None:
    """Persist formatted-ruleset warnings for the Streamlit review screens."""
    metadata = {
        "formatted_markdown_file": str(destination),
        "source_markdown_file": str(source_path),
        "rendered_markdown": rendered_markdown,
        "validation_warnings": validation_warnings,
    }
    metadata_path = destination.with_name(f"{destination.stem}_metadata.json")
    write_text_output(metadata_path, json.dumps(metadata, indent=2))
