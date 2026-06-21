from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import (
    get_document_service,
    get_input_orchestrator,
    get_output_orchestrator,
)
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.io_agent import InputAgentResponse, NormalizedRequestType, OutputAgentResponse


class RecordingStorageService:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []

    async def delete_by_storage_path(self, storage_path: str) -> None:
        self.deleted_paths.append(storage_path)


class RecordingDocumentService:
    def __init__(self, *, fail_ingest: bool = False) -> None:
        self.storage_service = RecordingStorageService()
        self.fail_ingest = fail_ingest
        self.upload_called = False
        self.ingest_called = False
        self.received_file_name: str | None = None
        self.received_storage_path: str | None = None

    async def upload_to_storage(
        self,
        *,
        file_bytes: bytes,
        project_id: str,
        document_id: str,
        file_name: str,
        upload_prefix: str,
    ) -> str:
        self.upload_called = True
        self.received_file_name = file_name
        self.received_storage_path = f"mock://{project_id}/{document_id}/{file_name}"
        return self.received_storage_path

    async def ingest_uploaded_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
        parsed_context: dict | None = None,
        progress_reporter=None,
    ) -> DocumentMetadata:
        self.ingest_called = True
        if self.fail_ingest:
            raise RuntimeError("ingest failed")
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )


class RecordingInputOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.called = False
        self.received_file_name: str | None = None

    async def normalize(self, request):
        self.called = True
        self.received_file_name = request.files[0].file_name
        if self.fail:
            return InputAgentResponse(
                success=False,
                agent_name="RecordingInputOrchestrator",
                normalized_request_type=NormalizedRequestType.UNKNOWN,
                error="normalization failed",
                validation_errors=["bad input"],
            )
        return InputAgentResponse(
            agent_name="RecordingInputOrchestrator",
            normalized_request_type=NormalizedRequestType.DOCUMENT_INGESTION,
            structured_context={"text": "parsed"},
        )


class StubOutputOrchestrator:
    async def format(self, request):
        return OutputAgentResponse(
            agent_name="StubOutputOrchestrator",
            display_payload={"formatted": True},
        )


def _install_upload_fakes(
    client: TestClient,
    document_service: RecordingDocumentService,
    input_orchestrator: RecordingInputOrchestrator,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: document_service
    client.app.dependency_overrides[get_input_orchestrator] = lambda: input_orchestrator
    client.app.dependency_overrides[get_output_orchestrator] = lambda: StubOutputOrchestrator()


def test_upload_strips_posix_and_windows_path_segments(client: TestClient) -> None:
    for uploaded_name in ("../../secret.txt", r"C:\Users\me\secret.txt"):
        document_service = RecordingDocumentService()
        input_orchestrator = RecordingInputOrchestrator()
        _install_upload_fakes(client, document_service, input_orchestrator)

        try:
            response = client.post(
                "/api/upload",
                data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
                files={"file": (uploaded_name, b"hello", "text/plain")},
            )
        finally:
            client.app.dependency_overrides.clear()

        assert response.status_code == 200
        assert document_service.received_file_name == "secret.txt"
        assert ".." not in document_service.received_storage_path
        assert "\\" not in document_service.received_storage_path


def test_upload_uppercase_extension_is_lowered_for_parser_only(client: TestClient) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("REQ-SPEC.PDF", b"%PDF text", "application/pdf")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert document_service.received_file_name == "REQ-SPEC.PDF"
    assert input_orchestrator.received_file_name == "REQ-SPEC.pdf"


def test_upload_rejects_mismatched_extension_and_mime_before_storage(
    client: TestClient,
) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("requirements.pdf", b"a,b", "text/csv")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "UPLOAD_CONTENT_TYPE_MISMATCH"
    assert document_service.upload_called is False
    assert input_orchestrator.called is False


def test_upload_allows_generic_mime_for_supported_extension(client: TestClient) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("requirements.md", b"# Requirements", "application/octet-stream")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert input_orchestrator.received_file_name == "requirements.md"


def test_upload_without_extension_uses_supported_mime_policy(client: TestClient) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("uploaded-file", b"%PDF text", "application/pdf")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert input_orchestrator.received_file_name == "uploaded-file.pdf"


def test_upload_max_bytes_boundary(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.api.upload.settings.UPLOAD_MAX_BYTES", 5)
    monkeypatch.setattr("app.api.upload.settings.UPLOAD_READ_CHUNK_BYTES", 2)

    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)
    try:
        ok_response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("five.txt", b"12345", "text/plain")},
        )
        too_large_response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("six.txt", b"123456", "text/plain")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert ok_response.status_code == 200
    assert too_large_response.status_code == 413
    assert too_large_response.json()["error_code"] == "UPLOAD_FILE_TOO_LARGE"


def test_upload_normalization_failure_cleans_uploaded_object(client: TestClient) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator(fail=True)
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("requirements.txt", b"hello", "text/plain")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "DOCUMENT_INPUT_NORMALIZATION_FAILED"
    assert document_service.storage_service.deleted_paths == [
        document_service.received_storage_path
    ]
    assert document_service.ingest_called is False


def test_upload_ingest_failure_cleans_uploaded_object(client: TestClient) -> None:
    document_service = RecordingDocumentService(fail_ingest=True)
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("requirements.txt", b"hello", "text/plain")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 500
    assert document_service.storage_service.deleted_paths == [
        document_service.received_storage_path
    ]
    assert "traceback" not in response.text.lower()


def test_upload_unsupported_extension_skips_storage_and_input(client: TestClient) -> None:
    document_service = RecordingDocumentService()
    input_orchestrator = RecordingInputOrchestrator()
    _install_upload_fakes(client, document_service, input_orchestrator)

    try:
        response = client.post(
            "/api/upload",
            data={"project_id": "PRJ-001", "document_type": "REQUIREMENT_SPEC"},
            files={"file": ("malware.exe", b"not empty", "application/octet-stream")},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "UNSUPPORTED_UPLOAD_FILE_TYPE"
    assert document_service.upload_called is False
    assert input_orchestrator.called is False
