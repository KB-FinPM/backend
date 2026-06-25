from __future__ import annotations

import pytest

from app.schemas.artifact import DocumentMetadata, DocumentType
from app.schemas.request import GenerationRequest
from app.services.generation_service import GenerationService


class StubOrchestrator:
    pass


class StubDocumentService:
    def __init__(self, documents: dict[str, DocumentMetadata]) -> None:
        self.documents = documents

    async def get_document(self, *, project_id: str, document_id: str):
        document = self.documents.get(document_id)
        if document and document.project_id == project_id:
            return document
        return None


def _doc(document_id: str, document_type: DocumentType, project_id: str = "PRJ-001"):
    return DocumentMetadata(
        document_id=document_id,
        project_id=project_id,
        document_type=document_type,
        file_name=f"{document_id}.txt",
        storage_path=f"mock://{document_id}.txt",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "target_artifact_type",
    ["REQUIREMENT_SPEC", "WBS", "SCREEN_DESIGN", "UNITTEST_SPEC"],
)
async def test_source_document_ids_are_optional_for_generation_targets(
    target_artifact_type: str,
) -> None:
    service = GenerationService(StubOrchestrator())

    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            target_artifact_type=target_artifact_type,
        ),
        document_service=StubDocumentService({}),
    )

    assert result.success is True
    assert result.error_code is None


@pytest.mark.anyio
async def test_source_validation_uses_db_document_type_not_request_claim() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-CONST"],
            source_document_type="REQUIREMENT_SPEC",
            target_artifact_type="WBS",
        ),
        document_service=StubDocumentService(
            {
                "DOC-CONST": _doc(
                    "DOC-CONST",
                    DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
                )
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"
    assert result.detail["documents"][0]["document_type"] == (
        "CONSTRUCTION_REQUIREMENT_DEFINITION"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("target_artifact_type", ["WBS", "SCREEN_DESIGN"])
async def test_downstream_artifacts_require_requirement_spec_source(
    target_artifact_type: str,
) -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-CONST"],
            target_artifact_type=target_artifact_type,
        ),
        document_service=StubDocumentService(
            {
                "DOC-CONST": _doc(
                    "DOC-CONST",
                    DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
                )
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"


@pytest.mark.anyio
async def test_unittest_generation_requires_screen_design_source() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-REQ"],
            target_artifact_type="UNITTEST_SPEC",
        ),
        document_service=StubDocumentService(
            {
                "DOC-REQ": _doc(
                    "DOC-REQ",
                    DocumentType.REQUIREMENT_SPEC,
                )
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"


@pytest.mark.anyio
async def test_unittest_generation_accepts_screen_design_source() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-SCREEN"],
            target_artifact_type="UNITTEST_SPEC",
        ),
        document_service=StubDocumentService(
            {
                "DOC-SCREEN": _doc(
                    "DOC-SCREEN",
                    DocumentType.SCREEN_DESIGN,
                )
            }
        ),
    )

    assert result.success is True
    assert result.error_code is None


@pytest.mark.anyio
async def test_meeting_notes_can_accompany_requirement_generation_but_not_replace_source() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-MEET"],
            target_artifact_type="REQUIREMENT_SPEC",
        ),
        document_service=StubDocumentService(
            {"DOC-MEET": _doc("DOC-MEET", DocumentType.MEETING_NOTES)}
        ),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"


@pytest.mark.anyio
async def test_source_validation_reports_all_missing_documents() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-OK", "DOC-MISSING-1", "DOC-MISSING-2"],
            target_artifact_type="WBS",
        ),
        document_service=StubDocumentService(
            {"DOC-OK": _doc("DOC-OK", DocumentType.REQUIREMENT_SPEC)}
        ),
    )

    assert result.success is False
    assert result.error_code == "SOURCE_DOCUMENT_NOT_FOUND"
    assert result.detail["missing_document_ids"] == [
        "DOC-MISSING-1",
        "DOC-MISSING-2",
    ]


@pytest.mark.anyio
async def test_source_validation_fails_if_any_source_document_type_is_invalid() -> None:
    service = GenerationService(StubOrchestrator())
    result = await service.validate_source_documents(
        GenerationRequest(
            project_id="PRJ-001",
            source_document_ids=["DOC-REQ", "DOC-BAD"],
            target_artifact_type="WBS",
        ),
        document_service=StubDocumentService(
            {
                "DOC-REQ": _doc("DOC-REQ", DocumentType.REQUIREMENT_SPEC),
                "DOC-BAD": _doc("DOC-BAD", DocumentType.MEETING_NOTES),
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "INVALID_SOURCE_DOCUMENT_TYPE"
    assert result.detail["documents"] == [
        {
            "document_id": "DOC-BAD",
            "document_type": "MEETING_NOTES",
            "required_document_type": "REQUIREMENT_SPEC",
        }
    ]
