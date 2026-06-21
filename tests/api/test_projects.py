from fastapi.testclient import TestClient

from app.dependencies import get_project_service
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate


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
