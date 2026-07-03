from pathlib import Path

import pytest

from src.common.output_naming import (
    creator_response_markdown_path_for_ruleset,
    evaluator_feedback_path_for_interpretation,
    pseudocode_path_for_ruleset,
    revised_interpretation_path_for_interpretation,
    review_markdown_path_for_ruleset,
    ruleset_short_label,
)
from src.common.overtime_rulesets import (
    PENALTIES_RULESET,
    explicit_clause_classification_output_path,
    explicit_ruleset_output_path,
    infer_overtime_ruleset_key_from_path,
    overtime_ruleset_config,
)


def test_penalties_ruleset_config_is_registered():
    config = overtime_ruleset_config(PENALTIES_RULESET)

    assert config.key == PENALTIES_RULESET
    assert config.display_name == "Penalties"
    assert config.source_tags == ("Penalty", "Breaks (Between Work Periods)")
    assert config.allowed_classifications == ("Penalty Rule",)
    assert config.generation_classifications == ("Penalty Rule",)


def test_penalties_short_label_and_canonical_paths():
    classification_path = Path("data/processed/MA000018/2_1_payment_classification.json")
    interpretation_path = Path("data/processed/MA000018/3_1_Penalties_ruleset.md")

    assert ruleset_short_label(PENALTIES_RULESET) == "Penalties"
    assert explicit_clause_classification_output_path(
        classification_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/2_2_Penalties_clause_classification.json")
    assert explicit_ruleset_output_path(
        classification_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/3_1_Penalties_ruleset.md")
    assert review_markdown_path_for_ruleset(
        interpretation_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/feedback/3_2_Penalties_review.md")
    assert creator_response_markdown_path_for_ruleset(
        interpretation_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/feedback/3_2_Penalties_creator_response.md")
    assert pseudocode_path_for_ruleset(
        interpretation_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/5_1_Penalties_pseudocode.md")


@pytest.mark.parametrize(
    ("path", "expected_ruleset"),
    [
        ("data/processed/MA000018/2_2_Penalties_clause_classification.json", PENALTIES_RULESET),
        ("data/processed/MA000018/3_1_Penalties_ruleset.md", PENALTIES_RULESET),
        ("data/processed/MA000018/3_2_Penalties_revised_ruleset.md", PENALTIES_RULESET),
        ("data/processed/MA000018/4_1_Penalties_formatted_ruleset.md", PENALTIES_RULESET),
        ("data/processed/MA000018/5_1_Penalties_pseudocode.md", PENALTIES_RULESET),
    ],
)
def test_penalties_ruleset_is_inferred_from_canonical_paths(path: str, expected_ruleset: str):
    assert infer_overtime_ruleset_key_from_path(path) == expected_ruleset


def test_penalties_interpretation_helpers_use_canonical_review_and_revised_paths():
    interpretation_path = Path("data/processed/MA000018/3_1_Penalties_ruleset.md")
    revised_path = Path("data/processed/MA000018/3_2_Penalties_revised_ruleset.md")

    assert evaluator_feedback_path_for_interpretation(interpretation_path) == Path(
        "data/processed/MA000018/feedback/3_2_Penalties_review.md"
    )
    assert revised_interpretation_path_for_interpretation(interpretation_path) == Path(
        "data/processed/MA000018/3_2_Penalties_revised_ruleset.md"
    )
    assert creator_response_markdown_path_for_ruleset(
        interpretation_path,
        PENALTIES_RULESET,
    ) == Path("data/processed/MA000018/feedback/3_2_Penalties_creator_response.md")
    assert infer_overtime_ruleset_key_from_path(revised_path) == PENALTIES_RULESET
