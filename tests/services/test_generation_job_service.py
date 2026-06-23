from app.schemas.progress import build_generation_progress
from app.schemas.response import GenerationResponse
from app.services.generation_job_service import _response_payload_with_preserved_progress


def test_response_payload_preserves_previous_generation_progress_on_failure() -> None:
    progress = build_generation_progress(
        stage="VALIDATION_AGENT_CHECK",
        stage_label="Validation Agent 검증 중",
        progress=70,
        progress_text="산출물 검증 중",
    )
    response = GenerationResponse(
        success=False,
        message="validation failed",
        project_id="PRJ-001",
        result={"error": "validation failed"},
    )

    payload = _response_payload_with_preserved_progress(
        response,
        {"generation_progress": progress},
    )

    assert payload["generation_progress"] == progress
    assert payload["result"]["generation_progress"] == progress
