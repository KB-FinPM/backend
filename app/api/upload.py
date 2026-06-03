# EN: Upload API route for project-scoped source documents.
# KO: 프로젝트 단위 선행 문서 업로드를 처리하는 API 라우터입니다.

from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.config import settings
from app.core.logger import get_logger
from app.dependencies import (
    get_document_service,
    get_input_orchestrator,
    get_output_orchestrator,
)
from app.orchestrator.input_orchestrator import InputOrchestrator
from app.orchestrator.output_orchestrator import OutputOrchestrator
from app.schemas.artifact import DocumentType
from app.schemas.io_agent import (
    InputAgentRequest,
    InputFilePayload,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)
from app.schemas.response import DocumentUploadResponse
from app.services.document_service import DocumentService
from app.storage.s3 import s3_service

logger = get_logger(__name__)
router = APIRouter()


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(
    project_id: str = Form(...),
    document_type: DocumentType = Form(DocumentType.UNKNOWN),
    file: UploadFile = File(...),
    document_service: DocumentService = Depends(get_document_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> DocumentUploadResponse:
    """Upload a source document and return project-scoped document metadata."""
    safe_file_name = PurePath(file.filename or "uploaded-file").name
    document_id = f"DOC-{uuid4().hex[:12].upper()}"
    storage_key = (
        f"{settings.S3_UPLOAD_PREFIX}/{project_id}/raw/{document_id}/{safe_file_name}"
    )

    logger.info(
        "upload | "
        f"project_id={project_id} | "
        f"document_id={document_id} | "
        f"document_type={document_type} | "
        f"file={safe_file_name}"
    )

    file_bytes = await file.read()
    storage_path = await s3_service.upload(file_bytes=file_bytes, key=storage_key)
    input_response = await input_orchestrator.normalize(
        InputAgentRequest(
            project_id=project_id,
            input_type=InputType.FILE,
            files=[
                InputFilePayload(
                    file_name=safe_file_name,
                    file_bytes=file_bytes,
                    content_type=file.content_type,
                )
            ],
            context={
                "document_id": document_id,
                "document_type": document_type.value,
                "storage_path": storage_path,
            },
        )
    )
    document = await document_service.ingest_uploaded_document(
        document_id=document_id,
        project_id=project_id,
        document_type=document_type,
        file_name=safe_file_name,
        storage_path=storage_path,
        file_bytes=file_bytes,
        parsed_context=(
            input_response.structured_context if input_response.success else None
        ),
    )
    output_response = await output_orchestrator.format(
        OutputAgentRequest(
            project_id=project_id,
            response_type=OutputResponseType.API_RESPONSE,
            result_json={"document": document.model_dump(mode="json")},
            message="document uploaded",
            errors=[] if input_response.success else input_response.validation_errors,
        )
    )

    return DocumentUploadResponse(
        message="document uploaded",
        document=document,
        display=output_response.display_payload,
    )
