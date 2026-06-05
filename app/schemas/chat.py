# EN: Chat request, response, conversation, and pending action contracts.

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.response import BaseResponse


class ChatRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    TOOL = "TOOL"


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChatActionType(StrEnum):
    GENERATE_REQUIREMENT = "GENERATE_REQUIREMENT"
    GENERATE_WBS = "GENERATE_WBS"
    GENERATE_SCREEN_DESIGN = "GENERATE_SCREEN_DESIGN"
    EXTRACT_ACTION_ITEMS = "EXTRACT_ACTION_ITEMS"


class ChatActionStatus(StrEnum):
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ChatCommandType(StrEnum):
    CONFIRM_PENDING_ACTION = "CONFIRM_PENDING_ACTION"
    CANCEL_PENDING_ACTION = "CANCEL_PENDING_ACTION"


class ChatState(StrEnum):
    IDLE = "IDLE"
    WAITING_REQUIRED_INFO = "WAITING_REQUIRED_INFO"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTING_ACTION = "EXECUTING_ACTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChatActionCommand(BaseModel):
    type: ChatCommandType = Field(..., description="Command selected by the user")
    action_id: str | None = Field(None, description="Pending action to execute")
    payload: dict[str, Any] = Field(default_factory=dict, description="Command payload")


class ChatMessageRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    user_id: str | None = Field(None, description="Requesting user ID")
    message: str = Field(..., min_length=1, description="User chat message")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="UI and project context such as selected documents",
    )
    action: ChatActionCommand | None = Field(
        None,
        description="Optional explicit UI command for pending chat actions",
    )
    permission_scope: list[str] = Field(
        default_factory=lambda: ["project:read"],
        description="Permission scope used by downstream services",
    )


class ChatSuggestedAction(BaseModel):
    type: ChatCommandType = Field(..., description="Suggested command type")
    label: str = Field(..., description="Button label")
    payload: dict[str, Any] = Field(default_factory=dict, description="Command payload")


class ConversationMetadata(BaseModel):
    conversation_id: str
    project_id: str
    user_id: str | None = None
    title: str | None = None
    status: ConversationStatus = ConversationStatus.ACTIVE


class ChatMessageMetadata(BaseModel):
    message_id: str
    conversation_id: str
    project_id: str
    role: ChatRole
    content: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class ChatActionMetadata(BaseModel):
    action_id: str
    conversation_id: str
    project_id: str
    action_type: ChatActionType
    status: ChatActionStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseResponse):
    conversation_id: str
    message_id: str | None = Field(None, description="Assistant message ID")
    state: ChatState = ChatState.IDLE
    pending_action: ChatActionMetadata | None = None
    suggested_actions: list[ChatSuggestedAction] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
