# EN: Document lookup API routes for project-scoped source documents.
# KO: 프로젝트 범위 원천 문서 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, status

from app.core.exceptions import ApiError
from app.dependencies import get_document_service
from app.schemas.artifact import DocumentMetadata
from app.schemas.response import ErrorResponse
from app.services.document_service import DocumentService

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
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentMetadata]:
    """List documents that belong to a project."""
    return await document_service.list_documents(project_id=project_id)


@router.get(
    "/projects/{project_id}/documents/{document_id}",
    response_model=DocumentMetadata,
    responses=DOCUMENT_ERROR_RESPONSES,
)
async def get_document(
    project_id: str,
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentMetadata:
    """Read one project-scoped document metadata record."""
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
