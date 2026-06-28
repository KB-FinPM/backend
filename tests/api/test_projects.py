from fastapi.testclient import TestClient

from app.dependencies import get_project_service, get_schedule_service
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate
from app.schemas.todo import (
    TodoDuplicateItem,
    TodoImportCommitResponse,
    TodoImportPreviewResponse,
    TodoItem,
    TodoListResponse,
)


class StubProjectService:
    def __init__(self) -> None:
        self.projects: dict[str, ProjectMetadata] = {}

    async def create_project(self, request: ProjectCreate) -> ProjectMetadata:
        project = ProjectMetadata(
            project_id=request.project_id,
            project_name=request.project_name,
            description=request.description,
            start_date=request.start_date,
            end_date=request.end_date,
            status=request.status or "ACTIVE",
            created_by=request.created_by,
            document_author=request.document_author,
        )
        self.projects[project.project_id] = project
        return project

    async def get_project(self, project_id: str) -> ProjectMetadata | None:
        return self.projects.get(project_id)

    async def list_projects(self) -> list[ProjectMetadata]:
        return list(self.projects.values())

    async def update_project(
        self,
        project_id: str,
        request: ProjectUpdate,
    ) -> ProjectMetadata | None:
        project = self.projects.get(project_id)
        if project is None:
            return None
        updated_project = project.model_copy(update=request.model_dump(exclude_none=True))
        self.projects[project_id] = updated_project
        return updated_project


class StubTodoScheduleService:
    def __init__(self) -> None:
        self.list_call: dict | None = None
        self.update_call: dict | None = None
        self.preview_call: dict | None = None
        self.commit_call: dict | None = None

    async def list_todos(
        self,
        *,
        project_id: str,
        status_filter: str | None = None,
        source_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> TodoListResponse:
        self.list_call = {
            "project_id": project_id,
            "status_filter": status_filter,
            "source_type": source_type,
            "date_from": date_from,
            "date_to": date_to,
        }
        return TodoListResponse(
            items=[
                TodoItem(
                    todo_id="TODO-001",
                    title="회의록 TODO",
                    assignee="김PM",
                    due_date="2026-06-30",
                    status="NOT_STARTED",
                    source_type="MEETING_NOTES",
                    source_document_id="DOC-001",
                    source_document_name="meeting.md",
                )
            ]
        )

    async def update_todo(
        self,
        *,
        project_id: str,
        todo_id: str,
        values: dict,
    ) -> TodoItem:
        self.update_call = {
            "project_id": project_id,
            "todo_id": todo_id,
            "values": values,
        }
        return TodoItem(
            todo_id=todo_id,
            title=values.get("title") or "회의록 TODO",
            assignee=values.get("assignee"),
            due_date=values.get("due_date"),
            status=values.get("status") or "NOT_STARTED",
            source_type="MEETING_NOTES",
        )

    async def delete_todo(self, *, project_id: str, todo_id: str) -> bool:
        return todo_id == "TODO-001"

    async def preview_todo_import(
        self,
        *,
        project_id: str,
        document_id: str,
        document_type: str,
    ) -> TodoImportPreviewResponse:
        self.preview_call = {
            "project_id": project_id,
            "document_id": document_id,
            "document_type": document_type,
        }
        candidate = TodoItem(
            todo_id="IMPORT-001",
            title="신규 TODO",
            status="NOT_STARTED",
            source_type=document_type,
            source_document_id=document_id,
        )
        existing = TodoItem(
            todo_id="TODO-EXISTING",
            title="기존 TODO",
            status="IN_PROGRESS",
            source_type=document_type,
        )
        return TodoImportPreviewResponse(
            new_items=[candidate],
            duplicate_items=[
                TodoDuplicateItem(
                    candidate=candidate,
                    matched_existing=existing,
                    duplicate_level="DUPLICATE_POSSIBLE",
                )
            ],
            metadata={"document_id": document_id},
        )

    async def commit_todo_import(
        self,
        *,
        project_id: str,
        items: list[dict],
        duplicate_decisions: list[dict[str, str]] | None = None,
    ) -> TodoImportCommitResponse:
        self.commit_call = {
            "project_id": project_id,
            "items": items,
            "duplicate_decisions": duplicate_decisions,
        }
        return TodoImportCommitResponse(
            saved_items=[
                TodoItem(
                    todo_id="TODO-SAVED",
                    title=items[0]["title"],
                    status="NOT_STARTED",
                    source_type=items[0]["source_type"],
                )
            ],
            metadata={"saved_count": 1},
        )


def test_create_project_response_id_can_be_used_for_detail_lookup(
    client: TestClient,
) -> None:
    service = StubProjectService()
    client.app.dependency_overrides[get_project_service] = lambda: service

    try:
        create_response = client.post(
            "/api/projects",
            json={
                "project_id": "  PRJ-NEW  ",
                "project_name": "신규 프로젝트",
                "description": "created from API",
                "document_author": "홍길동 PM",
            },
        )
        assert create_response.status_code == 201
        created_project_id = create_response.json()["project_id"]

        detail_response = client.get(f"/api/projects/{created_project_id}")
    finally:
        client.app.dependency_overrides.clear()

    assert created_project_id == "PRJ-NEW"
    assert detail_response.status_code == 200
    assert detail_response.json()["project_id"] == created_project_id
    assert detail_response.json()["project_name"] == "신규 프로젝트"
    assert detail_response.json()["document_author"] == "홍길동 PM"


def test_update_project_preserves_document_author(
    client: TestClient,
) -> None:
    service = StubProjectService()
    service.projects["PRJ-AUTHOR"] = ProjectMetadata(
        project_id="PRJ-AUTHOR",
        project_name="기존 프로젝트",
        document_author=None,
    )
    client.app.dependency_overrides[get_project_service] = lambda: service

    try:
        response = client.patch(
            "/api/projects/PRJ-AUTHOR",
            json={
                "project_name": "작성자 프로젝트",
                "document_author": "KBDS AI Hackathon 팀",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["project_name"] == "작성자 프로젝트"
    assert response.json()["document_author"] == "KBDS AI Hackathon 팀"


def test_get_project_returns_not_found_only_when_project_is_missing(
    client: TestClient,
) -> None:
    service = StubProjectService()
    client.app.dependency_overrides[get_project_service] = lambda: service

    try:
        response = client.get("/api/projects/PRJ-MISSING")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "PROJECT_NOT_FOUND"
    assert body["detail"] == {"project_id": "PRJ-MISSING"}


def test_list_project_todos_routes_filters_to_schedule_service(
    client: TestClient,
) -> None:
    service = StubTodoScheduleService()
    client.app.dependency_overrides[get_schedule_service] = lambda: service

    try:
        response = client.get(
            "/api/projects/PRJ-001/todos"
            "?status=NOT_STARTED&source_type=MEETING_NOTES&from=2026-06-01&to=2026-06-30"
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["todo_id"] == "TODO-001"
    assert service.list_call == {
        "project_id": "PRJ-001",
        "status_filter": "NOT_STARTED",
        "source_type": "MEETING_NOTES",
        "date_from": "2026-06-01",
        "date_to": "2026-06-30",
    }


def test_update_project_todo_routes_patch_payload_to_schedule_service(
    client: TestClient,
) -> None:
    service = StubTodoScheduleService()
    client.app.dependency_overrides[get_schedule_service] = lambda: service

    try:
        response = client.patch(
            "/api/projects/PRJ-001/todos/TODO-001",
            json={
                "title": "수정된 TODO",
                "assignee": "박PM",
                "due_date": "2026-07-01",
                "status": "IN_PROGRESS",
                "description": "상세",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"
    assert service.update_call == {
        "project_id": "PRJ-001",
        "todo_id": "TODO-001",
        "values": {
            "title": "수정된 TODO",
            "assignee": "박PM",
            "due_date": "2026-07-01",
            "status": "IN_PROGRESS",
            "description": "상세",
        },
    }


def test_project_todo_import_preview_and_commit_route_to_schedule_service(
    client: TestClient,
) -> None:
    service = StubTodoScheduleService()
    client.app.dependency_overrides[get_schedule_service] = lambda: service

    try:
        preview_response = client.post(
            "/api/projects/PRJ-001/todos/import/preview",
            json={"document_id": "DOC-001", "document_type": "MEETING_NOTES"},
        )
        commit_response = client.post(
            "/api/projects/PRJ-001/todos/import/commit",
            json={
                "items": [
                    {
                        "todo_id": "IMPORT-001",
                        "title": "신규 TODO",
                        "status": "NOT_STARTED",
                        "source_type": "MEETING_NOTES",
                    }
                ],
                "duplicate_decisions": [
                    {"client_import_id": "IMPORT-001", "decision": "ADD"}
                ],
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert preview_response.status_code == 200
    assert preview_response.json()["duplicate_items"][0]["duplicate_level"] == (
        "DUPLICATE_POSSIBLE"
    )
    assert service.preview_call == {
        "project_id": "PRJ-001",
        "document_id": "DOC-001",
        "document_type": "MEETING_NOTES",
    }
    assert commit_response.status_code == 200
    assert commit_response.json()["saved_items"][0]["todo_id"] == "TODO-SAVED"
    assert service.commit_call["project_id"] == "PRJ-001"
    assert service.commit_call["items"][0]["title"] == "신규 TODO"
