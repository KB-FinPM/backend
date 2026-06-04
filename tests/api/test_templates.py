# EN: Tests for template lookup APIs.
# KO: 템플릿 조회 API 테스트입니다.

from fastapi.testclient import TestClient

from app.dependencies import get_template_service
from app.schemas.artifact import ArtifactType
from app.schemas.template import TemplateMetadata


class StubTemplateService:
    async def list_templates(
        self,
        *,
        artifact_type: ArtifactType | None = None,
    ) -> list[TemplateMetadata]:
        return [
            TemplateMetadata(
                template_id="TPL-REQ-SPEC-DEFAULT",
                template_version="v1",
                artifact_type=ArtifactType.REQUIREMENT_SPEC,
                name="Default Requirement Specification",
                content="Generate requirements.",
                is_builtin=True,
            )
        ]

    async def get_template(
        self,
        *,
        template_id: str,
        template_version: str | None = None,
    ) -> TemplateMetadata | None:
        if template_id == "missing":
            return None

        return TemplateMetadata(
            template_id=template_id,
            template_version=template_version or "v1",
            artifact_type=ArtifactType.REQUIREMENT_SPEC,
            name="Default Requirement Specification",
            content="Generate requirements.",
            is_builtin=True,
        )


def test_list_templates_returns_available_templates(client: TestClient) -> None:
    client.app.dependency_overrides[get_template_service] = StubTemplateService

    try:
        response = client.get("/templates?artifact_type=REQUIREMENT_SPEC")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["template_id"] == "TPL-REQ-SPEC-DEFAULT"


def test_get_template_returns_404_when_missing(client: TestClient) -> None:
    client.app.dependency_overrides[get_template_service] = StubTemplateService

    try:
        response = client.get("/templates/missing")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "TEMPLATE_NOT_FOUND"
    assert body["detail"] == {
        "template_id": "missing",
        "template_version": None,
    }
