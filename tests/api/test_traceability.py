# EN: Tests for traceability API routes.
# KO: 산출물 관계 추적 API 테스트입니다.

from fastapi.testclient import TestClient

from app.dependencies import get_traceability_service
from app.schemas.traceability import ArtifactLinkCreate, ArtifactLinkMetadata


class StubTraceabilityService:
    async def create_link(
        self,
        request: ArtifactLinkCreate,
    ) -> ArtifactLinkMetadata:
        return ArtifactLinkMetadata(
            link_id="LINK-001",
            project_id=request.project_id,
            source_artifact_id=request.source_artifact_id,
            source_item_id=request.source_item_id,
            target_artifact_id=request.target_artifact_id,
            target_item_id=request.target_item_id,
            relation_type=request.relation_type,
            metadata=request.metadata,
        )

    async def list_project_links(
        self,
        *,
        project_id: str,
    ) -> list[ArtifactLinkMetadata]:
        return [
            ArtifactLinkMetadata(
                link_id="LINK-001",
                project_id=project_id,
                source_artifact_id="ART-REQ-001",
                target_artifact_id="ART-WBS-001",
                relation_type="DECOMPOSED_TO",
            )
        ]

    async def list_artifact_links(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> list[ArtifactLinkMetadata]:
        return [
            ArtifactLinkMetadata(
                link_id="LINK-001",
                project_id=project_id,
                source_artifact_id=artifact_id,
                target_artifact_id="ART-WBS-001",
                relation_type="DECOMPOSED_TO",
            )
        ]


def test_create_artifact_link_uses_path_project_id(client: TestClient) -> None:
    client.app.dependency_overrides[get_traceability_service] = StubTraceabilityService

    try:
        response = client.post(
            "/projects/PRJ-001/artifact-links",
            json={
                "project_id": "WRONG",
                "source_artifact_id": "ART-REQ-001",
                "source_item_id": "RQ-001",
                "target_artifact_id": "ART-WBS-001",
                "target_item_id": "WBS-001",
                "relation_type": "DECOMPOSED_TO",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["project_id"] == "PRJ-001"
    assert response.json()["relation_type"] == "DECOMPOSED_TO"


def test_list_project_artifact_links(client: TestClient) -> None:
    client.app.dependency_overrides[get_traceability_service] = StubTraceabilityService

    try:
        response = client.get("/projects/PRJ-001/artifact-links")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["link_id"] == "LINK-001"


def test_list_artifact_links(client: TestClient) -> None:
    client.app.dependency_overrides[get_traceability_service] = StubTraceabilityService

    try:
        response = client.get("/projects/PRJ-001/artifacts/ART-REQ-001/links")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["source_artifact_id"] == "ART-REQ-001"
