# EN: Tests for input/output agent envelope schemas.
# KO: Input/Output Agent envelope 스키마 테스트입니다.

from app.schemas.io_agent import InputAgentRequest, OutputAgentRequest


def test_input_agent_request_accepts_external_file_payload() -> None:
    request = InputAgentRequest(
        project_id="PRJ-001",
        file_name="requirements.txt",
        file_bytes=b"requirements",
        content_type="text/plain",
    )

    assert request.project_id == "PRJ-001"
    assert request.content_type == "text/plain"


def test_output_agent_request_accepts_artifact_json() -> None:
    request = OutputAgentRequest(
        project_id="PRJ-001",
        artifact_type="REQUIREMENT_SPEC",
        result_json={"artifact_type": "REQUIREMENT_SPEC"},
    )

    assert request.output_format == "markdown"
    assert request.result_json["artifact_type"] == "REQUIREMENT_SPEC"
