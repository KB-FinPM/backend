# EN: Tests for document and artifact schema contracts.
# KO: 문서 및 산출물 스키마 계약을 검증하는 테스트입니다.

from app.schemas.artifact import ArtifactType, DocumentType, GenerationFlow


def test_generation_flow_supports_confirmed_document_paths() -> None:
    requirement_flow = GenerationFlow(
        source_document_type=DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION,
        target_artifact_type=ArtifactType.REQUIREMENT_SPEC,
    )
    screen_flow = GenerationFlow(
        source_document_type=DocumentType.REQUIREMENT_SPEC,
        target_artifact_type=ArtifactType.SCREEN_DESIGN,
    )
    wbs_flow = GenerationFlow(
        source_document_type=DocumentType.REQUIREMENT_SPEC,
        target_artifact_type=ArtifactType.WBS,
    )

    assert requirement_flow.source_document_type == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert requirement_flow.target_artifact_type == "REQUIREMENT_SPEC"
    assert screen_flow.target_artifact_type == "SCREEN_DESIGN"
    assert wbs_flow.target_artifact_type == "WBS"
