# EN: Tests for source document upload API behavior.
# KO: 선행 문서 업로드 API 동작을 검증하는 테스트입니다.

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.dependencies import get_document_service
from app.schemas.artifact import DocumentMetadata, DocumentType


class StubS3Service:
    def __init__(self) -> None:
        self.received_file_bytes: bytes | None = None
        self.received_key: str | None = None

    async def upload(self, file_bytes: bytes, key: str) -> str:
        self.received_file_bytes = file_bytes
        self.received_key = key
        return f"s3://test-bucket/{key}"


class StubDocumentRepository:
    def __init__(self) -> None:
        self.received_document_id: str | None = None
        self.received_project_id: str | None = None
        self.received_document_type: DocumentType | None = None
        self.received_file_name: str | None = None
        self.received_storage_path: str | None = None

    async def create_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
    ) -> DocumentMetadata:
        self.received_document_id = document_id
        self.received_project_id = project_id
        self.received_document_type = document_type
        self.received_file_name = file_name
        self.received_storage_path = storage_path
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )


def test_upload_document_returns_document_metadata(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    stub_s3 = StubS3Service()
    stub_repository = StubDocumentRepository()
    monkeypatch.setattr("app.api.upload.s3_service", stub_s3)
    client.app.dependency_overrides[get_document_service] = lambda: stub_repository

    try:
        response = client.post(
            "/upload",
            data={
                "project_id": "PRJ-001",
                "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
            files={
                "file": (
                    "construction-requirements.pdf",
                    b"source document bytes",
                    "application/pdf",
                )
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "document uploaded"
    assert body["document"]["project_id"] == "PRJ-001"
    assert body["document"]["document_type"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert body["document"]["file_name"] == "construction-requirements.pdf"
    assert body["document"]["status"] == "UPLOADED"
    assert body["document"]["document_id"].startswith("DOC-")
    assert body["document"]["storage_path"].startswith(
        "s3://test-bucket/storage/upload_files/PRJ-001/raw/"
    )
    assert stub_s3.received_file_bytes == b"source document bytes"
    assert stub_s3.received_key is not None
    assert stub_s3.received_key.endswith("/construction-requirements.pdf")
    assert stub_repository.received_project_id == "PRJ-001"
    assert stub_repository.received_document_type == (
        DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION
    )
    assert stub_repository.received_storage_path == body["document"]["storage_path"]
