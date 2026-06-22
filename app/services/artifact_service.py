# EN: Business service for generated artifact persistence and lookup.
# KO: 생성 산출물 저장과 조회를 담당하는 비즈니스 서비스입니다.

from pathlib import PurePath
from typing import Any

from app.models.artifact import ArtifactModel
from app.repositories.artifact_repository import ArtifactRepository
from app.schemas.artifact import ArtifactMetadata, ArtifactStatus, ArtifactType
from app.storage.s3 import S3Service

ARTIFACT_FILE_EXTENSIONS = {
    ArtifactType.REQUIREMENT_SPEC: ".xlsx",
    ArtifactType.WBS: ".xlsx",
    ArtifactType.SCREEN_DESIGN: ".pptx",
    ArtifactType.UNITTEST_SPEC: ".xlsx",
}


class ArtifactService:
    """Coordinates artifact use cases without exposing repositories to routers."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        storage_service: S3Service | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.storage_service = storage_service

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
        version: int = 1,
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
            version=version,
        )
        return self._to_metadata(artifact)

    async def get_next_version(
        self,
        *,
        project_id: str,
        artifact_type: ArtifactType,
    ) -> int:
        return await self.artifact_repository.get_next_version(
            project_id=project_id,
            artifact_type=artifact_type,
        )

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

    async def rename_artifact_file(
        self,
        *,
        project_id: str,
        artifact_id: str,
        file_name: str,
    ) -> ArtifactMetadata | None:
        artifact = await self.artifact_repository.get_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
        )
        if artifact is None:
            return None

        safe_file_name = self._normalize_generated_file_name(
            file_name,
            artifact=artifact,
        )
        updated_artifact = await self.artifact_repository.update_artifact_name(
            project_id=project_id,
            artifact_id=artifact_id,
            name=safe_file_name,
        )
        if updated_artifact is None:
            return None
        return self._to_metadata(updated_artifact)

    async def delete_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> bool:
        artifact = await self.artifact_repository.get_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
        )
        if artifact is None:
            return False

        if self.storage_service is not None and artifact.storage_path:
            await self.storage_service.delete_by_storage_path(artifact.storage_path)

        return await self.artifact_repository.delete_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
        )

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
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )

    def _file_name_for_artifact(self, artifact: ArtifactModel) -> str | None:
        if artifact.name:
            return artifact.name
        if artifact.storage_path:
            file_name = PurePath(artifact.storage_path).name
            if file_name:
                return file_name
        return None

    def _normalize_generated_file_name(
        self,
        value: str,
        *,
        artifact: ArtifactModel,
    ) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            raise ValueError("파일명을 입력해주세요.")
        if len(candidate) > 255:
            raise ValueError("파일명은 255자 이하로 입력해주세요.")
        if (
            "/" in candidate
            or "\\" in candidate
            or ".." in candidate
            or any(ord(character) < 32 for character in candidate)
        ):
            raise ValueError("파일명에 사용할 수 없는 문자가 포함되어 있습니다.")
        if PurePath(candidate).name != candidate:
            raise ValueError("파일명에 경로를 포함할 수 없습니다.")

        artifact_type = ArtifactType(artifact.artifact_type)
        expected_extension = ARTIFACT_FILE_EXTENSIONS.get(artifact_type)
        existing_file_name = self._file_name_for_artifact(artifact) or artifact.name
        existing_extension = PurePath(existing_file_name).suffix or expected_extension
        candidate_extension = PurePath(candidate).suffix
        if not candidate_extension and existing_extension:
            candidate = f"{candidate}{existing_extension}"
            candidate_extension = existing_extension

        if expected_extension and candidate_extension.lower() != expected_extension:
            raise ValueError(f"{expected_extension} 확장자만 사용할 수 있습니다.")

        return candidate
