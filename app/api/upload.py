from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

from app.core.logger import get_logger
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.response import DocumentUploadResponse
from app.storage.s3 import s3_service

logger = get_logger(__name__)
router = APIRouter()


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(
    project_id: str = Form(...),
    document_type: DocumentType = Form(DocumentType.UNKNOWN),
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    """Upload a source document and return project-scoped document metadata."""
    safe_file_name = PurePath(file.filename or "uploaded-file").name
    document_id = f"DOC-{uuid4().hex[:12].upper()}"
    storage_key = f"{project_id}/raw/{document_id}/{safe_file_name}"

    logger.info(
        "upload | "
        f"project_id={project_id} | "
        f"document_id={document_id} | "
        f"document_type={document_type} | "
        f"file={safe_file_name}"
    )

    file_bytes = await file.read()
    storage_path = await s3_service.upload(file_bytes=file_bytes, key=storage_key)

    return DocumentUploadResponse(
        message="document uploaded",
        document=DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=safe_file_name,
            storage_path=storage_path,
        ),
    )
