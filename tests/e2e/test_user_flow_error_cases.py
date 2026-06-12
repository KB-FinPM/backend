from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.core_agents.wbs_agent.agent import WbsAgent
from app.dependencies import (
    get_artifact_service,
    get_document_service,
    get_generation_service,
    get_input_orchestrator,
)
from app.schemas.agent import AgentRequest
from app.schemas.artifact import ArtifactType
from app.schemas.chat import ChatMessageRequest
from app.schemas.io_agent import InputAgentResponse, NormalizedRequestType
from app.services.generation_service import GenerationSourceValidationResult

PROJECT_ID = "PRJ-TEST-001"
INTERNAL_FRAGMENTS = (
    "Input Agent",
    "Output Agent",
    "GenerationOrchestrator",
    "traceback",
    "stack trace",
)


def assert_user_facing_message(message: str) -> None:
    assert message.strip()
    lowered = message.lower()
    for fragment in INTERNAL_FRAGMENTS:
        assert fragment.lower() not in lowered


@pytest.mark.anyio
async def test_user_flow_wbs_request_without_document_gets_required_info(
    scenario_services,
) -> None:
    orchestrator = scenario_services["chat_orchestrator"]

    response = await orchestrator.handle_message(
        ChatMessageRequest(
            project_id=PROJECT_ID,
            user_id="USER-001",
            message="WBS 만들어줘",
        )
    )

    assert response.state == "WAITING_REQUIRED_INFO"
    assert response.result["required_source_document_types"] == ["REQUIREMENT_SPEC"]
    assert response.pending_action is None
    assert_user_facing_message(response.message)


class UploadDocumentService:
    async def upload_to_storage(
        self,
        *,
        file_bytes: bytes,
        project_id: str,
        document_id: str,
        file_name: str,
        upload_prefix: str,
    ) -> str:
        return f"mock://upload/{project_id}/{document_id}/{file_name}"


class UnsupportedFileInputOrchestrator:
    async def normalize(self, request):
        return InputAgentResponse(
            success=False,
            agent_name="UnsupportedFileInputOrchestrator",
            normalized_request_type=NormalizedRequestType.UNKNOWN,
            error="unsupported file",
            validation_errors=["unsupported file extension"],
        )


def test_user_flow_unsupported_upload_returns_422_without_500(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: UploadDocumentService()
    client.app.dependency_overrides[get_input_orchestrator] = (
        lambda: UnsupportedFileInputOrchestrator()
    )

    try:
        response = client.post(
            "/upload",
            data={
                "project_id": PROJECT_ID,
                "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
            files={"file": ("unsupported.exe", b"not empty", "application/octet-stream")},
        )
    finally:
        client.app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["error_code"] == "UNSUPPORTED_UPLOAD_FILE_TYPE"
    assert "traceback" not in str(body).lower()


@pytest.mark.anyio
async def test_user_flow_invalid_wbs_schedule_input_does_not_crash() -> None:
    response = await WbsAgent().generate(
        AgentRequest(
            project_id=PROJECT_ID,
            documents=[{"chunk_id": "CHUNK-001", "text": "mobile login"}],
            context={
                "start_date": "2024-99-99",
                "project_period": "abc",
                "requirement_artifact": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-001",
                            "requirement_name": "Mobile login",
                            "description": "Users can sign in.",
                            "biz_requirement_name": "Mobile banking",
                        }
                    ]
                },
            },
        )
    )

    assert response.success is True
    assert all("planned_start_date" not in task for task in response.result["tasks"])


class MissingDocumentService:
    async def get_document(self, *, project_id: str, document_id: str):
        return None


class ValidationOnlyGenerationService:
    async def validate_source_documents(
        self,
        request,
        *,
        document_service,
        required_source_type=None,
    ) -> GenerationSourceValidationResult:
        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=request.target_artifact_type,
            required_source_type=required_source_type,
            missing_document_ids=list(request.source_document_ids),
        )

    async def generate_artifact(self, *args, **kwargs):
        raise AssertionError("generation must not run when source document is missing")


def test_user_flow_missing_document_id_generation_returns_404(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: MissingDocumentService()
    client.app.dependency_overrides[get_generation_service] = (
        lambda: ValidationOnlyGenerationService()
    )

    try:
        response = client.post(
            "/generate/wbs",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": ["DOC-404"],
                "source_document_type": "REQUIREMENT_SPEC",
                "target_artifact_type": "WBS",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 404
    assert body["error_code"] == "SOURCE_DOCUMENT_NOT_FOUND"
    assert body["detail"]["missing_document_ids"] == ["DOC-404"]
    assert "traceback" not in str(body).lower()


class MissingArtifactService:
    async def get_artifact(self, *, project_id: str, artifact_id: str):
        return None

    async def list_artifacts(self, *, project_id: str):
        return []


def test_user_flow_missing_artifact_download_returns_404(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_artifact_service] = lambda: MissingArtifactService()

    try:
        response = client.get(f"/projects/{PROJECT_ID}/artifacts/ART-404/download")
    finally:
        client.app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 404
    assert body["error_code"] == "ARTIFACT_NOT_FOUND"
    assert body["detail"] == {"project_id": PROJECT_ID, "artifact_id": "ART-404"}
    assert "traceback" not in str(body).lower()
