# EN: Input agent for converting natural chat text into structured intent JSON.

from typing import Any

from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.chat import ChatCommandType
from app.schemas.io_agent import (
    InputAgentRequest,
    InputAgentResponse,
    InputType,
    NormalizedRequestType,
)


class ChatInputAgent:
    """Maps natural PM chat text to stable internal intents and slots."""

    AGENT_NAME = "ChatInputAgent"

    async def parse(self, request: InputAgentRequest) -> InputAgentResponse:
        if request.input_type != InputType.TEXT:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
                error="text input is required",
                validation_errors=["text input is required"],
            )

        message = str(request.raw_payload.get("message") or "").strip()
        action = request.raw_payload.get("action") or {}
        if not message and not action:
            return InputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
                error="message is required",
                validation_errors=["message is required"],
            )

        structured_context = self._build_structured_context(
            message=message,
            action=action,
            request_context=request.context,
        )
        return InputAgentResponse(
            agent_name=self.AGENT_NAME,
            normalized_request_type=NormalizedRequestType.CHAT_MESSAGE,
            structured_context={
                **structured_context,
                "raw_message": message,
                "permission_scope": request.permission_scope,
                "user_id": request.user_id,
            },
        )

    def _build_structured_context(
        self,
        *,
        message: str,
        action: dict[str, Any],
        request_context: dict[str, Any],
    ) -> dict[str, Any]:
        action_type = action.get("type")
        if action_type == ChatCommandType.CONFIRM_PENDING_ACTION.value:
            return {
                "intent": "CONFIRM_PENDING_ACTION",
                "action_id": action.get("action_id")
                or action.get("payload", {}).get("action_id"),
                "confidence": 1.0,
            }
        if action_type == ChatCommandType.CANCEL_PENDING_ACTION.value:
            return {
                "intent": "CANCEL_PENDING_ACTION",
                "action_id": action.get("action_id")
                or action.get("payload", {}).get("action_id"),
                "confidence": 1.0,
            }

        normalized = message.lower()
        if self._looks_like_confirmation(normalized):
            return {"intent": "CONFIRM_PENDING_ACTION", "confidence": 0.85}
        if self._looks_like_cancellation(normalized):
            return {"intent": "CANCEL_PENDING_ACTION", "confidence": 0.85}

        source_document_ids = self._extract_source_document_ids(request_context)
        source_document_type = request_context.get("source_document_type")
        if "wbs" in normalized:
            return self._artifact_intent(
                target_artifact_type=ArtifactType.WBS,
                source_document_ids=source_document_ids,
                source_document_type=(
                    source_document_type or DocumentType.REQUIREMENT_SPEC.value
                ),
                confidence=0.9,
            )

        if any(token in normalized for token in ("screen", "화면", "ui", "design")):
            return self._artifact_intent(
                target_artifact_type=ArtifactType.SCREEN_DESIGN,
                source_document_ids=source_document_ids,
                source_document_type=(
                    source_document_type or DocumentType.REQUIREMENT_SPEC.value
                ),
                confidence=0.86,
            )

        if any(token in normalized for token in ("요구사항", "requirement", "명세")):
            return self._artifact_intent(
                target_artifact_type=ArtifactType.REQUIREMENT_SPEC,
                source_document_ids=source_document_ids,
                source_document_type=source_document_type,
                confidence=0.82,
            )

        if any(token in normalized for token in ("action item", "todo", "할 일", "회의")):
            return {
                "intent": "EXTRACT_ACTION_ITEMS",
                "source_document_ids": source_document_ids,
                "meeting_notes": message,
                "confidence": 0.78,
            }

        return {
            "intent": "GENERAL_QA",
            "confidence": 0.5,
        }

    def _artifact_intent(
        self,
        *,
        target_artifact_type: ArtifactType,
        source_document_ids: list[str],
        source_document_type: str | None,
        confidence: float,
    ) -> dict[str, Any]:
        return {
            "intent": "GENERATE_ARTIFACT",
            "target_artifact_type": target_artifact_type.value,
            "source_document_ids": source_document_ids,
            "source_document_type": source_document_type,
            "confidence": confidence,
        }

    def _extract_source_document_ids(self, context: dict[str, Any]) -> list[str]:
        raw_ids = (
            context.get("source_document_ids")
            or context.get("selected_document_ids")
            or context.get("document_ids")
            or []
        )
        if isinstance(raw_ids, str):
            return [raw_ids]
        if isinstance(raw_ids, list):
            return [str(document_id) for document_id in raw_ids if document_id]
        return []

    def _looks_like_confirmation(self, normalized_message: str) -> bool:
        compact_message = "".join(normalized_message.split())
        confirmation_tokens = {
            "응",
            "네",
            "예",
            "좋아",
            "진행",
            "생성",
            "확인",
            "yes",
            "ok",
            "confirm",
            "생성해",
            "진행해",
            "계속",
        }
        return compact_message in confirmation_tokens

    def _looks_like_cancellation(self, normalized_message: str) -> bool:
        compact_message = "".join(normalized_message.split())
        cancellation_tokens = {"아니", "취소", "그만", "no", "cancel"}
        return compact_message in cancellation_tokens


chat_input_agent = ChatInputAgent()
