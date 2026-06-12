# EN: Tests for API request schema behavior.
# KO: API 요청 스키마 동작을 검증하는 테스트입니다.

import pytest

from pydantic import ValidationError

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


def test_generation_request_accepts_optional_wbs_schedule_fields() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        start_date="2024.01.10",
        project_period="6개월",
    )
    legacy_request = GenerationRequest(project_id="PRJ-002")

    assert request.start_date == "2024-01-10"
    assert request.project_period == "6개월"
    assert legacy_request.start_date is None
    assert legacy_request.project_period is None


@pytest.mark.parametrize("start_date", ["20266-01-01", "02026-01-01", "2024-02-30"])
def test_generation_request_rejects_invalid_start_date(start_date) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(project_id="PRJ-001", start_date=start_date)


def test_generation_request_accepts_requirement_generation_payload() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        project_name="Requirement Project",
        source_document_ids=["DOC-CONST-001"],
        source_document_type="CONSTRUCTION_REQUIREMENT_DEFINITION",
        target_artifact_type="REQUIREMENT_SPEC",
        template_id="TPL-REQ-SPEC-DEFAULT",
        query="Create a requirement specification.",
        author="Analyst",
        permission_scope=["project:read", "artifact:generate"],
    )

    assert request.project_id == "PRJ-001"
    assert request.project_name == "Requirement Project"
    assert request.source_document_ids == ["DOC-CONST-001"]
    assert request.document_ids == ["DOC-CONST-001"]
    assert request.source_document_type == "CONSTRUCTION_REQUIREMENT_DEFINITION"
    assert request.target_artifact_type == "REQUIREMENT_SPEC"
    assert request.template_id == "TPL-REQ-SPEC-DEFAULT"
    assert request.permission_scope == ["project:read", "artifact:generate"]


def test_generation_request_accepts_wbs_payload_without_schedule_fields() -> None:
    request = GenerationRequest(
        project_id="PRJ-001",
        source_document_ids=["DOC-REQ-001"],
        source_document_type="REQUIREMENT_SPEC",
        target_artifact_type="WBS",
        query="Create a WBS from the requirement specification.",
    )

    assert request.target_artifact_type == "WBS"
    assert request.source_document_type == "REQUIREMENT_SPEC"
    assert request.start_date is None
    assert request.project_period is None


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
