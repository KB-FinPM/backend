# EN: Tests for source document upload API behavior.
# KO: 선행 문서 업로드 API 동작을 검증하는 테스트입니다.

from fastapi.testclient import TestClient
from pytest import MonkeyPatch


class StubS3Service:
    def __init__(self) -> None:
        self.received_file_bytes: bytes | None = None
        self.received_key: str | None = None

    async def upload(self, file_bytes: bytes, key: str) -> str:
        self.received_file_bytes = file_bytes
        self.received_key = key
        return f"s3://test-bucket/{key}"


def test_upload_document_returns_document_metadata(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    stub_s3 = StubS3Service()
    monkeypatch.setattr("app.api.upload.s3_service", stub_s3)

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

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "document uploaded"
    assert body["document"]["project_id"] == "PRJ-001"
    assert body["document"]["document_type"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert body["document"]["file_name"] == "construction-requirements.pdf"
    assert body["document"]["status"] == "UPLOADED"
    assert body["document"]["document_id"].startswith("DOC-")
    assert body["document"]["storage_path"].startswith("s3://test-bucket/PRJ-001/raw/")
    assert stub_s3.received_file_bytes == b"source document bytes"
    assert stub_s3.received_key is not None
    assert stub_s3.received_key.endswith("/construction-requirements.pdf")
