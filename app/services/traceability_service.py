# EN: Business service for artifact relationship traceability.
# KO: 산출물 관계 추적 유스케이스를 담당하는 비즈니스 서비스입니다.

from typing import Any
from uuid import uuid4

from app.repositories.artifact_link_repository import ArtifactLinkRepository
from app.schemas.traceability import (
    ArtifactLinkCreate,
    ArtifactLinkMetadata,
    ArtifactRelationType,
)


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

    async def create_links_from_generated_artifact(
        self,
        *,
        project_id: str,
        source_artifact_id: str,
        target_artifact_id: str,
        generated_result: dict[str, Any],
    ) -> list[ArtifactLinkMetadata]:
        # TODO: Call this from GenerationOrchestrator once GenerationRequest or
        # agent metadata carries the source requirement artifact ID explicitly.
        links = self.build_links_from_generated_artifact(
            project_id=project_id,
            source_artifact_id=source_artifact_id,
            target_artifact_id=target_artifact_id,
            generated_result=generated_result,
        )
        return [await self.create_link(link) for link in links]

    def build_links_from_generated_artifact(
        self,
        *,
        project_id: str,
        source_artifact_id: str,
        target_artifact_id: str,
        generated_result: dict[str, Any],
    ) -> list[ArtifactLinkCreate]:
        artifact_type = generated_result.get("artifact_type")
        if artifact_type == "WBS":
            return self._build_item_links(
                project_id=project_id,
                source_artifact_id=source_artifact_id,
                target_artifact_id=target_artifact_id,
                items=generated_result.get("tasks", []),
                target_id_field="task_id",
                relation_type=ArtifactRelationType.DECOMPOSED_TO,
            )

        if artifact_type == "SCREEN_DESIGN":
            return self._build_item_links(
                project_id=project_id,
                source_artifact_id=source_artifact_id,
                target_artifact_id=target_artifact_id,
                items=generated_result.get("screens", []),
                target_id_field="screen_id",
                relation_type=ArtifactRelationType.DESIGNED_BY,
            )

        return []

    def _build_item_links(
        self,
        *,
        project_id: str,
        source_artifact_id: str,
        target_artifact_id: str,
        items: list[dict[str, Any]],
        target_id_field: str,
        relation_type: ArtifactRelationType,
    ) -> list[ArtifactLinkCreate]:
        links: list[ArtifactLinkCreate] = []
        for item in items:
            target_item_id = item.get(target_id_field)
            if not target_item_id:
                continue

            for source_requirement_id in item.get("source_requirement_ids", []):
                links.append(
                    ArtifactLinkCreate(
                        project_id=project_id,
                        source_artifact_id=source_artifact_id,
                        source_item_id=source_requirement_id,
                        target_artifact_id=target_artifact_id,
                        target_item_id=target_item_id,
                        relation_type=relation_type,
                        metadata={
                            "auto_generated": True,
                            "source_field": "source_requirement_ids",
                        },
                    )
                )

        return links

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
