# EN: Tests for minimal schedule todo schema contracts.
# KO: 일정관리 todo 최소 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.schedule import ScheduleTodoList


def test_schedule_todo_list_accepts_minimal_todo_payload() -> None:
    todo_list = ScheduleTodoList.model_validate(
        {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "todos": [
                {
                    "todo_id": "TODO-001",
                    "title": "Confirm login scope",
                    "source_chunk_ids": ["CHUNK-001"],
                }
            ],
        }
    )

    assert todo_list.todos[0].todo_id == "TODO-001"
    assert todo_list.todos[0].metadata == {}


def test_schedule_todo_list_rejects_missing_todo_id() -> None:
    with pytest.raises(ValidationError):
        ScheduleTodoList.model_validate(
            {
                "artifact_type": "SCHEDULE_TODO_LIST",
                "todos": [{"title": "Confirm login scope"}],
            }
        )
