from app.schemas.request import GenerationRequest


def test_generation_request_uses_independent_document_id_lists() -> None:
    first_request = GenerationRequest(project_id="PRJ-001")
    second_request = GenerationRequest(project_id="PRJ-002")

    first_request.document_ids.append("DOC-001")

    assert first_request.document_ids == ["DOC-001"]
    assert second_request.document_ids == []


def test_generation_request_syncs_legacy_document_ids() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        document_ids=["DOC-001"],
    )

    assert request.source_document_ids == ["DOC-001"]
    assert request.document_ids == ["DOC-001"]


def test_generation_request_syncs_source_document_ids() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_ids=["DOC-001"],
    )

    assert request.source_document_ids == ["DOC-001"]
    assert request.document_ids == ["DOC-001"]


def test_generation_request_builds_generation_flow() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_type="REQUIREMENT_SPEC",
        target_artifact_type="SCREEN_DESIGN",
        template_id="TPL-SCREEN-DESIGN",
        template_version="v1",
    )

    flow = request.generation_flow()

    assert flow.source_document_type == "REQUIREMENT_SPEC"
    assert flow.target_artifact_type == "SCREEN_DESIGN"
    assert flow.template.template_id == "TPL-SCREEN-DESIGN"
    assert flow.template.template_version == "v1"
