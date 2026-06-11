# EN: FastAPI application entry point and router registration.
# KO: FastAPI 앱 진입점이며 주요 라우터를 등록합니다.

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError

from app.api import (
    artifacts,
    chat,
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
from app.db.session import init_db
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


@app.on_event("startup")
async def initialize_database_schema() -> None:
    await init_db()


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


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    detail = exc.detail
    message = detail if isinstance(detail, str) else "request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            message=message,
            error_code=f"HTTP_{exc.status_code}",
            detail=jsonable_encoder(detail),
        ).model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            success=False,
            message="request validation failed",
            error_code="VALIDATION_ERROR",
            detail=jsonable_encoder(exc.errors()),
        ).model_dump(mode="json"),
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception("Database error while handling request")
    error_text = str(exc).lower()
    schema_not_ready_markers = (
        "no such table",
        "undefinedtable",
        "relation",
        "does not exist",
    )
    if (
        isinstance(exc, (OperationalError, ProgrammingError))
        and any(marker in error_text for marker in schema_not_ready_markers)
    ):
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                success=False,
                message="database schema is not initialized",
                error_code="DB_SCHEMA_NOT_READY",
                detail="Run `python -m app.db.init_schema` for the configured DATABASE_URL.",
            ).model_dump(mode="json"),
        )

    if "type \"vector\" does not exist" in error_text or "extension" in error_text and "vector" in error_text:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                success=False,
                message="pgvector extension is not initialized",
                error_code="DB_VECTOR_EXTENSION_NOT_READY",
                detail="Enable pgvector first, for example: CREATE EXTENSION IF NOT EXISTS vector; then run python -m app.db.init_schema.",
            ).model_dump(mode="json"),
        )

    if isinstance(exc, IntegrityError):
        error_code = "DB_INTEGRITY_ERROR"
        message = "database integrity constraint failed"
        if "unique" in error_text or "duplicate" in error_text:
            error_code = "DUPLICATE_RESOURCE"
            message = "resource already exists"
        if "foreign key" in error_text:
            error_code = "RELATED_RESOURCE_NOT_FOUND"
            message = "related resource not found"

        return JSONResponse(
            status_code=409,
            content=ErrorResponse(
                success=False,
                message=message,
                error_code=error_code,
                detail=None,
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
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(documents.router, tags=["documents"])
app.include_router(artifacts.router, tags=["artifacts"])
app.include_router(templates.router, tags=["templates"])
app.include_router(traceability.router, tags=["traceability"])
