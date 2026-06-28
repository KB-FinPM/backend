# EN: Project persistence helpers and repository operations.
# KO: Repository에서 공통으로 사용하는 프로젝트 저장 헬퍼입니다.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectModel
from app.schemas.project import ProjectCreate, ProjectMetadata, ProjectUpdate


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_project(self, request: ProjectCreate) -> ProjectMetadata:
        project = ProjectModel(
            project_id=request.project_id,
            project_name=request.project_name,
            description=request.description,
            start_date=request.start_date,
            end_date=request.end_date,
            status=request.status or "ACTIVE",
            created_by=request.created_by,
            document_author=request.document_author,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return self._to_metadata(project)

    async def get_project(self, project_id: str) -> ProjectMetadata | None:
        project = await self._get_project_model(project_id)
        if project is None:
            return None
        return self._to_metadata(project)

    async def list_projects(self) -> list[ProjectMetadata]:
        statement = select(ProjectModel).order_by(ProjectModel.updated_at.desc())
        result = await self.session.execute(statement)
        return [self._to_metadata(project) for project in result.scalars().all()]

    async def update_project(
        self,
        project_id: str,
        request: ProjectUpdate,
    ) -> ProjectMetadata | None:
        project = await self._get_project_model(project_id)
        if project is None:
            return None

        values = request.model_dump(exclude_unset=True)
        for field_name, value in values.items():
            if field_name == "project_name" and not value:
                continue
            if hasattr(project, field_name):
                setattr(project, field_name, value)

        await self.session.commit()
        await self.session.refresh(project)
        return self._to_metadata(project)

    async def _get_project_model(self, project_id: str) -> ProjectModel | None:
        statement = select(ProjectModel).where(ProjectModel.project_id == project_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    def _to_metadata(self, project: ProjectModel) -> ProjectMetadata:
        return ProjectMetadata(
            project_id=project.project_id,
            project_name=project.project_name,
            description=project.description,
            start_date=project.start_date,
            end_date=project.end_date,
            status=project.status,
            created_by=project.created_by,
            document_author=project.document_author,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


async def ensure_project(
    session: AsyncSession,
    *,
    project_id: str,
    project_name: str | None = None,
) -> ProjectModel:
    statement = select(ProjectModel).where(ProjectModel.project_id == project_id)
    result = await session.execute(statement)
    project = result.scalar_one_or_none()
    if project is not None:
        return project

    project = ProjectModel(
        project_id=project_id,
        project_name=project_name or project_id,
    )
    session.add(project)
    await session.flush()
    return project
