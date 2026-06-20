"""Evaluate curated intent-correction seed cases.

This script is intentionally separate from document RAG/vector DB. It loads the
reviewed JSON fixture and checks the in-memory command accuracy layer for the
Input, Output, and Schedule agents.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
import json
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "agent_accuracy_learning_seed_cases.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.core_agents.schedule_management_agent.agent import (  # noqa: E402
    ScheduleManagementAgent,
)
from app.agents.input_agents.chat_input_agent.agent import ChatInputAgent  # noqa: E402
from app.agents.output_agents.chat_agent.agent import ChatOutputAgent  # noqa: E402
from app.schemas.agent import AgentRequest  # noqa: E402
from app.schemas.io_agent import (  # noqa: E402
    InputAgentRequest,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _ratio(passed: int, total: int) -> float:
    return 1.0 if total == 0 else passed / total


async def _evaluate_input_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    agent = ChatInputAgent()
    metrics = Counter()
    failures: list[str] = []
    confusion = Counter()

    for case in cases:
        response = await agent.parse(
            InputAgentRequest(
                project_id="PRJ-001",
                input_type=InputType.TEXT,
                raw_payload={"message": case["message"]},
                context=case.get("context") or {},
            )
        )
        context = response.structured_context or {}
        expected_intent = case["expected_intent"]
        actual_intent = context.get("intent")

        metrics["intent_total"] += 1
        if response.success and actual_intent == expected_intent:
            metrics["intent_passed"] += 1
        else:
            failures.append(
                f"input intent mismatch: {case['message']} "
                f"expected={expected_intent} actual={actual_intent}"
            )
            confusion[(expected_intent, actual_intent)] += 1
            metrics["false_negative_count"] += 1

        expected_artifact_type = case.get("expected_artifact_type")
        if expected_artifact_type:
            metrics["artifact_total"] += 1
            actual_artifact_type = (
                context.get("target_artifact_type")
                or context.get("artifact_type")
                or context.get("artifact_type_slot")
            )
            if actual_artifact_type == expected_artifact_type:
                metrics["artifact_passed"] += 1
            else:
                failures.append(
                    f"artifact type mismatch: {case['message']} "
                    f"expected={expected_artifact_type} actual={actual_artifact_type}"
                )

        expected_schedule_action = case.get("expected_schedule_action")
        if expected_schedule_action:
            metrics["schedule_action_total"] += 1
            if context.get("schedule_action") == expected_schedule_action:
                metrics["schedule_action_passed"] += 1
            else:
                failures.append(
                    f"schedule action mismatch: {case['message']} "
                    f"expected={expected_schedule_action} "
                    f"actual={context.get('schedule_action')}"
                )

        expected_corrections = case.get("expected_corrections") or []
        if expected_corrections:
            metrics["correction_total"] += len(expected_corrections)
            actual_corrections = [
                {"source": item.get("source"), "target": item.get("target")}
                for item in context.get("corrections", [])
                if isinstance(item, dict)
            ]
            for correction in expected_corrections:
                if correction in actual_corrections:
                    metrics["correction_passed"] += 1
                else:
                    failures.append(
                        f"correction missing: {case['message']} expected={correction}"
                    )

        for forbidden_intent in case.get("negative_assertions", []):
            metrics["negative_guard_total"] += 1
            if actual_intent != forbidden_intent:
                metrics["negative_guard_passed"] += 1
            else:
                metrics["false_positive_count"] += 1
                failures.append(
                    f"negative guard failed: {case['message']} "
                    f"forbidden={forbidden_intent}"
                )

        if expected_intent in {"CONFIRM_PENDING_ACTION", "CANCEL_PENDING_ACTION"}:
            metrics["confirm_cancel_total"] += 1
            if actual_intent == expected_intent:
                metrics["confirm_cancel_passed"] += 1

    return {
        "metrics": dict(metrics),
        "failures": failures,
        "confusion_summary": {
            f"{expected}->{actual}": count
            for (expected, actual), count in sorted(confusion.items())
        },
    }


async def _evaluate_schedule_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    agent = ScheduleManagementAgent()
    failures: list[str] = []
    passed = 0

    for case in cases:
        if case["name"] == "blocked_status_alias":
            response = await agent.generate(
                AgentRequest(
                    project_id="PRJ-001",
                    context={
                        "action": "UPDATE_TODO_STATUS",
                        "normalized_input": case["normalized_input"],
                        "todos": case["todos"],
                    },
                )
            )
            ok = (
                response.success
                and response.result.get("status") == case["expected_status"]
                and response.result.get("matched_todo", {}).get("next_status")
                == case["expected_next_status"]
            )
        else:
            response = await agent.generate(
                AgentRequest(
                    project_id="PRJ-001",
                    context={
                        "action": "EXTRACT_TODOS_FROM_MEETING",
                        "meeting_notes": case["meeting_notes"],
                        "current_date": case.get("current_date", "2026-06-10"),
                    },
                )
            )
            todos = (response.result or {}).get("todos") or []
            if case["name"] == "stopword_not_assignee":
                forbidden = set(case["expected_forbidden_assignee_values"])
                ok = all(todo.get("assignee") not in forbidden for todo in todos)
            else:
                first = todos[0] if todos else {}
                ok = (
                    response.success
                    and first.get("due_date") == case["expected_due_date"]
                    and first.get("assignee") == case["expected_assignee"]
                )

        if ok:
            passed += 1
        else:
            failures.append(f"schedule case failed: {case['name']}")

    return {"passed": passed, "total": len(cases), "failures": failures}


async def _evaluate_output_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    agent = ChatOutputAgent()
    failures: list[str] = []
    passed = 0

    for case in cases:
        response = await agent.render(
            OutputAgentRequest(
                project_id="PRJ-001",
                response_type=OutputResponseType.CHAT_RESPONSE,
                result_json=case["result_json"],
            )
        )
        message = response.message or ""
        contains_expected = all(
            expected in message for expected in case["expected_user_message_contains"]
        )
        hides_internal = all(
            forbidden not in message for forbidden in case["forbidden_internal_terms"]
        )
        preserves_corrections = (
            response.display_payload.get("corrections")
            == case["result_json"].get("corrections")
        )
        if response.success and contains_expected and hides_internal and preserves_corrections:
            passed += 1
        else:
            failures.append(f"output case failed: {case['event']}")

    return {"passed": passed, "total": len(cases), "failures": failures}


async def main() -> int:
    fixture = _load_fixture()
    input_result = await _evaluate_input_cases(fixture["input_agent_cases"])
    schedule_result = await _evaluate_schedule_cases(fixture["schedule_agent_cases"])
    output_result = await _evaluate_output_cases(fixture["output_agent_cases"])

    metrics = input_result["metrics"]
    summary = {
        "input_intent_accuracy": _ratio(
            metrics.get("intent_passed", 0),
            metrics.get("intent_total", 0),
        ),
        "artifact_type_accuracy": _ratio(
            metrics.get("artifact_passed", 0),
            metrics.get("artifact_total", 0),
        ),
        "schedule_action_accuracy": _ratio(
            metrics.get("schedule_action_passed", 0),
            metrics.get("schedule_action_total", 0),
        ),
        "correction_accuracy": _ratio(
            metrics.get("correction_passed", 0),
            metrics.get("correction_total", 0),
        ),
        "negative_guard_accuracy": _ratio(
            metrics.get("negative_guard_passed", 0),
            metrics.get("negative_guard_total", 0),
        ),
        "confirm_cancel_accuracy": _ratio(
            metrics.get("confirm_cancel_passed", 0),
            metrics.get("confirm_cancel_total", 0),
        ),
        "schedule_agent_accuracy": _ratio(
            schedule_result["passed"],
            schedule_result["total"],
        ),
        "output_agent_accuracy": _ratio(
            output_result["passed"],
            output_result["total"],
        ),
        "false_positive_count": metrics.get("false_positive_count", 0),
        "false_negative_count": metrics.get("false_negative_count", 0),
        "confusion_summary": input_result["confusion_summary"],
    }

    failures = (
        input_result["failures"]
        + schedule_result["failures"]
        + output_result["failures"]
    )
    print(json.dumps({"summary": summary, "failures": failures}, ensure_ascii=False, indent=2))

    thresholds = {
        "input_intent_accuracy": 0.95,
        "artifact_type_accuracy": 0.98,
        "schedule_action_accuracy": 0.95,
        "negative_guard_accuracy": 1.0,
        "confirm_cancel_accuracy": 1.0,
        "schedule_agent_accuracy": 1.0,
        "output_agent_accuracy": 1.0,
    }
    failed_thresholds = [
        name for name, threshold in thresholds.items() if summary[name] < threshold
    ]
    return 1 if failures or failed_thresholds else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
