from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, upload, generation
from app.core.config import settings

app = FastAPI(
    title="FINPM Agent API",
    version="0.1.0",
    description="AI 기반 프로젝트 관리 지원 플랫폼",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health.router, tags=["health"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(generation.router, prefix="/generate", tags=["generation"])
