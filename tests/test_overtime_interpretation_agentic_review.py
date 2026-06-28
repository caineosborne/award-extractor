import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import RateLimitError

from src.script_3b_agentic_review_workflow import (
    AgenticReviewContext,
    AgenticReviewFinalOutput,
    agentic_conversation_path_for_interpretation,
    build_agentic_source_context,
    create_evaluator_feedback_tool,
    run_agent_with_rate_limit_retries,
    run_agentic_overtime_interpretation_review_async,
)
from src.script_3b_agentic_review_overtime_interpretation import main as agentic_cli_main
from src.script_3b_review_overtime_interpretation import PROJECT_ROOT


def sample_classification():
    return {
        "classified_clauses": {
            "20.1": {
                "tags": ["Ordinary Hours & Overtime"],
                "text": "Overtime after ordinary hours.",
            },
            "30.1": {
                "tags": ["Other Payment"],
                "text": "Possible missed overtime creation clause.",
            },
        }
    }


def sample_overtime_clause_classification():
    return {
        "schema_version": "overtime-clause-classification-v2",
        "clauses": [
            {
                "clause_number": "20.1",
                "classification": "Overtime Trigger",
                "classifications": ["Overtime Trigger"],
                "explanation": "Directly creates overtime.",
                "clause_text": "Overtime after ordinary hours.",
            }
        ],
    }


class FakeAgentRunner:
    def __init__(self, feedback_cycles_to_request: int):
        self.feedback_cycles_to_request = feedback_cycles_to_request
        self.calls = []

    async def __call__(self, agent, input_text, **kwargs):
        self.calls.append(
            {
                "agent_name": agent.name,
                "input_text": input_text,
                "kwargs": kwargs,
            }
        )

        if agent.name == "Overtime interpretation evaluator":
            feedback_number = len(
                [
                    call
                    for call in self.calls
                    if call["agent_name"] == "Overtime interpretation evaluator"
                ]
            )
            if feedback_number > 1:
                return SimpleNamespace(
                    final_output=(
                        '{"status":"needs_revision","reason":"Clause 20.1 still needs clarification."}'
                    )
                )
            return SimpleNamespace(
                final_output=(
                    "# Overtime interpretation supervisor feedback\n\n"
                    f"Feedback cycle {feedback_number}: clarify clause 20.1."
                )
            )

        tool_context = SimpleNamespace(
            tool_name="request_evaluator_feedback",
            run_config=None,
        )
        evaluator_tool = agent.tools[0]
        for cycle_number in range(1, self.feedback_cycles_to_request + 1):
            await evaluator_tool.on_invoke_tool(
                tool_context,
                json.dumps(
                    {
                        "current_draft_markdown": (
                            "# Overtime Interpretation Working Document\n\n"
                            f"Draft cycle {cycle_number}."
                        ),
                        "creator_question_or_focus": (
                            f"Please review draft cycle {cycle_number}."
                        ),
                    }
                ),
            )

        return SimpleNamespace(
            final_output=AgenticReviewFinalOutput(
                conversation_markdown=(
                    "# Creator/evaluator conversation\n\n"
                    "Creator accepted the useful clause 20.1 feedback."
                ),
                revised_interpretation_markdown=(
                    "# Overtime Interpretation Working Document\n\n"
                    "Clause 20.1 has been clarified."
                ),
            )
        )


class AgenticOvertimeInterpretationReviewTests(unittest.TestCase):
    def test_agentic_conversation_path_for_interpretation(self):
        interpretation_path = Path(
            "data/processed/3_overtime_interpretations/MA000018_overtime_interpretation.md"
        )

        self.assertEqual(
            agentic_conversation_path_for_interpretation(interpretation_path),
            Path(
                "data/processed/3_overtime_interpretations/feedback/"
                "MA000018_overtime_interpretation_agentic_review_conversation.md"
            ),
        )

    def test_build_agentic_source_context_includes_review_sources(self):
        source_context = build_agentic_source_context(
            interpretation_path="interpretation.md",
            interpretation_markdown="# Original draft",
            classification_path="classification.json",
            payment_classification=sample_classification(),
            overtime_clause_classification=sample_overtime_clause_classification(),
        )

        self.assertIn("# Original draft", source_context)
        self.assertIn("classification.json", source_context)
        self.assertIn("Relevant source clauses for the first pass", source_context)
        self.assertIn("Clause 20.1", source_context)
        self.assertNotIn('"30.1"', source_context)
        self.assertNotIn("Script 3 creator prompt context", source_context)
        self.assertNotIn("clause_classification_messages", source_context)
        self.assertNotIn("interpretation_messages", source_context)

    def test_evaluator_tool_enforces_max_feedback_cycles(self):
        async def fake_runner(agent, input_text, **kwargs):
            if "Return JSON only" in input_text:
                return SimpleNamespace(
                    final_output='{"status":"needs_revision","reason":"Review response."}'
                )
            return SimpleNamespace(final_output="# Feedback\n\nReview response.")

        context = AgenticReviewContext(
            evaluator_agent=SimpleNamespace(name="Overtime interpretation evaluator"),
            evaluator_input_builder=lambda draft, cycle: f"cycle {cycle}: {draft}",
            max_feedback_cycles=2,
            runner_run=fake_runner,
        )
        tool = create_evaluator_feedback_tool(context)
        tool_context = SimpleNamespace(
            tool_name="request_evaluator_feedback",
            run_config=None,
        )

        async def invoke_tool():
            first_response = await tool.on_invoke_tool(
                tool_context,
                json.dumps(
                    {
                        "current_draft_markdown": "# Draft 1",
                        "creator_question_or_focus": "Review draft 1.",
                    }
                ),
            )
            second_response = await tool.on_invoke_tool(
                tool_context,
                json.dumps(
                    {
                        "current_draft_markdown": "# Draft 2",
                        "creator_question_or_focus": "Review draft 2.",
                    }
                ),
            )
            third_response = await tool.on_invoke_tool(
                tool_context,
                json.dumps(
                    {
                        "current_draft_markdown": "# Draft 3",
                        "creator_question_or_focus": "Review draft 3.",
                    }
                ),
            )
            return first_response, second_response, third_response

        first_response, second_response, third_response = asyncio.run(invoke_tool())

        self.assertIn("Review response", first_response)
        self.assertIn('"status":"needs_revision"', second_response)
        self.assertIn("Maximum evaluator feedback cycles", third_response)
        self.assertEqual(context.feedback_cycles_used, 2)
        self.assertEqual(len(context.transcript_entries), 2)

    def test_agent_runner_retries_after_rate_limit(self):
        calls = []
        sleep_delays = []
        response = httpx.Response(
            429,
            headers={"retry-after": "0.25"},
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        )

        async def fake_runner(agent, input_text, **kwargs):
            calls.append((agent, input_text, kwargs))
            if len(calls) == 1:
                raise RateLimitError(
                    "Rate limit reached. Please try again in 0.25s.",
                    response=response,
                    body=None,
                )
            return SimpleNamespace(final_output="Completed after retry.")

        async def fake_sleep(delay_seconds):
            sleep_delays.append(delay_seconds)

        status_messages = []

        async def run_with_retry():
            with patch(
                "src.script_3b_agentic_review_workflow.asyncio.sleep",
                fake_sleep,
            ):
                return await run_agent_with_rate_limit_retries(
                    fake_runner,
                    SimpleNamespace(name="Overtime interpretation creator"),
                    "input",
                    status_callback=status_messages.append,
                    max_turns=3,
                )

        result = asyncio.run(run_with_retry())

        self.assertEqual(result.final_output, "Completed after retry.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleep_delays, [2.25])
        self.assertIn("retry 2/6", status_messages[0])

    def test_agentic_review_writes_conversation_and_revised_outputs(self):
        classification = sample_classification()
        overtime_clause_classification = sample_overtime_clause_classification()
        fake_runner = FakeAgentRunner(feedback_cycles_to_request=2)
        status_messages = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            interpretation_path = temp_path / "award_overtime_interpretation.md"
            classification_path = temp_path / "award_payment_classification.json"
            overtime_clause_classification_path = (
                temp_path
                / "3_overtime_interpretations"
                / "award_overtime_clause_classification.json"
            )

            interpretation_path.write_text("# Original draft", encoding="utf-8")
            classification_path.write_text(json.dumps(classification), encoding="utf-8")
            overtime_clause_classification_path.parent.mkdir()
            overtime_clause_classification_path.write_text(
                json.dumps(overtime_clause_classification),
                encoding="utf-8",
            )

            artifacts = asyncio.run(
                run_agentic_overtime_interpretation_review_async(
                    interpretation_path=interpretation_path,
                    classification_path=classification_path,
                    overtime_clause_classification_path=overtime_clause_classification_path,
                    inter_call_delay_seconds=0,
                    runner_run=fake_runner,
                    status_callback=status_messages.append,
                )
            )

            conversation_archive_files = list(
                (temp_path / "feedback" / "archive").glob(
                    "award_overtime_interpretation_agentic_review_conversation_*.md"
                )
            )
            revised_archive_files = list(
                (temp_path / "archive").glob(
                    "award_overtime_interpretation_revised_*.md"
                )
            )
            conversation_file_exists = artifacts.conversation_path.exists()
            revised_file_exists = artifacts.revised_interpretation_path.exists()

        self.assertTrue(conversation_file_exists)
        self.assertTrue(revised_file_exists)
        self.assertEqual(artifacts.evaluator_feedback_cycles, 2)
        self.assertIn("Creator accepted", artifacts.conversation_markdown)
        self.assertIn("Clause 20.1 has been clarified", artifacts.revised_interpretation_markdown)
        self.assertEqual(len(conversation_archive_files), 1)
        self.assertEqual(len(revised_archive_files), 1)
        self.assertEqual(fake_runner.calls[0]["agent_name"], "Overtime interpretation creator")
        self.assertEqual(fake_runner.calls[1]["agent_name"], "Overtime interpretation evaluator")
        self.assertNotIn("Script 3 creator prompt context", fake_runner.calls[0]["input_text"])
        self.assertIn("Relevant source clauses for the first pass", fake_runner.calls[0]["input_text"])
        self.assertIn("Review this overtime interpretation working document.", fake_runner.calls[1]["input_text"])
        self.assertIn('{"status":"pass"|"needs_revision","reason":"..."}', fake_runner.calls[2]["input_text"])
        self.assertTrue(
            any(
                "Token budget for script_3b_agentic_creator" in message
                for message in status_messages
            )
        )
        self.assertTrue(
            any(
                "Token budget for script_3b_agentic_evaluator" in message
                for message in status_messages
            )
        )

    def test_cli_resolves_paths_and_delegates_to_reusable_module(self):
        with patch(
            "src.script_3b_agentic_review_overtime_interpretation.load_openai_environment"
        ) as load_environment:
            with patch(
                "src.script_3b_agentic_review_overtime_interpretation."
                "run_agentic_overtime_interpretation_review"
            ) as run_review:
                run_review.return_value = SimpleNamespace(
                    conversation_path=Path("conversation.md"),
                    revised_interpretation_path=Path("revised.md"),
                    evaluator_feedback_cycles=2,
                )

                agentic_cli_main(
                    [
                        "MA000018",
                        "--classification-path",
                        "classification.json",
                        "--overtime-clause-classification-path",
                        "overtime_clause_classification.json",
                        "--creator-model",
                        "creator-model",
                        "--evaluator-model",
                        "evaluator-model",
                        "--max-feedback-cycles",
                        "2",
                    ]
                )

        load_environment.assert_called_once()
        run_review.assert_called_once()
        call_kwargs = run_review.call_args.kwargs
        self.assertEqual(
            call_kwargs["interpretation_path"],
            PROJECT_ROOT
            / Path("data/processed/MA000018/MA000018_overtime_interpretation.md"),
        )
        self.assertEqual(call_kwargs["classification_path"], Path("classification.json"))
        self.assertEqual(
            call_kwargs["overtime_clause_classification_path"],
            Path("overtime_clause_classification.json"),
        )
        self.assertEqual(call_kwargs["creator_model"], "creator-model")
        self.assertEqual(call_kwargs["evaluator_model"], "evaluator-model")
        self.assertEqual(call_kwargs["max_feedback_cycles"], 2)


if __name__ == "__main__":
    unittest.main()
