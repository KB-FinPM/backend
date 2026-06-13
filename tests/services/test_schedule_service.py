# EN: Tests for schedule service delegation behavior.

from types import SimpleNamespace

import pytest

from app.orchestrator.schedule_orchestrator import ScheduleOrchestrator
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse
from app.services.schedule_service import ScheduleService


class StubScheduleOrchestrator:
    def __init__(self) -> None:
        self.received_context: dict | None = None

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict | None = None,
    ) -> ScheduleTodoResponse:
        self.received_context = structured_context
        return ScheduleTodoResponse(
            project_id=request.project_id,
            result={"source": "stub-orchestrator"},
        )


@pytest.mark.anyio
async def test_schedule_service_delegates_to_orchestrator() -> None:
    orchestrator = StubScheduleOrchestrator()
    service = ScheduleService(orchestrator=orchestrator)

    response = await service.extract_todos(
        ScheduleTodoRequest(
            project_id="PRJ-001",
            meeting_notes="Discussed login scope.",
        ),
        structured_context={"normalized": True},
    )

    assert response.project_id == "PRJ-001"
    assert response.result == {"source": "stub-orchestrator"}
    assert orchestrator.received_context == {"normalized": True}


class StubActionItemRepository:
    def __init__(self) -> None:
        self.saved_wbs_todos: list[dict] = []

    async def list_project_todos(self, *, project_id: str) -> list[dict]:
        return []

    async def upsert_wbs_todos(
        self,
        *,
        project_id: str,
        todos: list[dict],
    ) -> list[dict]:
        self.saved_wbs_todos = [
            {**todo, "todo_id": f"TODO-WBS-{index:03d}", "status": "TODO"}
            for index, todo in enumerate(todos, start=1)
        ]
        return self.saved_wbs_todos


class StubArtifactRepository:
    async def list_artifacts_by_project(self, *, project_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                artifact_id="ART-WBS-001",
                artifact_type="WBS",
                name="generated-wbs.xlsx",
                result_json={
                    "artifact_type": "WBS",
                    "tasks": [
                        {
                            "task_id": "WBS-001",
                            "name": "설계 및 테스트",
                            "planned_start_date": "2026-06-08",
                            "planned_end_date": "2026-06-14",
                            "metadata": {
                                "level": "2",
                                "worker": "PM",
                                "wbs_id": "1.1",
                            },
                        }
                    ],
                },
            )
        ]


class StubNestedArtifactRepository:
    async def list_artifacts_by_project(self, *, project_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                artifact_id="ART-WBS-002",
                artifact_type="WBS",
                name="generated-wbs-nested.xlsx",
                result_json={
                    "artifact_type": "WBS",
                    "generated": {
                        "rows": [
                            {
                                "task_id": "WBS-002",
                                "name": "개발 및 테스트",
                                "start_date": "2026-06-08",
                                "end_date": "2026-06-14",
                            }
                        ],
                    },
                },
            )
        ]


@pytest.mark.anyio
async def test_schedule_service_uses_generated_wbs_artifact_without_upload() -> None:
    action_item_repository = StubActionItemRepository()
    service = ScheduleService(
        orchestrator=ScheduleOrchestrator(),
        action_item_repository=action_item_repository,
        artifact_repository=StubArtifactRepository(),
    )

    response = await service.run_query(
        project_id="PRJ-001",
        schedule_action="SHOW_THIS_WEEK_TODOS",
        context={
            "current_date": "2026-06-10",
            "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
        },
    )

    assert response.success is True
    assert response.result["status"] == "SUCCESS"
    assert response.result["todos"][0]["todo_id"] == "TODO-WBS-001"
    assert response.result["todos"][0]["title"] == "설계 및 테스트"
    assert response.result["metadata"]["wbs_todos_saved"] is True
    assert action_item_repository.saved_wbs_todos


@pytest.mark.anyio
async def test_schedule_service_reads_generated_wbs_rows_from_nested_artifact() -> None:
    action_item_repository = StubActionItemRepository()
    service = ScheduleService(
        orchestrator=ScheduleOrchestrator(),
        action_item_repository=action_item_repository,
        artifact_repository=StubNestedArtifactRepository(),
    )

    response = await service.run_query(
        project_id="PRJ-001",
        schedule_action="SHOW_THIS_WEEK_TODOS",
        context={
            "current_date": "2026-06-10",
            "normalized_input": {"needs_context": ["WBS", "TODO_LIST"]},
        },
    )

    assert response.success is True
    assert response.result["status"] == "SUCCESS"
    assert response.result["todos"][0]["title"] == "개발 및 테스트"
    assert response.result["todos"][0]["source_artifact_id"] == "ART-WBS-002"
