# EN: Tests for input/output agent envelope schemas.
# KO: Input/Output Agent envelope 스키마 테스트입니다.

from app.schemas.io_agent import (
    InputAgentRequest,
    InputFilePayload,
    InputType,
    OutputAgentRequest,
    OutputResponseType,
)


def test_input_agent_request_accepts_standard_user_file_payload() -> None:
    request = InputAgentRequest(
        project_id="PRJ-001",
        user_id="USER-001",
        permission_scope=["project:read"],
        input_type=InputType.FILE,
        raw_payload={"document_type": "REQUIREMENT_SPEC"},
        files=[
            InputFilePayload(
                file_name="requirements.txt",
                file_bytes=b"requirements",
                content_type="text/plain",
            )
        ],
    )

    assert request.project_id == "PRJ-001"
    assert request.files[0].content_type == "text/plain"
    assert request.permission_scope == ["project:read"]


def test_output_agent_request_accepts_standard_result_payload() -> None:
    request = OutputAgentRequest(
        project_id="PRJ-001",
        response_type=OutputResponseType.ARTIFACT_EXPORT,
        result_json={"artifact_type": "REQUIREMENT_SPEC"},
        artifact={"artifact_id": "ART-001"},
    )

    assert request.output_format == "markdown"
    assert request.artifact == {"artifact_id": "ART-001"}
