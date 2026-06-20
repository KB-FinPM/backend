import json
from pathlib import Path

import pytest

from app.agents.input_agents.chat_input_agent.agent import ChatInputAgent
from app.schemas.io_agent import InputAgentRequest, InputType


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_accuracy_learning_seed_cases.json"
)


def _seed_cases() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case",
    _seed_cases()["input_agent_cases"],
    ids=lambda case: case["message"],
)
async def test_chat_input_agent_seed_accuracy_cases(case: dict) -> None:
    agent = ChatInputAgent()

    response = await agent.parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": case["message"]},
            context=case.get("context") or {},
        )
    )

    assert response.success is True
    context = response.structured_context
    assert context["intent"] == case["expected_intent"]
    assert context.get("intent_source") in {"rule", "rule+example", "example"}

    if case.get("normalized_query"):
        assert context["normalized_query"] == case["normalized_query"]
    if case.get("expected_schedule_action"):
        assert context.get("schedule_action") == case["expected_schedule_action"]
    if case.get("expected_artifact_type"):
        assert (
            context.get("target_artifact_type")
            or context.get("artifact_type")
            or context.get("artifact_type_slot")
        ) == case["expected_artifact_type"]
    if case.get("expected_source_document_type"):
        assert context.get("source_document_type") == case["expected_source_document_type"]
    if case.get("expected_export_format"):
        assert context.get("export_format") == case["expected_export_format"]
    if case.get("expected_artifact_id"):
        assert context.get("artifact_id") == case["expected_artifact_id"]
    if case.get("expected_time_range"):
        assert (
            context.get("time_range")
            or context.get("entities", {}).get("time_range")
            or context.get("semantic_slots", {}).get("time_range")
        ) == case["expected_time_range"]
    if case.get("expected_status"):
        assert context.get("entities", {}).get("status") == case["expected_status"]
    if case.get("expected_assignee"):
        assert (
            context.get("assignee")
            or context.get("entities", {}).get("assignee")
            or context.get("semantic_slots", {}).get("assignee")
        ) == case["expected_assignee"]
    if case.get("expected_topic"):
        assert context.get("topic") == case["expected_topic"]
    if case.get("expected_missing_slots"):
        assert context.get("missing_slots") == case["expected_missing_slots"]
    if case.get("expected_todo_title_contains"):
        assert case["expected_todo_title_contains"] in context.get(
            "todo_title_query",
            "",
        )
    if case.get("expected_absent_artifact_type"):
        assert context.get("artifact_type") is None
        assert context.get("target_artifact_type") is None
        assert context.get("artifact_type_slot") is None
    for forbidden in case.get("forbidden_assignee_values", []):
        assert context.get("assignee") != forbidden
        assert context.get("entities", {}).get("assignee") != forbidden
    for forbidden_intent in case.get("negative_assertions", []):
        assert context["intent"] != forbidden_intent
    for field in case.get("forbidden_top_level_fields", []):
        assert field not in context or context.get(field) in (None, [], {})

    corrections = context.get("corrections") or []
    for expected_correction in case.get("expected_corrections", []):
        assert expected_correction in [
            {"source": item.get("source"), "target": item.get("target")}
            for item in corrections
        ]


@pytest.mark.anyio
async def test_chat_input_agent_tracks_example_match_without_exposing_runtime_objects() -> None:
    response = await ChatInputAgent().parse(
        InputAgentRequest(
            project_id="PRJ-001",
            input_type=InputType.TEXT,
            raw_payload={"message": "회이록에서 액션아이템 뽑아줘"},
        )
    )

    matches = response.structured_context.get("matched_intent_examples")
    assert matches
    assert matches[0]["id"].startswith("input.")
    assert "retriever" not in response.structured_context
