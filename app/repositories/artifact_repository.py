# EN: Repository for generated artifact persistence and lookup.
# KO: 생성된 산출물 저장과 조회를 담당하는 Repository입니다.

from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import ArtifactDocumentModel, ArtifactModel, ArtifactVersionModel
from app.repositories.project_repository import ensure_project
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
        await ensure_project(self.session, project_id=project_id)
        artifact = ArtifactModel(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=artifact_type.value,
            name=name,
            latest_version=1,
            template_id=template_id,
            template_version=template_version,
            storage_path=storage_path,
        )
        self.session.add(artifact)
        self.session.add(
            ArtifactVersionModel(
                artifact_version_id=f"ARTV-{uuid4().hex[:12].upper()}",
                artifact_id=artifact_id,
                version=1,
                result_json=result_json,
                storage_path=storage_path,
            )
        )
        for document_id in source_document_ids:
            self.session.add(
                ArtifactDocumentModel(
                    artifact_id=artifact_id,
                    document_id=document_id,
                )
            )
        await self.session.commit()
        await self.session.refresh(artifact)
        await self._attach_latest_payload(artifact)
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
        artifact = result.scalar_one_or_none()
        if artifact is None:
            return None
        await self._attach_latest_payload(artifact)
        return artifact

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
        artifacts = list(result.scalars().all())
        for artifact in artifacts:
            await self._attach_latest_payload(artifact)
        return artifacts

    async def _attach_latest_payload(self, artifact: ArtifactModel) -> None:
        version_statement = select(ArtifactVersionModel).where(
            ArtifactVersionModel.artifact_id == artifact.artifact_id,
            ArtifactVersionModel.version == artifact.latest_version,
        )
        version_result = await self.session.execute(version_statement)
        artifact_version = version_result.scalar_one_or_none()

        document_statement = select(ArtifactDocumentModel.document_id).where(
            ArtifactDocumentModel.artifact_id == artifact.artifact_id,
        )
        document_result = await self.session.execute(document_statement)

        artifact.version = artifact.latest_version
        artifact.result_json = (
            artifact_version.result_json if artifact_version is not None else {}
        )
        artifact.source_document_ids = list(document_result.scalars().all())
