# EN: Business service for artifact template lookup and default resolution.
# KO: 산출물 템플릿 조회와 기본 템플릿 결정을 담당하는 비즈니스 서비스입니다.

from app.models.template import TemplateModel
from app.repositories.template_repository import TemplateRepository
from app.schemas.artifact import ArtifactType, TemplateReference
from app.schemas.template import TemplateMetadata


BUILTIN_TEMPLATES: tuple[TemplateMetadata, ...] = (
    TemplateMetadata(
        template_id="TPL-REQ-SPEC-DEFAULT",
        template_version="v1",
        artifact_type=ArtifactType.REQUIREMENT_SPEC,
        name="Default Requirement Specification",
        content=(
            "Generate a REQUIREMENT_SPEC JSON artifact. Include requirement_id, "
            "title, description, priority, source_document_id, source_chunk_ids, "
            "acceptance_criteria, and rationale for every requirement."
        ),
        placeholders={
            "artifact_type": "REQUIREMENT_SPEC",
            "priority_default": "SHOULD",
        },
        is_builtin=True,
    ),
)


class TemplateService:
    """Provides template lookup while hiding storage details from routers/agents."""

    def __init__(self, template_repository: TemplateRepository) -> None:
        self.template_repository = template_repository

    async def list_templates(
        self,
        *,
        artifact_type: ArtifactType | None = None,
    ) -> list[TemplateMetadata]:
        db_templates = await self.template_repository.list_templates(
            artifact_type=artifact_type,
        )
        templates = [self._to_metadata(template) for template in db_templates]
        templates.extend(
            template
            for template in BUILTIN_TEMPLATES
            if artifact_type is None or template.artifact_type == artifact_type
        )
        return templates

    async def get_template(
        self,
        *,
        template_id: str,
        template_version: str | None = None,
    ) -> TemplateMetadata | None:
        db_template = await self.template_repository.get_template(
            template_id=template_id,
            template_version=template_version,
        )
        if db_template is not None:
            return self._to_metadata(db_template)

        return self._get_builtin_template(
            template_id=template_id,
            template_version=template_version,
        )

    async def resolve_template(
        self,
        *,
        reference: TemplateReference,
        artifact_type: ArtifactType,
    ) -> TemplateMetadata | None:
        if reference.template_id:
            template = await self.get_template(
                template_id=reference.template_id,
                template_version=reference.template_version,
            )
            if template is None or template.artifact_type != artifact_type:
                return None

            return template

        return self._get_default_builtin_template(artifact_type)

    def _get_builtin_template(
        self,
        *,
        template_id: str,
        template_version: str | None = None,
    ) -> TemplateMetadata | None:
        for template in BUILTIN_TEMPLATES:
            if template.template_id != template_id:
                continue
            if template_version is not None and (
                template.template_version != template_version
            ):
                continue

            return template

        return None

    def _get_default_builtin_template(
        self,
        artifact_type: ArtifactType,
    ) -> TemplateMetadata | None:
        for template in BUILTIN_TEMPLATES:
            if template.artifact_type == artifact_type:
                return template

        return None

    def _to_metadata(self, template: TemplateModel) -> TemplateMetadata:
        content = template.content or {}
        return TemplateMetadata(
            template_id=template.template_id,
            template_version=template.template_version,
            artifact_type=ArtifactType(template.artifact_type),
            name=template.name,
            content=content,
            placeholders=template.placeholders or {},
            is_builtin=template.is_builtin,
        )
