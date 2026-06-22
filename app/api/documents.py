# EN: Document lookup API routes for project-scoped source documents.
# KO: 프로젝트 범위 원천 문서 조회 API 라우트입니다.

from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from app.core.auth import CurrentUser, assert_project_access
from app.core.config import settings
from app.core.exceptions import ApiError
from app.dependencies import get_artifact_service, get_current_user, get_document_service
from app.schemas.artifact import DocumentMetadata
from app.schemas.response import BaseResponse, ErrorResponse, ProjectFilesResponse
from app.services.artifact_service import ArtifactService
from app.services.document_service import DocumentService
from app.storage.s3 import s3_service

router = APIRouter()

DOCUMENT_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.get(
    "/projects/{project_id}/documents",
    response_model=list[DocumentMetadata],
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def list_documents(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentMetadata]:
    """List documents that belong to a project."""
    assert_project_access(current_user, project_id, "document:read")
    return await document_service.list_documents(project_id=project_id)


@router.get(
    "/projects/{project_id}/files",
    response_model=ProjectFilesResponse,
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def list_project_files(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ProjectFilesResponse:
    """List uploaded source files separately from generated artifact files."""
    assert_project_access(current_user, project_id, "document:read")
    documents = await document_service.list_documents(project_id=project_id)
    generated_prefix = f"{settings.S3_GENERATED_PREFIX}/"
    uploaded_files = [
        document
        for document in documents
        if not str(document.storage_path or "").startswith(generated_prefix)
    ]
    return ProjectFilesResponse(
        uploaded_files=uploaded_files,
        generated_files=await artifact_service.list_artifacts(project_id=project_id),
    )


@router.get(
    "/projects/{project_id}/documents/{document_id}",
    response_model=DocumentMetadata,
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def get_document(
    project_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentMetadata:
    """Read one project-scoped document metadata record."""
    assert_project_access(current_user, project_id, "document:read")
    document = await document_service.get_document(
        project_id=project_id,
        document_id=document_id,
    )
    if document is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_NOT_FOUND",
            message="document not found",
            detail={"project_id": project_id, "document_id": document_id},
        )

    return document


@router.get(
    "/projects/{project_id}/files/{file_id}/download",
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def download_project_file(
    project_id: str,
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    assert_project_access(current_user, project_id, "document:read")
    document = await document_service.get_document(
        project_id=project_id,
        document_id=file_id,
    )
    if document is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_NOT_FOUND",
            message="document not found",
            detail={"project_id": project_id, "document_id": file_id},
        )

    try:
        file_bytes, stored_content_type = await s3_service.download_by_storage_path(
            document.storage_path,
        )
    except FileNotFoundError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_FILE_NOT_FOUND",
            message="document file not found",
            detail={"project_id": project_id, "document_id": file_id},
        ) from exc

    file_name = PurePath(document.file_name).name or "project-file"
    encoded_file_name = quote(file_name)
    return Response(
        content=file_bytes,
        media_type=stored_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_file_name}"
        },
    )


@router.delete(
    "/projects/{project_id}/files/{file_id}",
    response_model=BaseResponse,
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def delete_project_file(
    project_id: str,
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> BaseResponse:
    assert_project_access(current_user, project_id, "document:write")
    deleted = await document_service.delete_document(
        project_id=project_id,
        document_id=file_id,
    )
    if not deleted:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_NOT_FOUND",
            message="document not found",
            detail={"project_id": project_id, "document_id": file_id},
        )
    return BaseResponse(message="document deleted")
