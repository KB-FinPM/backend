# EN: Tests for API request schema behavior.
# KO: API 요청 스키마 동작을 검증하는 테스트입니다.

from app.schemas.request import GenerationRequest, ScheduleTodoRequest


def test_generation_request_uses_independent_document_id_lists() -> None:
    first_request = GenerationRequest(project_id="PRJ-001")
    second_request = GenerationRequest(project_id="PRJ-002")

    first_request.document_ids.append("DOC-001")
    first_request.permission_scope.append("artifact:generate")

    assert first_request.document_ids == ["DOC-001"]
    assert second_request.document_ids == []
    assert first_request.permission_scope == ["project:read", "artifact:generate"]
    assert second_request.permission_scope == ["project:read"]


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


def test_generation_request_accepts_permission_scope() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        permission_scope=["project:read", "artifact:generate"],
    )

    assert request.permission_scope == ["project:read", "artifact:generate"]


def test_schedule_todo_request_accepts_meeting_notes() -> None:
    request = ScheduleTodoRequest(
        project_id="PRJ-001",
        meeting_notes="Discussed login scope and due dates.",
        source_document_ids=["DOC-001"],
        user_id="USER-001",
    )

    assert request.project_id == "PRJ-001"
    assert request.source_document_ids == ["DOC-001"]
    assert request.permission_scope == ["project:read"]
    assert "Discussed login scope" in request.meeting_notes
