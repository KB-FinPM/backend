# EN: FastAPI application entry point and router registration.
# KO: FastAPI 앱 진입점이며 주요 라우터를 등록합니다.

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api import (
    artifacts,
    documents,
    generation,
    health,
    schedule,
    templates,
    traceability,
    upload,
)
from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.logger import get_logger
from app.schemas.response import ErrorResponse

logger = get_logger(__name__)

app = FastAPI(
    title="FINPM Agent API",
    version="0.1.0",
    description="AI-based project management agent platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            message=exc.message,
            error_code=exc.error_code,
            detail=exc.detail,
        ).model_dump(mode="json"),
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception("Database error while handling request")
    error_text = str(exc).lower()
    if isinstance(exc, OperationalError) and "no such table" in error_text:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                success=False,
                message="database schema is not initialized",
                error_code="DB_SCHEMA_NOT_READY",
                detail="Run `python -m app.db.init_schema` for the configured DATABASE_URL.",
            ).model_dump(mode="json"),
        )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            success=False,
            message="database error",
            error_code="DATABASE_ERROR",
            detail=None,
        ).model_dump(mode="json"),
    )

app.include_router(health.router, tags=["health"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(generation.router, prefix="/generate", tags=["generation"])
app.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
app.include_router(documents.router, tags=["documents"])
app.include_router(artifacts.router, tags=["artifacts"])
app.include_router(templates.router, tags=["templates"])
app.include_router(traceability.router, tags=["traceability"])
