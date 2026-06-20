from app.schemas.progress import (
    build_generation_progress,
    build_progress_segment,
    normalize_generation_progress,
)


def test_normalize_legacy_counter_as_batch_progress_not_overall() -> None:
    progress = normalize_generation_progress(
        {
            "current": 15,
            "total": 30,
            "progress": 50,
            "progress_text": "15/30",
            "label": "LLM batch 처리",
        }
    )

    assert progress["stage"] == "CORE_AGENT_EXTRACTION"
    assert progress["progress"] == 45
    assert progress["batch_progress"]["current"] == 15
    assert progress["batch_progress"]["total"] == 30
    assert progress["batch_progress"]["progress"] == 50
    assert "sub_progress" not in progress


def test_build_progress_segment_handles_missing_total_as_loading_text() -> None:
    segment = build_progress_segment(
        progress_type="CHUNK_PROCESSING",
        label="원본 문서 chunk 처리",
        current=137,
        total=0,
        unit="chunks",
    )

    assert segment["current"] == 137
    assert segment["total"] == 0
    assert "progress" not in segment
    assert segment["message"] == "원본 문서 chunk 처리 중"


def test_normalize_preserves_structured_sub_and_batch_progress() -> None:
    progress = normalize_generation_progress(
        build_generation_progress(
            stage="CORE_AGENT_EXTRACTION",
            stage_label="Core Agent 요구사항 추출 중",
            progress=45,
            progress_text="요구사항 추출 중",
            sub_progress={
                "type": "SOURCE_CHUNK_PROCESSING",
                "label": "원본 문서 chunk 처리",
                "current": 137,
                "total": 236,
                "unit": "chunks",
            },
            batch_progress={
                "type": "LLM_BATCH",
                "label": "LLM batch 처리",
                "current": 15,
                "total": 30,
                "unit": "batches",
            },
        )
    )

    assert progress["progress"] == 45
    assert progress["sub_progress"]["progress"] == 58
    assert progress["batch_progress"]["progress"] == 50
