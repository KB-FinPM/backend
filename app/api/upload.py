# EN: Upload API route for project-scoped source documents.
# KO: 프로젝트 단위 선행 문서 업로드를 처리하는 API 라우터입니다.

from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.config import settings
from app.core.exceptions import ApiError
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
from app.schemas.response import DocumentUploadResponse, ErrorResponse
from app.services.document_service import DocumentService

logger = get_logger(__name__)
router = APIRouter()

UPLOAD_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=DocumentUploadResponse,
    responses=UPLOAD_ERROR_RESPONSES,
)
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

    logger.info(
        "upload | "
        f"project_id={project_id} | "
        f"document_id={document_id} | "
        f"document_type={document_type} | "
        f"file={safe_file_name}"
    )

    file_bytes = await file.read()
    if not file_bytes:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_UPLOAD_FILE",
            message="uploaded file is empty",
            detail={"file_name": safe_file_name},
        )

    storage_path = await document_service.upload_to_storage(
        file_bytes=file_bytes,
        project_id=project_id,
        document_id=document_id,
        file_name=safe_file_name,
        upload_prefix=settings.S3_UPLOAD_PREFIX,
    )
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
    if not input_response.success:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="DOCUMENT_INPUT_NORMALIZATION_FAILED",
            message=input_response.error or "document input normalization failed",
            detail={"errors": input_response.validation_errors},
        )

    document = await document_service.ingest_uploaded_document(
        document_id=document_id,
        project_id=project_id,
        document_type=document_type,
        file_name=safe_file_name,
        storage_path=storage_path,
        file_bytes=file_bytes,
        parsed_context=(
            input_response.structured_context
        ),
    )
    output_response = await output_orchestrator.format(
        OutputAgentRequest(
            project_id=project_id,
            response_type=OutputResponseType.API_RESPONSE,
            result_json={"document": document.model_dump(mode="json")},
            message="document uploaded",
            errors=[],
        )
    )

    return DocumentUploadResponse(
        message="document uploaded",
        document=document,
        display=output_response.display_payload,
    )
