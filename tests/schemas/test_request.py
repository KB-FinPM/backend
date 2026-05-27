from app.schemas.request import GenerationRequest


def test_generation_request_uses_independent_document_id_lists() -> None:
    first_request = GenerationRequest(project_id="PRJ-001")
    second_request = GenerationRequest(project_id="PRJ-002")

    first_request.document_ids.append("DOC-001")

    assert first_request.document_ids == ["DOC-001"]
    assert second_request.document_ids == []
