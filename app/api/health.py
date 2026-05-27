# EN: Health check API route for service availability checks.
# KO: 서비스 상태 확인을 위한 Health Check API 라우터입니다.

from fastapi import APIRouter
from app.schemas.response import BaseResponse

router = APIRouter()


@router.get("/health", response_model=BaseResponse)
async def health_check():
    return BaseResponse(message="FINPM API is running")
