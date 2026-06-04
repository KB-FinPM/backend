# EN: Repository for artifact traceability links.
# KO: 산출물 추적 관계 저장과 조회를 담당하는 Repository입니다.

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_link import ArtifactLinkModel
from app.repositories.project_repository import ensure_project
from app.schemas.traceability import (
    ArtifactLinkCreate,
    ArtifactLinkMetadata,
    ArtifactRelationType,
)


class ArtifactLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_link(
        self,
        *,
        link_id: str,
        project_id: str,
        source_artifact_id: str,
        target_artifact_id: str,
        relation_type: ArtifactRelationType,
        source_item_id: str | None = None,
        target_item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactLinkMetadata:
        await ensure_project(self.session, project_id=project_id)
        link = ArtifactLinkModel(
            link_id=link_id,
            project_id=project_id,
            source_artifact_id=source_artifact_id,
            source_item_id=source_item_id,
            target_artifact_id=target_artifact_id,
            target_item_id=target_item_id,
            relation_type=relation_type.value,
            link_metadata=metadata or {},
        )
        self.session.add(link)
        await self.session.commit()
        await self.session.refresh(link)
        return self._to_metadata(link)

    async def list_links_by_project(
        self,
        *,
        project_id: str,
    ) -> list[ArtifactLinkMetadata]:
        statement = (
            select(ArtifactLinkModel)
            .where(ArtifactLinkModel.project_id == project_id)
            .order_by(ArtifactLinkModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return [self._to_metadata(link) for link in result.scalars().all()]

    async def list_links_for_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> list[ArtifactLinkMetadata]:
        statement = (
            select(ArtifactLinkModel)
            .where(
                ArtifactLinkModel.project_id == project_id,
                or_(
                    ArtifactLinkModel.source_artifact_id == artifact_id,
                    ArtifactLinkModel.target_artifact_id == artifact_id,
                ),
            )
            .order_by(ArtifactLinkModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return [self._to_metadata(link) for link in result.scalars().all()]

    def _to_metadata(self, link: ArtifactLinkModel) -> ArtifactLinkMetadata:
        return ArtifactLinkMetadata(
            link_id=link.link_id,
            project_id=link.project_id,
            source_artifact_id=link.source_artifact_id,
            source_item_id=link.source_item_id,
            target_artifact_id=link.target_artifact_id,
            target_item_id=link.target_item_id,
            relation_type=ArtifactRelationType(link.relation_type),
            metadata=link.link_metadata or {},
        )
