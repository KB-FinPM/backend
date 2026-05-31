# EN: Repository for generated artifact persistence and lookup.
# KO: 생성된 산출물 저장과 조회를 담당하는 Repository입니다.

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import ArtifactModel
from app.schemas.artifact import ArtifactType


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_artifact(
        self,
        *,
        artifact_id: str,
        project_id: str,
        artifact_type: ArtifactType,
        name: str,
        source_document_ids: list[str],
        result_json: dict[str, Any],
        template_id: Optional[str] = None,
        template_version: Optional[str] = None,
        storage_path: Optional[str] = None,
    ) -> ArtifactModel:
        artifact = ArtifactModel(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=artifact_type.value,
            name=name,
            source_document_ids=source_document_ids,
            template_id=template_id,
            template_version=template_version,
            result_json=result_json,
            storage_path=storage_path,
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> Optional[ArtifactModel]:
        statement = select(ArtifactModel).where(
            ArtifactModel.project_id == project_id,
            ArtifactModel.artifact_id == artifact_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_artifacts_by_project(
        self,
        *,
        project_id: str,
    ) -> list[ArtifactModel]:
        statement = (
            select(ArtifactModel)
            .where(ArtifactModel.project_id == project_id)
            .order_by(ArtifactModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
