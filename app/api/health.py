from fastapi import APIRouter
from app.schemas.response import BaseResponse

router = APIRouter()


@router.get("/health", response_model=BaseResponse)
async def health_check():
    return BaseResponse(message="FINPM API is running")
