# EN: Template lookup API routes for artifact generation.
# KO: 산출물 생성을 위한 템플릿 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, Query, status

from app.core.exceptions import ApiError
from app.dependencies import get_template_service
from app.schemas.artifact import ArtifactType
from app.schemas.response import ErrorResponse
from app.schemas.template import TemplateMetadata
from app.services.template_service import TemplateService

router = APIRouter()

TEMPLATE_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.get(
    "/templates",
    response_model=list[TemplateMetadata],
    responses=TEMPLATE_ERROR_RESPONSES,
)
async def list_templates(
    artifact_type: ArtifactType | None = Query(None),
    template_service: TemplateService = Depends(get_template_service),
) -> list[TemplateMetadata]:
    """List available built-in and stored artifact templates."""
    return await template_service.list_templates(artifact_type=artifact_type)


@router.get(
    "/templates/{template_id}",
    response_model=TemplateMetadata,
    responses=TEMPLATE_ERROR_RESPONSES,
)
async def get_template(
    template_id: str,
    template_version: str | None = Query(None),
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateMetadata:
    """Read one template by ID and optional version."""
    template = await template_service.get_template(
        template_id=template_id,
        template_version=template_version,
    )
    if template is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TEMPLATE_NOT_FOUND",
            message="template not found",
            detail={
                "template_id": template_id,
                "template_version": template_version,
            },
        )

    return template
