# EN: Artifact lookup API routes for generated project artifacts.
# KO: 프로젝트 생성 산출물 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_artifact_service
from app.schemas.artifact import ArtifactMetadata
from app.services.artifact_service import ArtifactService

router = APIRouter()


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=list[ArtifactMetadata],
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact not found",
        )

    return artifact
