# EN: Business service for artifact relationship traceability.
# KO: 산출물 관계 추적 유스케이스를 담당하는 비즈니스 서비스입니다.

from uuid import uuid4

from app.repositories.artifact_link_repository import ArtifactLinkRepository
from app.schemas.traceability import ArtifactLinkCreate, ArtifactLinkMetadata


class TraceabilityService:
    """Coordinates artifact link creation and lookup."""

    def __init__(self, artifact_link_repository: ArtifactLinkRepository) -> None:
        self.artifact_link_repository = artifact_link_repository

    async def create_link(
        self,
        request: ArtifactLinkCreate,
    ) -> ArtifactLinkMetadata:
        return await self.artifact_link_repository.create_link(
            link_id=f"LINK-{uuid4().hex[:12].upper()}",
            project_id=request.project_id,
            source_artifact_id=request.source_artifact_id,
            source_item_id=request.source_item_id,
            target_artifact_id=request.target_artifact_id,
            target_item_id=request.target_item_id,
            relation_type=request.relation_type,
            metadata=request.metadata,
        )

    async def list_project_links(
        self,
        *,
        project_id: str,
    ) -> list[ArtifactLinkMetadata]:
        return await self.artifact_link_repository.list_links_by_project(
            project_id=project_id,
        )

    async def list_artifact_links(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> list[ArtifactLinkMetadata]:
        return await self.artifact_link_repository.list_links_for_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
        )
