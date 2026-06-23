# EN: Tests for schedule service delegation behavior.

from datetime import date
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


class StubCompleteActionItemRepository:
    def __init__(self) -> None:
        self.completed_ids: list[str] = []
        self.todos = [
            {"todo_id": "TODO-001", "title": "회의록 TODO", "status": "TODO"},
            {"todo_id": "TODO-002", "title": "WBS TODO", "status": "TODO"},
        ]

    async def complete_todo_by_id(self, *, project_id: str, todo_id: str):
        self.completed_ids.append(todo_id)
        for todo in self.todos:
            if todo["todo_id"] == todo_id:
                todo["status"] = "DONE"
                return {**todo}
        return None

    async def list_project_todos(self, *, project_id: str) -> list[dict]:
        return [{**todo} for todo in self.todos]


class StubTodoDateRepository:
    async def list_project_todos(self, *, project_id: str) -> list[dict]:
        return [
            {"todo_id": "TODO-EMPTY", "title": "Empty due date", "status": "TODO"},
            {
                "todo_id": "TODO-YEARLESS",
                "title": "Yearless due date",
                "status": "TODO",
                "due_date": "01.17",
            },
            {
                "todo_id": "TODO-EXPLICIT",
                "title": "Explicit due date",
                "status": "TODO",
                "due_date": "2025.01.17",
            },
        ]


@pytest.mark.anyio
async def test_schedule_service_completes_todo_by_id_without_matching() -> None:
    action_item_repository = StubCompleteActionItemRepository()
    service = ScheduleService(
        orchestrator=StubScheduleOrchestrator(),
        action_item_repository=action_item_repository,
    )

    response = await service.complete_todo_by_id(
        project_id="PRJ-001",
        todo_id="TODO-002",
    )

    assert response.success is True
    assert action_item_repository.completed_ids == ["TODO-002"]
    assert response.result["matched_todo"]["todo_id"] == "TODO-002"
    assert response.result["matched_todo"]["next_status"] == "DONE"
    assert [todo["todo_id"] for todo in response.result["remaining_todos"]] == [
        "TODO-001"
    ]


@pytest.mark.anyio
async def test_schedule_service_complete_todo_by_id_returns_not_found() -> None:
    service = ScheduleService(
        orchestrator=StubScheduleOrchestrator(),
        action_item_repository=StubCompleteActionItemRepository(),
    )

    response = await service.complete_todo_by_id(
        project_id="PRJ-001",
        todo_id="TODO-404",
    )

    assert response.success is False
    assert response.result["status"] == "NOT_FOUND"


@pytest.mark.anyio
async def test_schedule_service_normalizes_todo_due_dates_for_manager() -> None:
    service = ScheduleService(
        orchestrator=StubScheduleOrchestrator(),
        action_item_repository=StubTodoDateRepository(),
    )

    response = await service.list_todos(project_id="PRJ-001")

    due_dates = {item.todo_id: item.due_date for item in response.items}
    assert due_dates["TODO-EMPTY"] == date.today().isoformat()
    assert due_dates["TODO-YEARLESS"] == f"{date.today().year}-01-17"
    assert due_dates["TODO-EXPLICIT"] == "2025-01-17"


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
