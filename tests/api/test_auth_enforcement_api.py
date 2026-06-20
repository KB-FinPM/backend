from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient

from app.core.auth import DEFAULT_MVP_SCOPES
from app.core.exceptions import ApiError
from app.dependencies import (
    get_artifact_service,
    get_chat_service,
    get_document_service,
    get_generation_service,
    get_input_orchestrator,
    get_output_orchestrator,
    get_retrieval_service,
    get_template_service,
    get_traceability_service,
)
from app.schemas.artifact import ArtifactMetadata, ArtifactType, DocumentMetadata, DocumentType
from app.schemas.chat import ChatResponse, ChatState
from app.schemas.io_agent import (
    InputAgentResponse,
    NormalizedRequestType,
    OutputAgentResponse,
)
from app.schemas.response import GenerationResponse, ScheduleTodoResponse
from app.services.generation_service import GenerationSourceValidationResult


class RequirementDocumentService:
    def __init__(self) -> None:
        self.called = False

    async def get_document(self, *, project_id: str, document_id: str):
        self.called = True
        return DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=DocumentType.REQUIREMENT_SPEC,
            file_name="requirement.xlsx",
            storage_path="mock://requirement.xlsx",
        )


class SpyGenerationService:
    def __init__(self) -> None:
        self.received_request = None
        self.generate_called = False

    async def validate_source_documents(self, request, *, document_service, required_source_type=None):
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
        )

    async def generate_artifact(self, request, **kwargs):
        self.generate_called = True
        self.received_request = request
        return GenerationResponse(
            project_id=request.project_id,
            result={
                "artifact": {
                    "artifact_id": "ART-WBS-001",
                    "project_id": request.project_id,
                    "artifact_type": request.target_artifact_type.value,
                    "name": "WBS",
                    "version": 1,
                    "source_document_ids": request.source_document_ids,
                    "result_json": {},
                    "status": "CREATED",
                },
                "generated": {"artifact_type": request.target_artifact_type.value},
            },
        )


class PassingInputOrchestrator:
    def __init__(self) -> None:
        self.received_request = None

    async def normalize(self, request):
        self.received_request = request
        return InputAgentResponse(
            agent_name="PassingInputOrchestrator",
            normalized_request_type=NormalizedRequestType.ARTIFACT_GENERATION,
            structured_context={"ok": True},
        )


class PassingOutputOrchestrator:
    async def format(self, request):
        return OutputAgentResponse(
            agent_name="PassingOutputOrchestrator",
            display_payload={"formatted": True},
        )


def test_generation_api_ignores_client_permission_scope(client: TestClient) -> None:
    generation_service = SpyGenerationService()
    input_orchestrator = PassingInputOrchestrator()
    client.app.dependency_overrides[get_generation_service] = lambda: generation_service
    client.app.dependency_overrides[get_document_service] = lambda: RequirementDocumentService()
    client.app.dependency_overrides[get_input_orchestrator] = lambda: input_orchestrator
    client.app.dependency_overrides[get_output_orchestrator] = lambda: PassingOutputOrchestrator()
    client.app.dependency_overrides[get_artifact_service] = lambda: object()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()

    try:
        response = client.post(
            "/api/generate/wbs",
            headers={"X-User-Id": "trusted-user"},
            json={
                "project_id": "PRJ-001",
                "source_document_ids": ["DOC-REQ-001"],
                "source_document_type": "REQUIREMENT_SPEC",
                "permission_scope": ["attacker:scope"],
                "user_id": "attacker-user",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert generation_service.received_request is not None
    assert generation_service.received_request.user_id == "trusted-user"
    assert "attacker:scope" not in generation_service.received_request.permission_scope
    assert "artifact:generate" in generation_service.received_request.permission_scope
    assert input_orchestrator.received_request is not None
    assert "attacker:scope" not in input_orchestrator.received_request.permission_scope


class SpyChatService:
    def __init__(self) -> None:
        self.received_request = None

    async def handle_message(self, request):
        self.received_request = request
        return ChatResponse(
            conversation_id="CONV-001",
            message_id="MSG-001",
            message="ok",
            state=ChatState.IDLE,
        )


def test_chat_api_uses_current_user_not_body_user(client: TestClient) -> None:
    chat_service = SpyChatService()
    client.app.dependency_overrides[get_chat_service] = lambda: chat_service

    try:
        response = client.post(
            "/api/chat/messages",
            headers={"X-User-Id": "trusted-user"},
            json={
                "project_id": "PRJ-001",
                "user_id": "attacker-user",
                "message": "hello",
                "permission_scope": [],
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert chat_service.received_request.user_id == "trusted-user"
    assert chat_service.received_request.permission_scope == DEFAULT_MVP_SCOPES


class SpyScheduleService:
    def __init__(self) -> None:
        self.received_request = None

    async def extract_todos(self, request, *, structured_context=None):
        self.received_request = request
        return ScheduleTodoResponse(
            project_id=request.project_id,
            result={"artifact_type": "SCHEDULE_TODO_LIST", "todos": []},
        )


def test_schedule_api_uses_server_permission_scope(client: TestClient) -> None:
    schedule_service = SpyScheduleService()
    input_orchestrator = PassingInputOrchestrator()
    client.app.dependency_overrides[get_input_orchestrator] = lambda: input_orchestrator
    client.app.dependency_overrides[get_output_orchestrator] = lambda: PassingOutputOrchestrator()
    client.app.dependency_overrides["unused"] = lambda: None
    from app.dependencies import get_schedule_service

    client.app.dependency_overrides[get_schedule_service] = lambda: schedule_service

    try:
        response = client.post(
            "/api/schedule/todos",
            headers={"X-User-Id": "trusted-user"},
            json={
                "project_id": "PRJ-001",
                "user_id": "attacker-user",
                "meeting_notes": "Discussed scope.",
                "permission_scope": [],
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert schedule_service.received_request.user_id == "trusted-user"
    assert schedule_service.received_request.permission_scope == DEFAULT_MVP_SCOPES
    assert input_orchestrator.received_request.permission_scope == DEFAULT_MVP_SCOPES


class FailIfCalledTraceabilityService:
    async def create_link(self, request):
        raise AssertionError("traceability service must not run after auth denial")

    async def list_project_links(self, *, project_id: str):
        raise AssertionError("traceability service must not run after auth denial")

    async def list_artifact_links(self, *, project_id: str, artifact_id: str):
        raise AssertionError("traceability service must not run after auth denial")


def _deny_access(*args, **kwargs):
    raise ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        error_code="PROJECT_ACCESS_DENIED",
        message="project access denied",
    )


def test_traceability_api_checks_project_access(client: TestClient, monkeypatch) -> None:
    import app.api.traceability as traceability_api

    monkeypatch.setattr(traceability_api, "assert_project_access", _deny_access)
    client.app.dependency_overrides[get_traceability_service] = (
        lambda: FailIfCalledTraceabilityService()
    )

    try:
        create_response = client.post(
            "/api/projects/PRJ-001/artifact-links",
            json={
                "project_id": "PRJ-001",
                "source_artifact_id": "ART-REQ",
                "target_artifact_id": "ART-WBS",
                "relation_type": "DECOMPOSED_TO",
            },
        )
        list_response = client.get("/api/projects/PRJ-001/artifact-links")
        artifact_response = client.get("/api/projects/PRJ-001/artifacts/ART-REQ/links")
    finally:
        client.app.dependency_overrides.clear()

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert artifact_response.status_code == 403


class FailIfCalledDocumentService:
    async def get_document(self, **kwargs):
        raise AssertionError("document service must not be called after auth denial")

    async def delete_document(self, **kwargs):
        raise AssertionError("document service must not be called after auth denial")


def test_document_download_and_delete_check_access_before_service(
    client: TestClient,
    monkeypatch,
) -> None:
    import app.api.documents as documents_api

    monkeypatch.setattr(documents_api, "assert_project_access", _deny_access)
    client.app.dependency_overrides[get_document_service] = lambda: FailIfCalledDocumentService()

    try:
        download_response = client.get("/api/projects/PRJ-001/files/DOC-001/download")
        delete_response = client.delete("/api/projects/PRJ-001/files/DOC-001")
    finally:
        client.app.dependency_overrides.clear()

    assert download_response.status_code == 403
    assert delete_response.status_code == 403


class FailIfCalledArtifactService:
    async def get_artifact(self, **kwargs):
        raise AssertionError("artifact service must not be called after auth denial")

    async def list_artifacts(self, **kwargs):
        return []


def test_artifact_download_checks_access_before_service(
    client: TestClient,
    monkeypatch,
) -> None:
    import app.api.artifacts as artifacts_api

    monkeypatch.setattr(artifacts_api, "assert_project_access", _deny_access)
    client.app.dependency_overrides[get_artifact_service] = lambda: FailIfCalledArtifactService()

    try:
        response = client.get("/api/projects/PRJ-001/artifacts/ART-001/download")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 403
