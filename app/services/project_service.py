from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate


class ProjectService:
    def __init__(self, project_repository: ProjectRepository) -> None:
        self.project_repository = project_repository

    async def create_project(self, request: ProjectCreate) -> ProjectMetadata:
        return await self.project_repository.create_project(request)

    async def get_project(self, project_id: str) -> ProjectMetadata | None:
        return await self.project_repository.get_project(project_id)

    async def list_projects(self) -> list[ProjectMetadata]:
        return await self.project_repository.list_projects()

    async def update_project(
        self,
        project_id: str,
        request: ProjectUpdate,
    ) -> ProjectMetadata | None:
        return await self.project_repository.update_project(project_id, request)
