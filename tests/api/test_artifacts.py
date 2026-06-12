# EN: Tests for project-scoped artifact lookup APIs.
# KO: 프로젝트 범위 산출물 조회 API 테스트입니다.

from fastapi.testclient import TestClient

from app.dependencies import get_artifact_service
from app.schemas.artifact import ArtifactMetadata, ArtifactType


class StubArtifactService:
    async def list_artifacts(self, *, project_id: str) -> list[ArtifactMetadata]:
        return [
            ArtifactMetadata(
                artifact_id="ART-001",
                project_id=project_id,
                artifact_type=ArtifactType.REQUIREMENT_SPEC,
                name="Requirement Spec",
                source_document_ids=["DOC-001"],
                result_json={"requirements": [{"id": "RQ-001"}]},
            )
        ]

    async def get_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactMetadata | None:
        if artifact_id == "ART-404":
            return None

        return ArtifactMetadata(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=ArtifactType.REQUIREMENT_SPEC,
            name="Requirement Spec",
            source_document_ids=["DOC-001"],
            result_json={"requirements": [{"id": "RQ-001"}]},
        )


def test_list_artifacts_returns_project_artifacts(client: TestClient) -> None:
    client.app.dependency_overrides[get_artifact_service] = StubArtifactService

    try:
        response = client.get("/api/projects/PRJ-001/artifacts")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["project_id"] == "PRJ-001"
    assert response.json()[0]["artifact_id"] == "ART-001"


def test_get_artifact_returns_404_when_missing(client: TestClient) -> None:
    client.app.dependency_overrides[get_artifact_service] = StubArtifactService

    try:
        response = client.get("/api/projects/PRJ-001/artifacts/ART-404")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "ARTIFACT_NOT_FOUND"
    assert body["detail"] == {
        "project_id": "PRJ-001",
        "artifact_id": "ART-404",
    }
