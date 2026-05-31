# EN: Document lookup API routes for project-scoped source documents.
# KO: 프로젝트 범위 원천 문서 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_document_service
from app.schemas.artifact import DocumentMetadata
from app.services.document_service import DocumentService

router = APIRouter()


@router.get(
    "/projects/{project_id}/documents",
    response_model=list[DocumentMetadata],
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    return document
