import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.Archive.award_interpreter_prompt import SYSTEM_PROMPT


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "MA000018_sections.json"
DEFAULT_MODEL = "gpt-5.4"


class AwardInterpreterError(RuntimeError):
    """Base exception for award interpreter failures."""


class ClauseNotFoundError(AwardInterpreterError):
    """Raised when a clause reference does not exist in the section index."""


def load_environment(env_path: Path | str = PROJECT_ROOT / ".env") -> None:
    load_dotenv(env_path)
    if not os.getenv("OPENAI_API_KEY"):
        raise AwardInterpreterError(
            "OPENAI_API_KEY is not set. Add it to the root .env file or export it."
        )


def load_sections(sections_path: Path | str = DEFAULT_SECTIONS_PATH) -> dict[str, Any]:
    path = Path(sections_path)
    if not path.exists():
        raise AwardInterpreterError(f"Section index not found: {path}")

    try:
        with path.open(encoding="utf-8") as sections_file:
            sections = json.load(sections_file)
    except json.JSONDecodeError as exc:
        raise AwardInterpreterError(f"Section index is not valid JSON: {path}") from exc

    if not isinstance(sections, dict):
        raise AwardInterpreterError(f"Section index must contain a JSON object: {path}")

    return sections


def get_clause_node(clause_reference: str, sections: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized_reference = clause_reference.strip()
    clause_node = sections.get(normalized_reference)
    if clause_node is None:
        raise ClauseNotFoundError(f"Clause reference not found: {normalized_reference}")
    if not isinstance(clause_node, Mapping):
        raise AwardInterpreterError(
            f"Clause reference {normalized_reference} does not contain a clause object."
        )
    return clause_node


def flatten_clause(clause_reference: str, clause_node: Mapping[str, Any]) -> str:
    lines: list[str] = []

    def walk(node: Mapping[str, Any], label: str) -> None:
        content = node.get("_content", [])
        if isinstance(content, list):
            for item in content:
                lines.append(f"{label}: {format_content_item(item)}")
        elif content:
            lines.append(f"{label}: {format_content_item(content)}")

        for key, value in node.items():
            if key == "_content" or not isinstance(value, Mapping):
                continue
            child_label = format_child_label(label, str(key))
            walk(value, child_label)

    walk(clause_node, clause_reference.strip())
    return "\n".join(line for line in lines if line.strip())


def format_child_label(parent_label: str, child_key: str) -> str:
    if len(child_key) <= 3 and child_key.isalpha():
        return f"{parent_label}({child_key})"
    return child_key


def format_content_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    return json.dumps(item, ensure_ascii=False)


def build_user_prompt(
    clause_reference: str,
    clause_text: str,
    guidelines: str | None = None,
) -> str:
    prompt = [
        f"Clause reference: {clause_reference.strip()}",
        "",
        "Clause text:",
        clause_text,
    ]

    if guidelines and guidelines.strip():
        prompt.extend(["", "Additional guidelines:", guidelines.strip()])

    return "\n".join(prompt)


def build_messages(
    clause_reference: str,
    clause_text: str,
    guidelines: str | None = None,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(clause_reference, clause_text, guidelines),
        },
    ]


def lookup_clause_text(
    clause_reference: str,
    sections_path: Path | str = DEFAULT_SECTIONS_PATH,
) -> str:
    sections = load_sections(sections_path)
    clause_node = get_clause_node(clause_reference, sections)
    clause_text = flatten_clause(clause_reference, clause_node)
    if not clause_text:
        raise AwardInterpreterError(f"Clause reference has no text: {clause_reference}")
    return clause_text


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    text_parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for content_item in content:
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text)

    return "\n".join(text_parts)


def interpret_clause(
    clause_reference: str,
    guidelines: str | None = None,
    sections_path: Path | str = DEFAULT_SECTIONS_PATH,
    model: str | None = None,
) -> str:
    load_environment()
    selected_model = model or os.getenv("AWARD_INTERPRETER_MODEL", DEFAULT_MODEL)
    clause_text = lookup_clause_text(clause_reference, sections_path)

    client = OpenAI()
    messages = build_messages(clause_reference, clause_text, guidelines)

    try:
        response = client.responses.create(model=selected_model, input=messages)
    except Exception as exc:
        raise AwardInterpreterError("OpenAI request failed.") from exc

    output_text = extract_response_text(response)
    if not output_text:
        raise AwardInterpreterError("OpenAI response did not include output text.")

    return output_text


def interpret_clause_with_text(
    clause_reference: str,
    guidelines: str | None = None,
    sections_path: Path | str = DEFAULT_SECTIONS_PATH,
    model: str | None = None,
) -> tuple[str, str]:
    clause_text = lookup_clause_text(clause_reference, sections_path)
    llm_response = interpret_clause(
        clause_reference=clause_reference,
        guidelines=guidelines,
        sections_path=sections_path,
        model=model,
    )
    return clause_text, llm_response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interpret an award clause into plain English and pseudocode."
    )
    parser.add_argument("clause_reference", help="Clause reference to interpret, for example 24.1")
    parser.add_argument(
        "--guidelines",
        default=None,
        help="Optional extra guidance for the interpretation.",
    )
    parser.add_argument(
        "--sections-path",
        default=DEFAULT_SECTIONS_PATH,
        help="Path to the processed award section index JSON.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenAI model to use. Defaults to AWARD_INTERPRETER_MODEL or {DEFAULT_MODEL}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        interpret_clause(
            clause_reference=args.clause_reference,
            guidelines=args.guidelines,
            sections_path=args.sections_path,
            model=args.model,
        )
    )


if __name__ == "__main__":
    main()
