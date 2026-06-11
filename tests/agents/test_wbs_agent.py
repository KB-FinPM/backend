# EN: Tests for WBS agent input validation behavior.
# KO: WBS Agent 입력 검증 동작 테스트입니다.

from datetime import date, timedelta

import pytest

from app.agents.core_agents.wbs_agent.agent import WbsAgent
from app.schemas.agent import AgentRequest
from util.agent_template_utils import load_wbs_common_rows


@pytest.mark.anyio
async def test_wbs_agent_requires_requirement_context() -> None:
    agent = WbsAgent()

    response = await agent.generate(AgentRequest(project_id="PRJ-001"))

    assert response.success is False
    assert response.agent_name == "WbsAgent"
    assert response.error == "No requirement context available for WBS generation"


@pytest.mark.anyio
async def test_wbs_agent_applies_planned_dates_from_context() -> None:
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[{"chunk_id": "CHUNK-001", "text": "Login and reporting"}],
            context={
                "project_name": "Schedule Test",
                "start_date": "2024.01.10",
                "project_period": "6개월",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-001",
                            "requirement_name": "Login",
                            "description": "Users can sign in.",
                            "biz_requirement_name": "Access",
                        },
                        {
                            "requirement_id": "REQ-002",
                            "requirement_name": "Report",
                            "description": "Users can view reports.",
                            "biz_requirement_name": "Reporting",
                        },
                    ],
                },
            },
        )
    )

    assert response.success is True
    tasks = response.result["tasks"]
    project_start = date.fromisoformat("2024-01-10")
    project_end = date.fromisoformat("2024-07-10")

    assert tasks[0]["planned_start_date"] == "2024-01-10"
    assert tasks[0]["planned_end_date"] == "2024-07-10"
    task_by_id = {task["task_id"]: task for task in tasks}
    for task in tasks:
        planned_start = date.fromisoformat(task["planned_start_date"])
        planned_end = date.fromisoformat(task["planned_end_date"])
        metadata = task["metadata"]

        assert project_start <= planned_start <= project_end
        assert project_start <= planned_end <= project_end
        assert planned_start <= planned_end
        assert task["start_date"] == metadata["start_date"]
        assert task["end_date"] == metadata["end_date"]
        assert metadata["start_date"] == planned_start.strftime("%Y.%m.%d")
        assert metadata["end_date"] == planned_end.strftime("%Y.%m.%d")
        assert task["planned_start_date"] == metadata["planned_start_date"]
        assert task["planned_end_date"] == metadata["planned_end_date"]

        parent_id = metadata.get("parent_task_id")
        if parent_id and parent_id in task_by_id:
            parent = task_by_id[parent_id]
            parent_start = date.fromisoformat(parent["planned_start_date"])
            parent_end = date.fromisoformat(parent["planned_end_date"])
            assert parent_start <= planned_start <= parent_end
            assert parent_start <= planned_end <= parent_end


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("2024.01.10", date(2024, 1, 10)),
        ("2024-01-10", date(2024, 1, 10)),
        ("2024/01/10", date(2024, 1, 10)),
    ],
)
def test_wbs_agent_parses_supported_start_date_formats(
    raw_value: str,
    expected: date,
) -> None:
    assert WbsAgent()._parse_start_date(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("6개월", date(2024, 7, 10)),
        ("180일", date(2024, 7, 8)),
        ("12주", date(2024, 4, 3)),
        ("6 months", date(2024, 7, 10)),
        ("180 days", date(2024, 7, 8)),
        ("12 weeks", date(2024, 4, 3)),
        ("1일", date(2024, 1, 11)),
    ],
)
def test_wbs_agent_parses_supported_project_period_formats(
    raw_value: str,
    expected: date,
) -> None:
    assert WbsAgent()._parse_project_period(raw_value, date(2024, 1, 10)) == expected


def test_wbs_agent_parses_month_end_period_boundary() -> None:
    assert WbsAgent()._parse_project_period("1개월", date(2024, 1, 31)) == date(
        2024,
        2,
        29,
    )


@pytest.mark.anyio
async def test_wbs_agent_defaults_missing_project_period_to_six_months() -> None:
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[{"chunk_id": "CHUNK-001", "text": "Login"}],
            context={
                "project_name": "Schedule Test",
                "start_date": "2024.01.10",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-001",
                            "requirement_name": "Login",
                            "description": "Users can sign in.",
                            "biz_requirement_name": "Access",
                        },
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert response.result["metadata"]["project_start_date"] == "2024.01.10"
    assert response.result["metadata"]["project_end_date"] == "2024.07.10"
    assert response.result["metadata"]["project_period"] == "6개월"
    assert response.result["tasks"][0]["start_date"] == "2024.01.10"
    assert response.result["tasks"][0]["end_date"] == "2024.07.10"


@pytest.mark.anyio
async def test_wbs_agent_defaults_invalid_schedule_context_to_today(monkeypatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls):  # type: ignore[override]
            return cls(2026, 6, 10)

    monkeypatch.setattr("app.agents.core_agents.wbs_agent.agent.date", FixedDate)
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[{"chunk_id": "CHUNK-001", "text": "Login"}],
            context={
                "project_name": "Schedule Test",
                "start_date": "not-a-date",
                "project_period": "not-a-period",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-001",
                            "requirement_name": "Login",
                            "description": "Users can sign in.",
                            "biz_requirement_name": "Access",
                        },
                    ],
                },
            },
        )
    )

    assert response.success is True
    assert response.result["metadata"]["project_start_date"] == "2026.06.10"
    assert response.result["metadata"]["project_end_date"] == "2026.12.10"
    assert all("planned_start_date" in task for task in response.result["tasks"])


@pytest.mark.anyio
async def test_wbs_agent_uses_backend_dev_common_prefix_and_keeps_generated_tasks() -> None:
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "project_name": "테스트 프로젝트",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "RQ-001",
                            "title": "로그인",
                            "description": "로그인 기능",
                            "biz_requirement_name": "접근관리",
                        }
                    ]
                },
            },
        )
    )

    assert response.success is True
    tasks = response.result["tasks"]
    template_rows = load_wbs_common_rows()

    assert len(tasks) > len(template_rows)
    for task, template_row in zip(tasks[: len(template_rows)], template_rows, strict=True):
        assert task["metadata"]["level"] == template_row["level"]
        assert task["metadata"]["wbs_id"] == template_row["wbs_id"]
        assert task["name"] == template_row["wbs_name"]

    generated = tasks[len(template_rows):]
    assert generated[0]["name"] == "접근관리"
    assert generated[0]["metadata"]["wbs_id"] == "4"


@pytest.mark.anyio
async def test_wbs_agent_applies_special_schedule_rules_by_id_hierarchy() -> None:
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "start_date": "2026.01.01",
                "project_period": "6개월",
                "project_name": "테스트 프로젝트",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "RQ-001",
                            "title": "로그인",
                            "description": "로그인 기능",
                        }
                    ]
                },
            },
        )
    )

    assert response.success is True
    task_map = {task["metadata"]["wbs_id"]: task for task in response.result["tasks"]}
    windows = agent._build_development_phase_windows(date(2026, 1, 1), date(2026, 7, 1))

    requirement_end = windows["요구사항정의"][1]
    design_end = windows["설계"][1]
    implementation_end = windows["구현"][1]
    test_start, test_end = windows["테스트"]
    transition_end = windows["이행"][1]

    assert task_map["1.1.1.4"]["metadata"]["start_date"] == requirement_end.strftime("%Y.%m.%d")
    assert task_map["1.1.1.4"]["metadata"]["end_date"] == requirement_end.strftime("%Y.%m.%d")

    test_plan_start, test_plan_end = agent._align_to_week_boundaries(
        design_end - timedelta(weeks=1),
        design_end,
    )
    assert task_map["3.3.5"]["metadata"]["start_date"] == test_plan_start.strftime("%Y.%m.%d")
    assert task_map["3.3.5"]["metadata"]["end_date"] == test_plan_end.strftime("%Y.%m.%d")

    unit_start, unit_end = agent._align_to_week_boundaries(
        implementation_end - timedelta(weeks=2),
        implementation_end,
    )
    assert task_map["3.4.3"]["metadata"]["start_date"] == unit_start.strftime("%Y.%m.%d")
    assert task_map["3.4.3"]["metadata"]["end_date"] == unit_end.strftime("%Y.%m.%d")

    integration_start, integration_end = agent._align_to_week_boundaries(
        test_start,
        test_end - timedelta(weeks=1),
    )
    assert task_map["3.5.1"]["metadata"]["start_date"] == integration_start.strftime("%Y.%m.%d")
    assert task_map["3.5.1"]["metadata"]["end_date"] == integration_end.strftime("%Y.%m.%d")

    assert task_map["3.6.2.3"]["metadata"]["start_date"] == transition_end.strftime("%Y.%m.%d")
    assert task_map["3.6.2.3"]["metadata"]["end_date"] == transition_end.strftime("%Y.%m.%d")
