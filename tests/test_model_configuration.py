"""Tests for the model and reasoning settings of the early pipeline steps."""

from pathlib import Path

import pytest

from src.common.overtime_clause_classification import (
    DEFAULT_MODEL as OVERTIME_CLASSIFICATION_MODEL,
    OvertimeInterpretationError,
)
from src.step_2_1_classify_payments.schema import (
    DEFAULT_MODEL as PAYMENT_CLASSIFICATION_MODEL,
    TopLevelGroup,
)
from src.step_2_1_classify_payments.step_3_classify_groups import classify_group
from src.step_2_2_classify_overtime_clauses.step_3_classify_overtime import (
    classify_overtime_clauses,
)
from src.step_3_1_generate_ruleset.schema import (
    DEFAULT_MODEL as RULESET_GENERATION_MODEL,
)
from src.step_3_1_generate_ruleset.step_2_generate_expert_rules import (
    request_structured_interpretation_run,
)
from src.step_3_1_generate_ruleset.step_4_combine_expert_rules import (
    combine_expert_rulesets,
)
from src.step_3_2_review_ruleset.schema import (
    DEFAULT_CREATOR_MODEL,
    DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS,
    EVALUATOR_MODEL,
    OvertimeInterpretationReviewError,
)
from src.step_3_2_review_ruleset.step_2_run_reviewer import (
    request_evaluator_feedback,
)
from src.step_4_1_format_ruleset.schema import DEFAULT_MODEL as FORMATTER_MODEL
from src.step_5_1_generate_pseudocode.schema import DEFAULT_MODEL as PSEUDOCODE_MODEL
from src.step_6_1_generate_calculator_yaml.core import DEFAULT_MODEL as CALCULATOR_MODEL


class FakeResponses:
    """Record one Responses API call without contacting the model provider."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class FakeClient:
    """Provide the small client surface needed by the model-call functions."""

    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_steps_2_1_2_2_and_3_1_default_to_gpt_5_6_luna():
    assert PAYMENT_CLASSIFICATION_MODEL == "gpt-5.6-luna"
    assert OVERTIME_CLASSIFICATION_MODEL == "gpt-5.6-luna"
    assert RULESET_GENERATION_MODEL == "gpt-5.6-luna"


def test_step_4_1_uses_quality_model_while_other_later_steps_use_luna():
    assert EVALUATOR_MODEL == "gpt-5.6-luna"
    assert DEFAULT_CREATOR_MODEL == "gpt-5.6-luna"
    assert DEFAULT_EVALUATOR_MAX_OUTPUT_TOKENS == 16000
    assert FORMATTER_MODEL == "gpt-5.6-sol"
    assert PSEUDOCODE_MODEL == "gpt-5.6-luna"
    assert CALCULATOR_MODEL == "gpt-5.6-luna"


def test_step_3_2_evaluator_request_uses_medium_reasoning(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(
        "src.step_3_2_review_ruleset.step_2_run_reviewer.extract_response_text",
        lambda response: "",
    )
    monkeypatch.setattr(
        "src.step_3_2_review_ruleset.step_2_run_reviewer.build_evaluator_repair_messages",
        lambda messages, **kwargs: messages,
    )

    with pytest.raises(OvertimeInterpretationReviewError):
        request_evaluator_feedback(
            evaluator_client=client,
            evaluator_model="gpt-5.6-luna",
            evaluator_max_output_tokens=16000,
            evaluator_messages=[],
            original_rules=[],
            ruleset_key="overtime_creation",
        )

    assert client.responses.calls[0]["reasoning"] == {"effort": "medium"}


def test_step_2_1_request_does_not_request_reasoning(monkeypatch):
    group = TopLevelGroup(
        reference="10",
        title="Allowances",
        text="Allowances are paid under this clause.",
        descendants=(),
    )
    client = FakeClient()

    monkeypatch.setattr(
        "src.step_2_1_classify_payments.step_3_classify_groups.build_messages",
        lambda group: [],
    )
    monkeypatch.setattr(
        "src.step_2_1_classify_payments.step_3_classify_groups.extract_response_text",
        lambda response: '{"top_level_clause": {}, "classified_clauses": []}',
    )

    classify_group(group, client, "gpt-5.6-luna")

    assert "reasoning" not in client.responses.calls[0]


def test_step_2_2_request_does_not_request_reasoning(monkeypatch):
    client = FakeClient()

    monkeypatch.setattr(
        "src.step_2_2_classify_overtime_clauses.step_3_classify_overtime.build_clause_classification_messages",
        lambda overtime_clauses, ruleset_key: [],
    )
    monkeypatch.setattr(
        "src.step_2_2_classify_overtime_clauses.step_3_classify_overtime.extract_response_text",
        lambda response: "",
    )

    with pytest.raises(OvertimeInterpretationError, match="did not include output text"):
        classify_overtime_clauses({}, client, "gpt-5.6-luna")

    assert "reasoning" not in client.responses.calls[0]


def test_step_3_1_expert_and_comparison_requests_use_medium_reasoning(monkeypatch):
    client = FakeClient()

    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.step_2_generate_expert_rules.build_interpretation_messages",
        lambda *args: [],
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.step_2_generate_expert_rules.extract_response_text",
        lambda response: "",
    )

    with pytest.raises(OvertimeInterpretationError, match="did not include output text"):
        request_structured_interpretation_run(
            client=client,
            model="gpt-5.6-luna",
            source_path=Path("source.json"),
            overtime_creation_clauses=[],
        )

    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.step_4_combine_expert_rules.build_expert_comparison_messages",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "src.step_3_1_generate_ruleset.step_4_combine_expert_rules.extract_response_text",
        lambda response: "",
    )

    with pytest.raises(OvertimeInterpretationError, match="did not include output text"):
        combine_expert_rulesets(
            client=client,
            model="gpt-5.6-luna",
            source_path=Path("source.json"),
            overtime_creation_clauses=[],
            expert_a_rules=[],
            expert_b_rules=[],
        )

    assert client.responses.calls[0]["reasoning"] == {"effort": "medium"}
    assert client.responses.calls[1]["reasoning"] == {"effort": "medium"}
