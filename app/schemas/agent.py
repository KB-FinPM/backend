"""Common request and response envelopes for all agents."""

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AgentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    documents: list[dict] = Field(
        default_factory=list,
        description="Retrieved RAG/document chunks",
    )
    context: Optional[dict] = Field(
        None,
        description="Additional JSON-serializable context",
    )

    @field_validator("context")
    @classmethod
    def validate_json_serializable_context(cls, value):
        if value is None:
            return value
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("context must be JSON-serializable") from exc
        return value


class AgentResponse(BaseModel):
    success: bool = True
    agent_name: str = Field(..., description="Agent name")
    result: Any = Field(None, description="Agent result JSON")
    error: Optional[str] = None
