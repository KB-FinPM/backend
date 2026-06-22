# EN: Artifact lookup API routes for generated project artifacts.
# KO: 프로젝트 생성 산출물 조회 API 라우트입니다.

from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import Response

from app.core.auth import CurrentUser, assert_project_access
from app.core.exceptions import ApiError
from app.dependencies import get_artifact_service, get_current_user
from app.schemas.artifact import ArtifactMetadata, ArtifactType
from app.schemas.request import ArtifactRenameRequest
from app.schemas.response import ErrorResponse
from app.services.artifact_service import ArtifactService
from app.storage.s3 import s3_service

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
    current_user: CurrentUser = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactMetadata]:
    """List generated artifacts that belong to a project."""
    assert_project_access(current_user, project_id, "artifact:read")
    return await artifact_service.list_artifacts(project_id=project_id)


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}",
    response_model=ArtifactMetadata,
    responses=ARTIFACT_ERROR_RESPONSES,
)
async def get_artifact(
    project_id: str,
    artifact_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactMetadata:
    """Read one project-scoped artifact metadata record."""
    assert_project_access(current_user, project_id, "artifact:read")
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


@router.patch(
    "/projects/{project_id}/artifacts/{artifact_id}",
    response_model=ArtifactMetadata,
    responses=ARTIFACT_ERROR_RESPONSES,
)
async def update_artifact(
    project_id: str,
    artifact_id: str,
    request: ArtifactRenameRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactMetadata:
    """Update generated artifact display/download file metadata."""
    assert_project_access(current_user, project_id, "artifact:write")
    try:
        artifact = await artifact_service.rename_artifact_file(
            project_id=project_id,
            artifact_id=artifact_id,
            file_name=request.file_name,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="INVALID_ARTIFACT_FILE_NAME",
            message=str(exc),
            detail={"project_id": project_id, "artifact_id": artifact_id},
        ) from exc
    if artifact is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ARTIFACT_NOT_FOUND",
            message="artifact not found",
            detail={"project_id": project_id, "artifact_id": artifact_id},
        )
    return artifact


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}/download",
    responses=ARTIFACT_ERROR_RESPONSES,
)
async def download_artifact(
    project_id: str,
    artifact_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> Response:
    """Download one generated artifact as a browser attachment."""
    assert_project_access(current_user, project_id, "artifact:read")
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
    if not artifact.storage_path:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ARTIFACT_FILE_NOT_FOUND",
            message="artifact file not found",
            detail={"project_id": project_id, "artifact_id": artifact_id},
        )

    try:
        file_bytes, stored_content_type = await s3_service.download_by_storage_path(
            artifact.storage_path,
        )
    except FileNotFoundError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ARTIFACT_FILE_NOT_FOUND",
            message="artifact file not found",
            detail={"project_id": project_id, "artifact_id": artifact_id},
        ) from exc

    file_name = _download_file_name(artifact)
    content_type = stored_content_type or _content_type_for_artifact(
        artifact.artifact_type,
    )
    encoded_file_name = quote(file_name)
    headers = {
        "Content-Disposition": (
            f"attachment; filename*=UTF-8''{encoded_file_name}"
        )
    }

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers=headers,
    )


def _download_file_name(artifact: ArtifactMetadata) -> str:
    if artifact.file_name:
        return PurePath(artifact.file_name).name or artifact.file_name
    if artifact.name:
        return PurePath(artifact.name).name or artifact.name
    if artifact.storage_path:
        file_name = PurePath(artifact.storage_path).name
        if file_name:
            return file_name
    if artifact.artifact_type == ArtifactType.REQUIREMENT_SPEC:
        return "요구사항명세서.xlsx"
    return f"{artifact.name or artifact.artifact_type.value}.bin"


def _content_type_for_artifact(artifact_type: ArtifactType) -> str:
    if artifact_type == ArtifactType.REQUIREMENT_SPEC:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if artifact_type in {ArtifactType.WBS, ArtifactType.UNITTEST_SPEC}:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if artifact_type == ArtifactType.SCREEN_DESIGN:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return "application/octet-stream"
