# EN: Small project persistence helpers shared by repositories.
# KO: Repository에서 공통으로 사용하는 프로젝트 저장 헬퍼입니다.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectModel


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
