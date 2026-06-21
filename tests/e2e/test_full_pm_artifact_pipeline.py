from __future__ import annotations

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.dependencies import (
    get_artifact_service,
    get_document_service,
    get_generation_service,
    get_input_orchestrator,
    get_output_orchestrator,
    get_project_service,
    get_retrieval_service,
    get_template_service,
)
from app.schemas.artifact import ArtifactMetadata, ArtifactStatus, ArtifactType
from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.io_agent import (
    InputAgentResponse,
    InputType,
    NormalizedRequestType,
    OutputAgentResponse,
)
from app.schemas.project import ProjectMetadata
from app.schemas.response import GenerationResponse
from app.services.generation_service import GenerationSourceValidationResult


PROJECT_ID = "PRJ-PIPELINE-001"


class PipelineStorageService:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []

    async def delete_by_storage_path(self, storage_path: str) -> None:
        self.deleted_paths.append(storage_path)


class PipelineDocumentService:
    def __init__(self) -> None:
        self.documents: dict[str, DocumentMetadata] = {}
        self.storage_service = PipelineStorageService()

    async def upload_to_storage(
        self,
        *,
        file_bytes: bytes,
        project_id: str,
        document_id: str,
        file_name: str,
        upload_prefix: str,
    ) -> str:
        return f"mock://uploaded/{project_id}/{document_id}/{file_name}"

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
        document = DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )
        self.documents[document_id] = document
        return document

    def add_generated_document(
        self,
        *,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
    ) -> DocumentMetadata:
        document = DocumentMetadata(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )
        self.documents[document_id] = document
        return document

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> DocumentMetadata | None:
        document = self.documents.get(document_id)
        if document and document.project_id == project_id:
            return document
        return None


class PipelineArtifactService:
    def __init__(self) -> None:
        self.artifacts: dict[str, ArtifactMetadata] = {}

    async def create_artifact(self, **kwargs) -> ArtifactMetadata:
        artifact = ArtifactMetadata(
            artifact_id=kwargs["artifact_id"],
            project_id=kwargs["project_id"],
            artifact_type=kwargs["artifact_type"],
            name=kwargs["name"],
            version=kwargs.get("version", 1),
            source_document_ids=kwargs.get("source_document_ids") or [],
            template_id=kwargs.get("template_id"),
            template_version=kwargs.get("template_version"),
            result_json=kwargs.get("result_json") or {},
            storage_path=kwargs.get("storage_path"),
            status=ArtifactStatus.CREATED,
        )
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    async def get_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactMetadata | None:
        artifact = self.artifacts.get(artifact_id)
        if artifact and artifact.project_id == project_id:
            return artifact
        return None

    async def list_artifacts(self, *, project_id: str) -> list[ArtifactMetadata]:
        return [
            artifact
            for artifact in self.artifacts.values()
            if artifact.project_id == project_id
        ]


class PipelineProjectService:
    async def get_project(self, project_id: str):
        return ProjectMetadata(
            project_id=project_id,
            project_name="Pipeline Project",
            start_date=date(2026, 1, 5),
        )


class PipelineInputOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    async def normalize(self, request):
        self.requests.append(request)
        normalized_type = (
            NormalizedRequestType.DOCUMENT_INGESTION
            if request.input_type == InputType.FILE
            else NormalizedRequestType.ARTIFACT_GENERATION
        )
        return InputAgentResponse(
            agent_name="PipelineInputOrchestrator",
            normalized_request_type=normalized_type,
            structured_context={"text": "parsed source"},
        )


class PipelineOutputOrchestrator:
    async def format(self, request):
        return OutputAgentResponse(
            agent_name="PipelineOutputOrchestrator",
            display_payload={"message": request.message, "result": request.result_json},
        )


class PipelineGenerationService:
    def __init__(self, *, fail_requirement: bool = False) -> None:
        self.fail_requirement = fail_requirement
        self.requests = []

    async def validate_source_documents(
        self,
        request,
        *,
        document_service,
        required_source_type=None,
    ) -> GenerationSourceValidationResult:
        target_type = ArtifactType(request.target_artifact_type)
        required = required_source_type or (
            DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION
            if target_type == ArtifactType.REQUIREMENT_SPEC
            else DocumentType.REQUIREMENT_SPEC
        )
        missing: list[str] = []
        invalid: list[dict[str, str]] = []
        for document_id in request.source_document_ids:
            document = await document_service.get_document(
                project_id=request.project_id,
                document_id=document_id,
            )
            if document is None:
                missing.append(document_id)
            elif document.document_type != required:
                invalid.append(
                    {
                        "document_id": document.document_id,
                        "document_type": document.document_type.value,
                        "required_document_type": required.value,
                    }
                )

        return GenerationSourceValidationResult(
            project_id=request.project_id,
            target_artifact_type=target_type,
            required_source_type=required,
            missing_document_ids=missing,
            invalid_type_documents=invalid,
        )

    async def generate_artifact(
        self,
        request,
        *,
        artifact_service=None,
        retrieval_service=None,
        template_service=None,
        document_service=None,
    ) -> GenerationResponse:
        target_type = ArtifactType(request.target_artifact_type)
        self.requests.append(request)
        if self.fail_requirement and target_type == ArtifactType.REQUIREMENT_SPEC:
            return GenerationResponse(
                success=False,
                project_id=request.project_id,
                message="requirement generation failed",
                result={"error": "requirement generation failed"},
            )

        artifact_id = f"ART-{target_type.value}-PIPELINE"
        file_name = f"{target_type.value}.xlsx"
        storage_path = f"mock://generated/{artifact_id}/{file_name}"
        generated = self._generated_payload(target_type)
        artifact = await artifact_service.create_artifact(
            artifact_id=artifact_id,
            project_id=request.project_id,
            artifact_type=target_type,
            name=file_name,
            source_document_ids=request.source_document_ids,
            result_json=generated,
            storage_path=storage_path,
        )
        exported_document = None
        if target_type == ArtifactType.REQUIREMENT_SPEC:
            exported_document = document_service.add_generated_document(
                document_id="DOC-REQUIREMENT-SPEC-PIPELINE",
                project_id=request.project_id,
                document_type=DocumentType.REQUIREMENT_SPEC,
                file_name=file_name,
                storage_path=storage_path,
            )

        result: dict[str, Any] = {
            "artifact": artifact.model_dump(mode="json"),
            "generated": generated,
            "exported_file": {
                "file_name": file_name,
                "content_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "storage_path": storage_path,
            },
        }
        if exported_document is not None:
            result["exported_document"] = exported_document.model_dump(mode="json")

        return GenerationResponse(
            project_id=request.project_id,
            message="artifact generated",
            result=result,
        )

    def _generated_payload(self, artifact_type: ArtifactType) -> dict[str, Any]:
        if artifact_type == ArtifactType.REQUIREMENT_SPEC:
            return {
                "artifact_type": artifact_type.value,
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "title": "Login",
                        "description": "Users can sign in.",
                    }
                ],
            }
        if artifact_type == ArtifactType.WBS:
            return {
                "artifact_type": artifact_type.value,
                "tasks": [
                    {
                        "task_id": "WBS-001",
                        "name": "Build login",
                        "source_requirement_ids": ["REQ-001"],
                    }
                ],
            }
        if artifact_type == ArtifactType.SCREEN_DESIGN:
            return {
                "artifact_type": artifact_type.value,
                "screens": [
                    {
                        "screen_id": "SCR-001",
                        "name": "Login screen",
                        "source_requirement_ids": ["REQ-001"],
                    }
                ],
            }
        return {
            "artifact_type": artifact_type.value,
            "test_cases": [
                {
                    "test_case_id": "TC-001",
                    "test_case_name": "Login success",
                    "requirement_id": "REQ-001",
                    "requirement_name": "Login",
                    "scenario_id": "SCN-001",
                    "test_content": "Enter valid credentials.",
                }
            ],
        }


def _install_pipeline_fakes(
    client: TestClient,
    *,
    document_service: PipelineDocumentService,
    artifact_service: PipelineArtifactService,
    generation_service: PipelineGenerationService,
    input_orchestrator: PipelineInputOrchestrator | None = None,
) -> None:
    client.app.dependency_overrides[get_document_service] = lambda: document_service
    client.app.dependency_overrides[get_artifact_service] = lambda: artifact_service
    client.app.dependency_overrides[get_generation_service] = lambda: generation_service
    client.app.dependency_overrides[get_input_orchestrator] = (
        lambda: input_orchestrator or PipelineInputOrchestrator()
    )
    client.app.dependency_overrides[get_output_orchestrator] = (
        lambda: PipelineOutputOrchestrator()
    )
    client.app.dependency_overrides[get_project_service] = lambda: PipelineProjectService()
    client.app.dependency_overrides[get_retrieval_service] = lambda: object()
    client.app.dependency_overrides[get_template_service] = lambda: object()


def test_full_pm_artifact_pipeline_upload_generate_and_download(
    client: TestClient,
    monkeypatch,
) -> None:
    document_service = PipelineDocumentService()
    artifact_service = PipelineArtifactService()
    generation_service = PipelineGenerationService()
    input_orchestrator = PipelineInputOrchestrator()
    _install_pipeline_fakes(
        client,
        document_service=document_service,
        artifact_service=artifact_service,
        generation_service=generation_service,
        input_orchestrator=input_orchestrator,
    )

    async def fake_download_by_storage_path(storage_path: str):
        assert storage_path.startswith("mock://generated/")
        return b"artifact bytes", "application/octet-stream"

    monkeypatch.setattr(
        "app.api.artifacts.s3_service.download_by_storage_path",
        fake_download_by_storage_path,
    )

    try:
        upload_response = client.post(
            "/api/upload",
            data={
                "project_id": PROJECT_ID,
                "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
            files={"file": ("rfp.txt", b"Build login", "text/plain")},
        )
        assert upload_response.status_code == 200
        source_document_id = upload_response.json()["document"]["document_id"]

        requirement_response = client.post(
            "/api/generate/requirement",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": [source_document_id],
                "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
        )
        assert requirement_response.status_code == 200
        requirement_document_id = requirement_response.json()["document_id"]
        assert requirement_document_id == "DOC-REQUIREMENT-SPEC-PIPELINE"

        wbs_response = client.post(
            "/api/generate/wbs",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": [requirement_document_id],
            },
        )
        screen_response = client.post(
            "/api/generate/screen-design",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": [requirement_document_id],
            },
        )
        unittest_response = client.post(
            "/api/generate/unittest",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": [requirement_document_id],
            },
        )
        assert wbs_response.status_code == 200
        assert screen_response.status_code == 200
        assert unittest_response.status_code == 200

        download_artifact_id = unittest_response.json()["result"]["artifact"][
            "artifact_id"
        ]
        download_response = client.get(
            f"/api/projects/{PROJECT_ID}/artifacts/{download_artifact_id}/download"
        )
    finally:
        client.app.dependency_overrides.clear()

    assert download_response.status_code == 200
    assert download_response.content == b"artifact bytes"
    assert set(artifact.artifact_type for artifact in artifact_service.artifacts.values()) == {
        ArtifactType.REQUIREMENT_SPEC,
        ArtifactType.WBS,
        ArtifactType.SCREEN_DESIGN,
        ArtifactType.UNITTEST_SPEC,
    }
    assert [request.target_artifact_type for request in generation_service.requests] == [
        ArtifactType.REQUIREMENT_SPEC,
        ArtifactType.WBS,
        ArtifactType.SCREEN_DESIGN,
        ArtifactType.UNITTEST_SPEC,
    ]


def test_pipeline_failure_does_not_persist_requirement_artifact(
    client: TestClient,
) -> None:
    document_service = PipelineDocumentService()
    artifact_service = PipelineArtifactService()
    generation_service = PipelineGenerationService(fail_requirement=True)
    _install_pipeline_fakes(
        client,
        document_service=document_service,
        artifact_service=artifact_service,
        generation_service=generation_service,
    )

    try:
        upload_response = client.post(
            "/api/upload",
            data={
                "project_id": PROJECT_ID,
                "document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
            files={"file": ("rfp.txt", b"Build login", "text/plain")},
        )
        response = client.post(
            "/api/generate/requirement",
            json={
                "project_id": PROJECT_ID,
                "source_document_ids": [
                    upload_response.json()["document"]["document_id"]
                ],
                "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error_code"] == "GENERATION_FAILED"
    assert artifact_service.artifacts == {}
