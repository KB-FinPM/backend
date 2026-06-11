# EN: Tests for WBS agent input validation behavior.
# KO: WBS Agent 입력 검증 동작 테스트입니다.

import pytest
from datetime import date
from datetime import timedelta
from math import floor

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
async def test_wbs_agent_populates_schedule_and_worker_metadata() -> None:
    agent = WbsAgent()

    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            documents=[{"text": "추진 일정: 6개월\n계약일: 2024.01.10"}],
            context={"start_date": "2024.01.10", "project_name": "테스트 프로젝트"},
        )
    )

    assert response.success is True
    assert response.result is not None

    tasks = response.result["tasks"]
    metadata = next(task for task in tasks if task["metadata"].get("level") == "2")

    assert metadata["metadata"]["start_date"] == "2024.01.10"
    assert metadata["metadata"]["end_date"] == "2024.07.10"
    assert metadata["metadata"]["worker"] == "작업자"
    assert response.result["metadata"]["project_start_date"] == "2024.01.10"
    assert response.result["metadata"]["project_end_date"] == "2024.07.10"


@pytest.mark.anyio
async def test_wbs_agent_defaults_missing_schedule_to_today(monkeypatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls):  # type: ignore[override]
            return cls(2026, 6, 10)

    monkeypatch.setattr("app.agents.core_agents.wbs_agent.agent.date", FixedDate)

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
                        }
                    ]
                },
            },
        )
    )

    assert response.success is True
    assert response.result is not None
    assert response.result["metadata"]["project_start_date"] == "2026.06.10"
    assert response.result["metadata"]["project_end_date"] == "2026.12.10"
    assert response.result["metadata"]["project_period"] == "6개월"
    first_task = response.result["tasks"][0]
    assert first_task["metadata"]["start_date"] == "2026.06.10"
    assert first_task["metadata"]["end_date"] == "2026.12.10"


@pytest.mark.anyio
async def test_wbs_agent_defaults_missing_project_period_to_six_months(monkeypatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls):  # type: ignore[override]
            return cls(2026, 6, 10)

    monkeypatch.setattr("app.agents.core_agents.wbs_agent.agent.date", FixedDate)

    agent = WbsAgent()
    response = await agent.generate(
        AgentRequest(
            project_id="PRJ-001",
            context={
                "start_date": "2026.01.15",
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
    assert response.result is not None
    assert response.result["metadata"]["project_start_date"] == "2026.01.15"
    assert response.result["metadata"]["project_end_date"] == "2026.07.15"
    assert response.result["metadata"]["project_period"] == "6개월"


@pytest.mark.anyio
async def test_wbs_agent_distributes_development_phase_dates_by_ratio() -> None:
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
    assert response.result is not None

    tasks = response.result["tasks"]
    task_map = {task["name"]: task for task in tasks}
    project_start = date(2026, 1, 1)
    project_end = date(2026, 7, 1)

    def expected_windows(start: date, end: date) -> dict[str, tuple[date, date]]:
        total_days = max((end - start).days + 1, 1)
        cumulative = 0.0
        previous_cut = 0
        current_start = start
        raw_windows: dict[str, tuple[date, date]] = {}
        ratios = WbsAgent._development_phase_ratios()
        for index, (phase_name, ratio) in enumerate(ratios):
            cumulative += ratio
            if index == len(ratios) - 1:
                cut_day_count = total_days
            else:
                cut_day_count = floor(total_days * cumulative)
                cut_day_count = max(cut_day_count, previous_cut + 1)
                cut_day_count = min(cut_day_count, total_days - (len(ratios) - index - 1))
            phase_end = start + timedelta(days=cut_day_count - 1)
            raw_windows[phase_name] = (current_start, phase_end)
            current_start = phase_end + timedelta(days=1)
            previous_cut = cut_day_count

        windows: dict[str, tuple[date, date]] = {}
        for phase_name, (raw_start, raw_end) in raw_windows.items():
            windows[phase_name] = agent._align_to_week_boundaries(raw_start, raw_end)
        return windows

    windows = expected_windows(project_start, project_end)

    assert task_map["개발영역"]["metadata"]["start_date"] == "2026.01.01"
    assert task_map["개발영역"]["metadata"]["end_date"] == "2026.07.01"

    assert task_map["요구사항정의"]["metadata"]["start_date"] == windows["요구사항정의"][0].strftime("%Y.%m.%d")
    assert task_map["요구사항정의"]["metadata"]["end_date"] == windows["요구사항정의"][1].strftime("%Y.%m.%d")
    assert task_map["요건정의"]["metadata"]["start_date"] == windows["요구사항정의"][0].strftime("%Y.%m.%d")
    assert task_map["요건정의"]["metadata"]["end_date"] == windows["요구사항정의"][1].strftime("%Y.%m.%d")

    assert task_map["분석"]["metadata"]["start_date"] == windows["분석"][0].strftime("%Y.%m.%d")
    assert task_map["분석"]["metadata"]["end_date"] == windows["분석"][1].strftime("%Y.%m.%d")
    assert task_map["데이터분석"]["metadata"]["start_date"] == windows["분석"][0].strftime("%Y.%m.%d")

    assert task_map["설계"]["metadata"]["start_date"] == windows["설계"][0].strftime("%Y.%m.%d")
    assert task_map["구현"]["metadata"]["start_date"] == windows["구현"][0].strftime("%Y.%m.%d")
    assert task_map["테스트"]["metadata"]["start_date"] == windows["테스트"][0].strftime("%Y.%m.%d")
    assert task_map["이행"]["metadata"]["start_date"] == windows["이행"][0].strftime("%Y.%m.%d")
    assert task_map["안정화"]["metadata"]["start_date"] == windows["안정화"][0].strftime("%Y.%m.%d")
    assert task_map["분석"]["metadata"]["start_date"] == windows["분석"][0].strftime("%Y.%m.%d")
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
    assert response.result is not None

    tasks = response.result["tasks"]
    task_map = {task["metadata"]["wbs_id"]: task for task in tasks}
    project_start = date(2026, 1, 1)
    project_end = date(2026, 7, 1)

    def expected_windows(start: date, end: date) -> dict[str, tuple[date, date]]:
        total_days = max((end - start).days + 1, 1)
        cumulative = 0.0
        previous_cut = 0
        current_start = start
        raw_windows: dict[str, tuple[date, date]] = {}
        ratios = WbsAgent._development_phase_ratios()
        for index, (phase_name, ratio) in enumerate(ratios):
            cumulative += ratio
            if index == len(ratios) - 1:
                cut_day_count = total_days
            else:
                cut_day_count = floor(total_days * cumulative)
                cut_day_count = max(cut_day_count, previous_cut + 1)
                cut_day_count = min(cut_day_count, total_days - (len(ratios) - index - 1))
            phase_end = start + timedelta(days=cut_day_count - 1)
            raw_windows[phase_name] = (current_start, phase_end)
            current_start = phase_end + timedelta(days=1)
            previous_cut = cut_day_count

        windows: dict[str, tuple[date, date]] = {}
        for phase_name, (raw_start, raw_end) in raw_windows.items():
            windows[phase_name] = agent._align_to_week_boundaries(raw_start, raw_end)
        return windows

    windows = expected_windows(project_start, project_end)

    requirement_start, requirement_end = windows["요구사항정의"]
    analysis_end = windows["분석"][1]
    design_end = windows["설계"][1]
    implementation_start, implementation_end = windows["구현"]
    test_start, test_end = windows["테스트"]
    stabilization_start, stabilization_end = windows["안정화"]
    transition_end = windows["이행"][1]

    plan_start, plan_end = agent._align_to_week_boundaries(
        requirement_end - timedelta(weeks=1),
        requirement_end,
    )
    cutover_start, cutover_end = agent._align_to_week_boundaries(
        transition_end - timedelta(weeks=2),
        transition_end - timedelta(weeks=1),
    )
    stabilization_start, stabilization_end = agent._align_to_week_boundaries(
        stabilization_start,
        stabilization_end,
    )
    requirement_review_start, requirement_review_end = agent._align_to_week_boundaries(
        analysis_end - timedelta(weeks=1),
        analysis_end,
    )
    implementation_review_start, implementation_review_end = agent._align_to_week_boundaries(
        implementation_end - timedelta(weeks=1),
        implementation_end,
    )
    requirement_area_start, requirement_area_end = agent._align_to_week_boundaries(
        requirement_start,
        requirement_end,
    )
    infra_env_start, infra_env_end = agent._align_to_week_boundaries(
        implementation_start,
        implementation_start + timedelta(weeks=3),
    )
    infra_test_start, infra_test_end = agent._align_to_week_boundaries(
        test_start - timedelta(weeks=1),
        test_end,
    )

    assert task_map["1.1.1"]["metadata"]["start_date"] == plan_start.strftime("%Y.%m.%d")
    assert task_map["1.1.1"]["metadata"]["end_date"] == plan_end.strftime("%Y.%m.%d")
    assert task_map["1.1.1.1"]["metadata"]["start_date"] == plan_start.strftime("%Y.%m.%d")
    assert task_map["1.1.1.1"]["metadata"]["end_date"] == plan_end.strftime("%Y.%m.%d")
    assert task_map["1.1.1.3"]["metadata"]["start_date"] == plan_start.strftime("%Y.%m.%d")
    assert task_map["1.1.1.3"]["metadata"]["end_date"] == plan_end.strftime("%Y.%m.%d")

    assert task_map["1.1.1.4"]["metadata"]["start_date"] == requirement_end.strftime("%Y.%m.%d")
    assert task_map["1.1.1.4"]["metadata"]["end_date"] == requirement_end.strftime("%Y.%m.%d")

    assert task_map["1.1.2"]["metadata"]["start_date"] == cutover_start.strftime("%Y.%m.%d")
    assert task_map["1.1.2"]["metadata"]["end_date"] == cutover_end.strftime("%Y.%m.%d")
    assert task_map["1.1.2.1"]["metadata"]["start_date"] == cutover_start.strftime("%Y.%m.%d")
    assert task_map["1.1.2.1"]["metadata"]["end_date"] == cutover_end.strftime("%Y.%m.%d")

    assert task_map["1.1.3"]["metadata"]["start_date"] == stabilization_start.strftime("%Y.%m.%d")
    assert task_map["1.1.3"]["metadata"]["end_date"] == stabilization_end.strftime("%Y.%m.%d")
    assert task_map["1.1.3.1"]["metadata"]["start_date"] == stabilization_start.strftime("%Y.%m.%d")
    assert task_map["1.1.3.1"]["metadata"]["end_date"] == stabilization_end.strftime("%Y.%m.%d")
    assert task_map["1.1.3.2"]["metadata"]["start_date"] == stabilization_start.strftime("%Y.%m.%d")
    assert task_map["1.1.3.2"]["metadata"]["end_date"] == stabilization_end.strftime("%Y.%m.%d")

    assert task_map["1.3.2.1"]["metadata"]["start_date"] == requirement_review_start.strftime("%Y.%m.%d")
    assert task_map["1.3.2.1"]["metadata"]["end_date"] == requirement_review_end.strftime("%Y.%m.%d")
    assert task_map["1.3.2.1.1"]["metadata"]["start_date"] == requirement_review_start.strftime("%Y.%m.%d")
    assert task_map["1.3.2.1.1"]["metadata"]["end_date"] == requirement_review_end.strftime("%Y.%m.%d")
    assert task_map["1.3.2.1.2"]["metadata"]["start_date"] == requirement_review_start.strftime("%Y.%m.%d")
    assert task_map["1.3.2.1.2"]["metadata"]["end_date"] == requirement_review_end.strftime("%Y.%m.%d")
    assert task_map["1.3.2.2"]["metadata"]["start_date"] == implementation_review_start.strftime("%Y.%m.%d")
    assert task_map["1.3.2.2"]["metadata"]["end_date"] == implementation_review_end.strftime("%Y.%m.%d")
    assert task_map["1.3.2.2.1"]["metadata"]["start_date"] == implementation_review_start.strftime("%Y.%m.%d")
    assert task_map["1.3.2.2.1"]["metadata"]["end_date"] == implementation_review_end.strftime("%Y.%m.%d")

    assert task_map["2.1"]["metadata"]["start_date"] == requirement_area_start.strftime("%Y.%m.%d")
    assert task_map["2.1"]["metadata"]["end_date"] == requirement_area_end.strftime("%Y.%m.%d")
    assert task_map["2.1.1"]["metadata"]["start_date"] == requirement_area_start.strftime("%Y.%m.%d")
    assert task_map["2.1.1"]["metadata"]["end_date"] == requirement_area_end.strftime("%Y.%m.%d")
    assert task_map["2.2.1"]["metadata"]["start_date"] == requirement_area_start.strftime("%Y.%m.%d")
    assert task_map["2.2.1"]["metadata"]["end_date"] == requirement_area_end.strftime("%Y.%m.%d")

    assert task_map["2.2.2"]["metadata"]["start_date"] == infra_env_start.strftime("%Y.%m.%d")
    assert task_map["2.2.2"]["metadata"]["end_date"] == infra_env_end.strftime("%Y.%m.%d")
    assert task_map["2.2.3"]["metadata"]["start_date"] == infra_env_start.strftime("%Y.%m.%d")
    assert task_map["2.2.3"]["metadata"]["end_date"] == infra_env_end.strftime("%Y.%m.%d")

    assert task_map["2.2.4"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.1"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.1"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.2"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.2"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.3"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.3"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.4"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.4"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.5"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.5"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")
    assert task_map["2.2.4.6"]["metadata"]["start_date"] == infra_test_start.strftime("%Y.%m.%d")
    assert task_map["2.2.4.6"]["metadata"]["end_date"] == infra_test_end.strftime("%Y.%m.%d")

    test_plan_start, test_plan_end = agent._align_to_week_boundaries(
        design_end - timedelta(weeks=1),
        design_end,
    )
    unit_test_start, unit_test_end = agent._align_to_week_boundaries(
        implementation_end - timedelta(weeks=2),
        implementation_end,
    )
    integration_test_start, integration_test_end = agent._align_to_week_boundaries(
        test_start,
        test_end - timedelta(weeks=1),
    )
    uat_start, uat_end = agent._align_to_week_boundaries(
        test_end - timedelta(weeks=1),
        test_end,
    )

    assert task_map["3.3.5"]["metadata"]["start_date"] == test_plan_start.strftime("%Y.%m.%d")
    assert task_map["3.3.5"]["metadata"]["end_date"] == test_plan_end.strftime("%Y.%m.%d")
    assert task_map["3.3.5.1"]["metadata"]["start_date"] == test_plan_start.strftime("%Y.%m.%d")
    assert task_map["3.3.5.1"]["metadata"]["end_date"] == test_plan_end.strftime("%Y.%m.%d")

    assert task_map["3.4.3"]["metadata"]["start_date"] == unit_test_start.strftime("%Y.%m.%d")
    assert task_map["3.4.3"]["metadata"]["end_date"] == unit_test_end.strftime("%Y.%m.%d")
    assert task_map["3.4.3.1"]["metadata"]["start_date"] == unit_test_start.strftime("%Y.%m.%d")
    assert task_map["3.4.3.1"]["metadata"]["end_date"] == unit_test_end.strftime("%Y.%m.%d")

    assert task_map["3.5.1"]["metadata"]["start_date"] == integration_test_start.strftime("%Y.%m.%d")
    assert task_map["3.5.1"]["metadata"]["end_date"] == integration_test_end.strftime("%Y.%m.%d")
    assert task_map["3.5.1.1"]["metadata"]["start_date"] == integration_test_start.strftime("%Y.%m.%d")
    assert task_map["3.5.1.1"]["metadata"]["end_date"] == integration_test_end.strftime("%Y.%m.%d")
    assert task_map["3.5.1.2"]["metadata"]["start_date"] == integration_test_start.strftime("%Y.%m.%d")
    assert task_map["3.5.1.2"]["metadata"]["end_date"] == integration_test_end.strftime("%Y.%m.%d")
    assert task_map["3.5.1.3"]["metadata"]["start_date"] == integration_test_start.strftime("%Y.%m.%d")
    assert task_map["3.5.1.3"]["metadata"]["end_date"] == integration_test_end.strftime("%Y.%m.%d")

    assert task_map["3.5.3"]["metadata"]["start_date"] == uat_start.strftime("%Y.%m.%d")
    assert task_map["3.5.3"]["metadata"]["end_date"] == uat_end.strftime("%Y.%m.%d")
    assert task_map["3.5.3.1"]["metadata"]["start_date"] == uat_start.strftime("%Y.%m.%d")
    assert task_map["3.5.3.1"]["metadata"]["end_date"] == uat_end.strftime("%Y.%m.%d")

    assert task_map["3.6.2"]["metadata"]["start_date"] == (transition_end - timedelta(days=3)).strftime("%Y.%m.%d")
    assert task_map["3.6.2"]["metadata"]["end_date"] == transition_end.strftime("%Y.%m.%d")
    assert task_map["3.6.2.1"]["metadata"]["start_date"] == (transition_end - timedelta(days=3)).strftime("%Y.%m.%d")
    assert task_map["3.6.2.1"]["metadata"]["end_date"] == (transition_end - timedelta(days=1)).strftime("%Y.%m.%d")
    assert task_map["3.6.2.3"]["metadata"]["start_date"] == transition_end.strftime("%Y.%m.%d")
    assert task_map["3.6.2.3"]["metadata"]["end_date"] == transition_end.strftime("%Y.%m.%d")


@pytest.mark.anyio
async def test_wbs_agent_uses_common_prefix_rows() -> None:
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
                        }
                    ]
                },
            },
        )
    )

    assert response.success is True
    assert response.result is not None

    tasks = response.result["tasks"]
    template_rows = load_wbs_common_rows()

    assert len(tasks) == len(template_rows)
    for task, template_row in zip(tasks, template_rows, strict=True):
        assert task["metadata"]["level"] == template_row["level"]
        assert task["metadata"]["wbs_id"] == template_row["wbs_id"]
        assert task["name"] == template_row["wbs_name"]


def test_wbs_common_rows_ignore_s3_template_backend(monkeypatch) -> None:
    monkeypatch.setattr("util.agent_template_utils.settings.S3_STORAGE_BACKEND", "s3")

    rows = load_wbs_common_rows()

    assert len(rows) == 85
    assert rows[-1]["wbs_name"] == "안정화 수행"
