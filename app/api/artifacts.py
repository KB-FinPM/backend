# EN: Artifact lookup API routes for generated project artifacts.
# KO: 프로젝트 생성 산출물 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, status

from app.core.exceptions import ApiError
from app.dependencies import get_artifact_service
from app.schemas.artifact import ArtifactMetadata
from app.schemas.response import ErrorResponse
from app.services.artifact_service import ArtifactService

router = APIRouter()

ARTIFACT_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=list[ArtifactMetadata],
    responses=ARTIFACT_ERROR_RESPONSES,
)
async def list_artifacts(
    project_id: str,
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactMetadata]:
    """List generated artifacts that belong to a project."""
    return await artifact_service.list_artifacts(project_id=project_id)


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}",
    response_model=ArtifactMetadata,
    responses=ARTIFACT_ERROR_RESPONSES,
)
async def get_artifact(
    project_id: str,
    artifact_id: str,
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactMetadata:
    """Read one project-scoped artifact metadata record."""
    artifact = await artifact_service.get_artifact(
        project_id=project_id,
        artifact_id=artifact_id,
    )
    if artifact is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ARTIFACT_NOT_FOUND",
            message="artifact not found",
            detail={"project_id": project_id, "artifact_id": artifact_id},
        )

    return artifact
