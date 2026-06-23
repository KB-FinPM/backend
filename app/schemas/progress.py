"""Shared progress payload helpers for generation and ingestion flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


DEFAULT_GENERATION_STAGE = "CORE_AGENT_EXTRACTION"
DEFAULT_GENERATION_STAGE_LABEL = "Core Agent 요구사항 추출 중"
DEFAULT_GENERATION_PROGRESS_TEXT = "요구사항 추출 중"


def build_progress_segment(
    *,
    progress_type: str,
    label: str,
    current: int | None = None,
    total: int | None = None,
    unit: str | None = None,
    progress: int | float | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Build a chunk/batch/embedding/indexing progress segment."""
    current_value = _coerce_non_negative_int(current)
    total_value = _coerce_non_negative_int(total)
    payload: dict[str, Any] = {
        "type": progress_type,
        "label": label,
    }

    if current_value is not None:
        payload["current"] = current_value
    if total_value is not None:
        payload["total"] = total_value
    if unit:
        payload["unit"] = unit

    progress_value = (
        _clamp_progress(progress)
        if progress is not None
        else _percent(current_value, total_value)
    )
    if progress_value is not None:
        payload["progress"] = progress_value

    payload["message"] = message or _segment_message(
        label=label,
        current=current_value,
        total=total_value,
        unit=unit,
    )
    return payload


def build_generation_progress(
    *,
    stage: str,
    stage_label: str,
    progress: int | float,
    progress_text: str | None = None,
    sub_progress: Mapping[str, Any] | None = None,
    batch_progress: Mapping[str, Any] | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build the top-level generation progress contract."""
    payload: dict[str, Any] = {
        "stage": stage,
        "stage_label": stage_label,
        "progress": _clamp_progress(progress),
        "progress_text": progress_text or stage_label,
        "updated_at": updated_at or _utc_now_iso(),
    }
    if sub_progress is not None:
        payload["sub_progress"] = dict(sub_progress)
    if batch_progress is not None:
        payload["batch_progress"] = dict(batch_progress)
    return payload


def normalize_generation_progress(
    payload: Mapping[str, Any] | None,
    *,
    default_stage: str = DEFAULT_GENERATION_STAGE,
    default_stage_label: str = DEFAULT_GENERATION_STAGE_LABEL,
    default_progress: int | float = 45,
    default_progress_text: str = DEFAULT_GENERATION_PROGRESS_TEXT,
) -> dict[str, Any]:
    """Normalize legacy and structured progress payloads to the shared contract."""
    source: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    structured = any(
        key in source
        for key in ("stage", "stage_label", "sub_progress", "batch_progress")
    )

    progress = source.get("progress") if structured else default_progress
    normalized = build_generation_progress(
        stage=str(source.get("stage") or default_stage),
        stage_label=str(source.get("stage_label") or default_stage_label),
        progress=progress if progress is not None else default_progress,
        progress_text=str(source.get("progress_text") or default_progress_text),
        updated_at=str(source.get("updated_at")) if source.get("updated_at") else None,
    )

    sub_progress = _normalize_segment(source.get("sub_progress"))
    if sub_progress is not None:
        normalized["sub_progress"] = sub_progress

    batch_progress = _normalize_segment(source.get("batch_progress"))
    if batch_progress is None and _has_legacy_counter(source):
        batch_progress = build_progress_segment(
            progress_type=str(source.get("type") or "LLM_BATCH"),
            label=str(source.get("label") or "LLM batch 처리"),
            current=_coerce_non_negative_int(source.get("current")),
            total=_coerce_non_negative_int(source.get("total")),
            unit=str(source.get("unit") or "batches"),
            progress=source.get("progress"),
            message=str(source.get("message")) if source.get("message") else None,
        )
    if batch_progress is not None:
        normalized["batch_progress"] = batch_progress

    return normalized


def _normalize_segment(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return build_progress_segment(
        progress_type=str(value.get("type") or "SUB_PROGRESS"),
        label=str(value.get("label") or value.get("type") or "세부 처리"),
        current=_coerce_non_negative_int(value.get("current")),
        total=_coerce_non_negative_int(value.get("total")),
        unit=str(value.get("unit")) if value.get("unit") else None,
        progress=value.get("progress"),
        message=str(value.get("message")) if value.get("message") else None,
    )


def _has_legacy_counter(source: Mapping[str, Any]) -> bool:
    return "current" in source or "total" in source


def _segment_message(
    *,
    label: str,
    current: int | None,
    total: int | None,
    unit: str | None,
) -> str:
    if current is not None and total is not None and total > 0:
        unit_suffix = f" {unit}" if unit else ""
        return f"{label} 중 {current}/{total}{unit_suffix}"
    return f"{label} 중"


def _percent(current: int | None, total: int | None) -> int | None:
    if current is None or total is None or total <= 0:
        return None
    return _clamp_progress(round(current * 100 / total))


def _coerce_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _clamp_progress(value: Any) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        numeric = 0
    return max(0, min(numeric, 100))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
