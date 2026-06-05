# EN: Output agent for rendering chat orchestration results.

from typing import Any

from app.schemas.chat import ChatActionType, ChatCommandType, ChatState
from app.schemas.io_agent import (
    OutputAgentRequest,
    OutputAgentResponse,
    OutputResponseType,
)


class ChatOutputAgent:
    """Converts chat result JSON into assistant-facing message payloads."""

    AGENT_NAME = "ChatOutputAgent"

    async def render(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.response_type != OutputResponseType.CHAT_RESPONSE:
            return OutputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                message="unsupported response type",
                error="unsupported response type",
            )

        display_payload = self._build_display_payload(request.result_json)
        return OutputAgentResponse(
            agent_name=self.AGENT_NAME,
            message=display_payload["message"],
            display_payload=display_payload,
            artifact_refs=display_payload.get("artifact_refs", []),
        )

    def _build_display_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        event = result_json.get("event")
        if event == "CONFIRMATION_REQUIRED":
            return self._confirmation_payload(result_json)
        if event == "ACTION_COMPLETED":
            return self._completed_payload(result_json)
        if event == "ACTION_FAILED":
            return self._failed_payload(result_json)
        if event == "ACTION_CANCELLED":
            return {
                "state": ChatState.IDLE.value,
                "message": "요청을 취소했습니다.",
                "suggested_actions": [],
            }
        if event == "REQUIRED_INFO":
            return {
                "state": ChatState.WAITING_REQUIRED_INFO.value,
                "message": "생성을 진행하려면 기준이 될 문서를 먼저 선택해 주세요.",
                "suggested_actions": [],
            }

        return {
            "state": ChatState.IDLE.value,
            "message": (
                "현재는 프로젝트 문서 생성과 회의록 기반 할 일 추출 요청을 "
                "도와드릴 수 있습니다."
            ),
            "suggested_actions": [],
        }

    def _confirmation_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        action = result_json.get("pending_action") or {}
        action_type = action.get("action_type")
        payload = action.get("payload") or {}
        artifact_label = self._artifact_label(payload.get("target_artifact_type"))
        if action_type == ChatActionType.EXTRACT_ACTION_ITEMS.value:
            message = "회의 내용을 기준으로 할 일 목록을 추출해드릴까요?"
        else:
            source_ids = payload.get("source_document_ids") or []
            source_text = ", ".join(source_ids) if source_ids else "선택된 문서"
            message = f"{source_text} 기준으로 {artifact_label} 문서를 생성해드릴까요?"

        return {
            "state": ChatState.WAITING_CONFIRMATION.value,
            "message": message,
            "pending_action": action,
            "suggested_actions": [
                {
                    "type": ChatCommandType.CONFIRM_PENDING_ACTION.value,
                    "label": "생성하기",
                    "payload": {"action_id": action.get("action_id")},
                },
                {
                    "type": ChatCommandType.CANCEL_PENDING_ACTION.value,
                    "label": "취소",
                    "payload": {"action_id": action.get("action_id")},
                },
            ],
        }

    def _completed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        generation_result = result_json.get("result") or {}
        artifact = generation_result.get("artifact") or {}
        artifact_id = artifact.get("artifact_id")
        if artifact_id:
            message = f"문서를 생성했습니다. 생성된 산출물은 {artifact_id}입니다."
        else:
            message = "요청한 작업을 완료했습니다."

        return {
            "state": ChatState.COMPLETED.value,
            "message": message,
            "result": generation_result,
            "artifact_refs": [artifact] if artifact else [],
            "suggested_actions": [],
        }

    def _failed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        error = result_json.get("error") or "요청 처리에 실패했습니다."
        return {
            "state": ChatState.FAILED.value,
            "message": f"요청을 처리하지 못했습니다. {error}",
            "result": result_json.get("result") or {},
            "suggested_actions": [],
        }

    def _artifact_label(self, artifact_type: str | None) -> str:
        labels = {
            "REQUIREMENT_SPEC": "요구사항 명세",
            "WBS": "WBS",
            "SCREEN_DESIGN": "화면 설계",
        }
        return labels.get(artifact_type or "", "산출물")


chat_output_agent = ChatOutputAgent()
