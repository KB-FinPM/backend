# EN: Tests for project-scoped document lookup APIs.
# KO: 프로젝트 범위 문서 조회 API 테스트입니다.

from fastapi.testclient import TestClient

from app.dependencies import get_document_service
from app.schemas.artifact import DocumentMetadata, DocumentType


class StubDocumentService:
    async def list_documents(self, *, project_id: str) -> list[DocumentMetadata]:
        return [
            DocumentMetadata(
                document_id="DOC-001",
                project_id=project_id,
                document_type=DocumentType.REQUIREMENT_SPEC,
                file_name="requirements.pdf",
                storage_path="s3://bucket/requirements.pdf",
            )
        ]

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> DocumentMetadata | None:
        if document_id == "DOC-404":
            return None

        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirements.pdf",
            storage_path="s3://bucket/requirements.pdf",
        )


def test_list_documents_returns_project_documents(client: TestClient) -> None:
    client.app.dependency_overrides[get_document_service] = StubDocumentService

    try:
        response = client.get("/projects/PRJ-001/documents")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["project_id"] == "PRJ-001"
    assert response.json()[0]["document_id"] == "DOC-001"


def test_get_document_returns_404_when_missing(client: TestClient) -> None:
    client.app.dependency_overrides[get_document_service] = StubDocumentService

    try:
        response = client.get("/projects/PRJ-001/documents/DOC-404")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "document not found"
