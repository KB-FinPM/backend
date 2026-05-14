from fastapi import APIRouter, UploadFile, File, Form
from app.schemas.response import BaseResponse
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("", response_model=BaseResponse)
async def upload_document(
    project_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    PDF 또는 회의록 파일 업로드.
    TODO: S3 업로드 + RAG 파이프라인 연동
    """
    logger.info(f"upload | project_id={project_id} | file={file.filename}")

    # TODO: storage_service.upload(file) 호출
    # TODO: rag_service.ingest(document_id) 호출

    return BaseResponse(message=f"{file.filename} 업로드 완료 (Mock)")
