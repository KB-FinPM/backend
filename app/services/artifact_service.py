# EN: Business service for generated artifact persistence and lookup.
# KO: 생성 산출물 저장과 조회를 담당하는 비즈니스 서비스입니다.

from pathlib import PurePath
from typing import Any

from app.models.artifact import ArtifactModel
from app.repositories.artifact_repository import ArtifactRepository
from app.schemas.artifact import ArtifactMetadata, ArtifactStatus, ArtifactType


class ArtifactService:
    """Coordinates artifact use cases without exposing repositories to routers."""

    def __init__(self, artifact_repository: ArtifactRepository) -> None:
        self.artifact_repository = artifact_repository

    async def create_artifact(
        self,
        *,
        artifact_id: str,
        project_id: str,
        artifact_type: ArtifactType,
        name: str,
        source_document_ids: list[str],
        result_json: dict[str, Any],
        template_id: str | None = None,
        template_version: str | None = None,
        storage_path: str | None = None,
    ) -> ArtifactMetadata:
        artifact = await self.artifact_repository.create_artifact(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=artifact_type,
            name=name,
            source_document_ids=source_document_ids,
            result_json=result_json,
            template_id=template_id,
            template_version=template_version,
            storage_path=storage_path,
        )
        return self._to_metadata(artifact)

    async def get_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactMetadata | None:
        artifact = await self.artifact_repository.get_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
        )
        if artifact is None:
            return None

        return self._to_metadata(artifact)

    async def list_artifacts(self, *, project_id: str) -> list[ArtifactMetadata]:
        artifacts = await self.artifact_repository.list_artifacts_by_project(
            project_id=project_id,
        )
        return [self._to_metadata(artifact) for artifact in artifacts]

    def _to_metadata(self, artifact: ArtifactModel) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=artifact.artifact_id,
            project_id=artifact.project_id,
            artifact_type=ArtifactType(artifact.artifact_type),
            name=artifact.name,
            file_name=self._file_name_for_artifact(artifact),
            version=artifact.version,
            source_document_ids=artifact.source_document_ids or [],
            template_id=artifact.template_id,
            template_version=artifact.template_version,
            result_json=artifact.result_json or {},
            storage_path=artifact.storage_path,
            status=ArtifactStatus(artifact.status),
        )

    def _file_name_for_artifact(self, artifact: ArtifactModel) -> str | None:
        if artifact.storage_path:
            file_name = PurePath(artifact.storage_path).name
            if file_name:
                return file_name
        return artifact.name or None
