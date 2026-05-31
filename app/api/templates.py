# EN: Template lookup API routes for artifact generation.
# KO: 산출물 생성을 위한 템플릿 조회 API 라우트입니다.

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_template_service
from app.schemas.artifact import ArtifactType
from app.schemas.template import TemplateMetadata
from app.services.template_service import TemplateService

router = APIRouter()


@router.get("/templates", response_model=list[TemplateMetadata])
async def list_templates(
    artifact_type: ArtifactType | None = Query(None),
    template_service: TemplateService = Depends(get_template_service),
) -> list[TemplateMetadata]:
    """List available built-in and stored artifact templates."""
    return await template_service.list_templates(artifact_type=artifact_type)


@router.get("/templates/{template_id}", response_model=TemplateMetadata)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="template not found",
        )

    return template
