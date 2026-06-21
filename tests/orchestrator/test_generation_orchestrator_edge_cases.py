from __future__ import annotations

import json

import pytest

from app.orchestrator.generation_orchestrator import GenerationOrchestrator
from app.schemas.agent import AgentResponse
from app.schemas.artifact import ArtifactMetadata, ArtifactType
from app.schemas.request import GenerationRequest


class RecordingRetrieval:
    def __init__(self, documents=None) -> None:
        self.documents = documents if documents is not None else [
            {"chunk_id": "CHUNK-001", "text": "source text"}
        ]
        self.called = False

    async def search(self, **kwargs):
        self.called = True
        self.received_kwargs = kwargs
        return self.documents


class RecordingGenerator:
    def __init__(self, response: AgentResponse | None = None) -> None:
        self.response = response or AgentResponse(
            agent_name="RecordingGenerator",
            result={
                "artifact_type": "REQUIREMENT_SPEC",
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "title": "Login",
                        "description": "Users can sign in.",
                    }
                ],
            },
        )
        self.received_request = None

    def with_model_invoker(self, model_invoker):
        self.model_invoker = model_invoker
        return self

    async def generate(self, request):
        self.received_request = request
        json.dumps(request.context)
        return self.response


class RecordingValidator:
    def __init__(self, response: AgentResponse | None = None) -> None:
        self.called = False
        self.response = response or AgentResponse(
            agent_name="RecordingValidator",
            result={
                "artifact_type": "REQUIREMENT_SPEC",
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "title": "Login",
                        "description": "Users can sign in.",
                    }
                ],
            },
        )

    async def validate(self, result, *, expected_artifact_type=None):
        self.called = True
        self.expected_artifact_type = expected_artifact_type
        return self.response


class MissingTemplateService:
    def __init__(self) -> None:
        self.called = False

    async def resolve_template(self, *, reference, artifact_type):
        self.called = True
        return None


class RecordingArtifactService:
    def __init__(self) -> None:
        self.created = []

    async def create_artifact(self, **kwargs):
        self.created.append(kwargs)
        return ArtifactMetadata(
            artifact_id=kwargs["artifact_id"],
            project_id=kwargs["project_id"],
            artifact_type=kwargs["artifact_type"],
            name=kwargs["name"],
            source_document_ids=kwargs["source_document_ids"],
            result_json=kwargs["result_json"],
            storage_path=kwargs.get("storage_path"),
        )


@pytest.mark.anyio
async def test_missing_template_stops_before_retrieval_and_agent() -> None:
    retrieval = RecordingRetrieval()
    generator = RecordingGenerator()
    orchestrator = GenerationOrchestrator(
        retrieval=retrieval,
        artifact_generator=generator,
        validator=RecordingValidator(),
    )

    response = await orchestrator.generate_artifact(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            target_artifact_type="REQUIREMENT_SPEC",
            template_id="TPL-MISSING",
        ),
        artifact_service=RecordingArtifactService(),
        template_service=MissingTemplateService(),
    )

    assert response.success is False
    assert retrieval.called is False
    assert generator.received_request is None


@pytest.mark.anyio
async def test_empty_retrieval_context_fails_before_agent_and_persistence() -> None:
    retrieval = RecordingRetrieval(documents=[])
    generator = RecordingGenerator()
    artifact_service = RecordingArtifactService()
    orchestrator = GenerationOrchestrator(
        retrieval=retrieval,
        artifact_generator=generator,
        validator=RecordingValidator(),
    )

    response = await orchestrator.generate_artifact(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            target_artifact_type="REQUIREMENT_SPEC",
        ),
        artifact_service=artifact_service,
    )

    assert response.success is False
    assert generator.received_request is None
    assert artifact_service.created == []


@pytest.mark.anyio
async def test_agent_failure_skips_validator_and_artifact_persistence() -> None:
    validator = RecordingValidator()
    artifact_service = RecordingArtifactService()
    orchestrator = GenerationOrchestrator(
        retrieval=RecordingRetrieval(),
        artifact_generator=RecordingGenerator(
            AgentResponse(
                success=False,
                agent_name="RecordingGenerator",
                error="agent failed",
            )
        ),
        validator=validator,
    )

    response = await orchestrator.generate_artifact(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            target_artifact_type="REQUIREMENT_SPEC",
        ),
        artifact_service=artifact_service,
    )

    assert response.success is False
    assert validator.called is False
    assert artifact_service.created == []


@pytest.mark.anyio
async def test_validator_failure_skips_artifact_persistence() -> None:
    artifact_service = RecordingArtifactService()
    orchestrator = GenerationOrchestrator(
        retrieval=RecordingRetrieval(),
        artifact_generator=RecordingGenerator(),
        validator=RecordingValidator(
            AgentResponse(
                success=False,
                agent_name="RecordingValidator",
                error="invalid generated artifact",
            )
        ),
    )

    response = await orchestrator.generate_artifact(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            target_artifact_type="REQUIREMENT_SPEC",
        ),
        artifact_service=artifact_service,
    )

    assert response.success is False
    assert artifact_service.created == []


@pytest.mark.anyio
async def test_export_failure_does_not_create_orphan_artifact(monkeypatch) -> None:
    async def fail_export(*args, **kwargs):
        raise RuntimeError("export failed")

    monkeypatch.setattr(
        "app.orchestrator.generation_orchestrator.artifact_export_service.export_artifact",
        fail_export,
    )
    artifact_service = RecordingArtifactService()
    orchestrator = GenerationOrchestrator(
        retrieval=RecordingRetrieval(),
        artifact_generator=RecordingGenerator(),
        validator=RecordingValidator(),
    )

    response = await orchestrator.generate_artifact(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-001"],
            target_artifact_type="REQUIREMENT_SPEC",
        ),
        artifact_service=artifact_service,
    )

    assert response.success is False
    assert "export failed" in response.message
    assert artifact_service.created == []
