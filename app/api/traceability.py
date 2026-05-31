# EN: Traceability API routes for artifact relationships.
# KO: 산출물 관계 추적 API 라우트입니다.

from fastapi import APIRouter, Depends

from app.dependencies import get_traceability_service
from app.schemas.traceability import ArtifactLinkCreate, ArtifactLinkMetadata
from app.services.traceability_service import TraceabilityService

router = APIRouter()


@router.post(
    "/projects/{project_id}/artifact-links",
    response_model=ArtifactLinkMetadata,
)
async def create_artifact_link(
    project_id: str,
    request: ArtifactLinkCreate,
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> ArtifactLinkMetadata:
    """Create a traceability link between artifact items."""
    request.project_id = project_id
    return await traceability_service.create_link(request)


@router.get(
    "/projects/{project_id}/artifact-links",
    response_model=list[ArtifactLinkMetadata],
)
async def list_project_artifact_links(
    project_id: str,
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> list[ArtifactLinkMetadata]:
    """List all artifact links in a project."""
    return await traceability_service.list_project_links(project_id=project_id)


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}/links",
    response_model=list[ArtifactLinkMetadata],
)
async def list_artifact_links(
    project_id: str,
    artifact_id: str,
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> list[ArtifactLinkMetadata]:
    """List links where the artifact is either the source or the target."""
    return await traceability_service.list_artifact_links(
        project_id=project_id,
        artifact_id=artifact_id,
    )
