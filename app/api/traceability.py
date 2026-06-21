# EN: Traceability API routes for artifact relationships.
# KO: 산출물 관계 추적 API 라우트입니다.

from fastapi import APIRouter, Depends, status

from app.core.auth import CurrentUser, assert_project_access
from app.dependencies import get_current_user, get_traceability_service
from app.schemas.response import ErrorResponse
from app.schemas.traceability import ArtifactLinkCreate, ArtifactLinkMetadata
from app.services.traceability_service import TraceabilityService

router = APIRouter()

TRACEABILITY_ERROR_RESPONSES = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.post(
    "/projects/{project_id}/artifact-links",
    response_model=ArtifactLinkMetadata,
    status_code=status.HTTP_201_CREATED,
    responses=TRACEABILITY_ERROR_RESPONSES,
)
async def create_artifact_link(
    project_id: str,
    request: ArtifactLinkCreate,
    current_user: CurrentUser = Depends(get_current_user),
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> ArtifactLinkMetadata:
    """Create a traceability link between artifact items."""
    assert_project_access(current_user, project_id, "artifact:generate")
    request.project_id = project_id
    return await traceability_service.create_link(request)


@router.get(
    "/projects/{project_id}/artifact-links",
    response_model=list[ArtifactLinkMetadata],
    responses=TRACEABILITY_ERROR_RESPONSES,
)
async def list_project_artifact_links(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> list[ArtifactLinkMetadata]:
    """List all artifact links in a project."""
    assert_project_access(current_user, project_id, "artifact:read")
    return await traceability_service.list_project_links(project_id=project_id)


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}/links",
    response_model=list[ArtifactLinkMetadata],
    responses=TRACEABILITY_ERROR_RESPONSES,
)
async def list_artifact_links(
    project_id: str,
    artifact_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    traceability_service: TraceabilityService = Depends(get_traceability_service),
) -> list[ArtifactLinkMetadata]:
    """List links where the artifact is either the source or the target."""
    assert_project_access(current_user, project_id, "artifact:read")
    return await traceability_service.list_artifact_links(
        project_id=project_id,
        artifact_id=artifact_id,
    )
