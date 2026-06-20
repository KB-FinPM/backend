"""Upload API route for project-scoped source documents."""

from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.auth import CurrentUser, assert_project_access
from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.logger import get_logger
from app.core.supported_files import (
    GENERIC_MIME_TYPES,
    SUPPORTED_FILE_TYPE_MESSAGE,
    SUPPORTED_MIME_TYPES,
    normalize_content_type,
    resolve_supported_file_type,
    supported_extensions_for_display,
)
from app.dependencies import (
    get_current_user,
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
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse},
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
    current_user: CurrentUser = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
    input_orchestrator: InputOrchestrator = Depends(get_input_orchestrator),
    output_orchestrator: OutputOrchestrator = Depends(get_output_orchestrator),
) -> DocumentUploadResponse:
    """Upload a source document and return project-scoped document metadata."""
    assert_project_access(current_user, project_id, "document:write")
    safe_file_name = PurePath(file.filename or "uploaded-file").name
    document_id = f"DOC-{uuid4().hex[:12].upper()}"

    logger.info(
        "upload | "
        f"project_id={project_id} | "
        f"document_id={document_id} | "
        f"document_type={document_type} | "
        f"file={safe_file_name}"
    )

    resolved_file_type = resolve_supported_file_type(
        file_name=safe_file_name,
        content_type=file.content_type,
    )
    if resolved_file_type is None:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="UNSUPPORTED_UPLOAD_FILE_TYPE",
            message=SUPPORTED_FILE_TYPE_MESSAGE,
            detail={
                "file_name": safe_file_name,
                "content_type": file.content_type,
                "supported_extensions": supported_extensions_for_display(),
            },
        )
    _validate_content_type(
        file_name=safe_file_name,
        content_type=file.content_type,
        extension=resolved_file_type.extension,
    )
    parser_file_name = _normalize_parser_file_name(
        safe_file_name,
        extension=resolved_file_type.extension,
    )

    file_bytes = await _read_upload_file_limited(file, safe_file_name)
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

    try:
        input_response = await input_orchestrator.normalize(
            InputAgentRequest(
                project_id=project_id,
                input_type=InputType.FILE,
                files=[
                    InputFilePayload(
                        file_name=parser_file_name,
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
            await _cleanup_uploaded_object(document_service, storage_path)
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                error_code="DOCUMENT_INPUT_NORMALIZATION_FAILED",
                message=input_response.error or "document input normalization failed",
                detail={
                    "file_name": safe_file_name,
                    "content_type": file.content_type,
                    "errors": input_response.validation_errors,
                },
            )

        document = await document_service.ingest_uploaded_document(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=safe_file_name,
            storage_path=storage_path,
            file_bytes=file_bytes,
            parsed_context=input_response.structured_context,
        )
    except ApiError:
        raise
    except Exception:
        await _cleanup_uploaded_object(document_service, storage_path)
        raise

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


def _normalize_parser_file_name(file_name: str, *, extension: str) -> str:
    path = PurePath(file_name)
    suffix = path.suffix
    if suffix and suffix.lower() == extension:
        return path.with_suffix(suffix.lower()).name
    return path.name


def _validate_content_type(
    *,
    file_name: str,
    content_type: str | None,
    extension: str,
) -> None:
    normalized_content_type = normalize_content_type(content_type)
    if normalized_content_type in GENERIC_MIME_TYPES:
        return

    mime_extension = SUPPORTED_MIME_TYPES.get(normalized_content_type)
    if mime_extension is None:
        return

    compatible_extensions = {mime_extension}
    if mime_extension == ".txt":
        compatible_extensions.update({".md", ".markdown", ".log"})
    if extension in compatible_extensions:
        return

    raise ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="UPLOAD_CONTENT_TYPE_MISMATCH",
        message="uploaded file content type does not match the file extension",
        detail={
            "file_name": file_name,
            "content_type": content_type,
            "extension": extension,
        },
    )


async def _read_upload_file_limited(
    file: UploadFile,
    file_name: str,
) -> bytes:
    max_bytes = max(int(settings.UPLOAD_MAX_BYTES or 0), 1)
    chunk_size = max(int(settings.UPLOAD_READ_CHUNK_BYTES or 0), 1)
    chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise ApiError(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                error_code="UPLOAD_FILE_TOO_LARGE",
                message="uploaded file is too large",
                detail={"file_name": file_name, "max_bytes": max_bytes},
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def _cleanup_uploaded_object(
    document_service: DocumentService,
    storage_path: str,
) -> None:
    storage_service = getattr(document_service, "storage_service", None)
    delete_by_storage_path = getattr(storage_service, "delete_by_storage_path", None)
    if not callable(delete_by_storage_path):
        return
    try:
        await delete_by_storage_path(storage_path)
    except Exception as exc:
        logger.warning(
            "upload cleanup failed | "
            f"storage_path={storage_path} | error={type(exc).__name__}"
        )
