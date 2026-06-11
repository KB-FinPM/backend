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
    GENERATION_TOKENS = (
        "만들",
        "생성",
        "작성",
        "뽑",
        "추출",
        "정리",
    )
    QUESTION_TOKENS = (
        "뭐야",
        "무엇",
        "뭔지",
        "어떤문서",
        "어떤 문서",
        "설명",
        "알려줘",
    )
    REQUIREMENT_TERMS = (
        "요구사항정의서",
        "요구사항 정의서",
        "요구사항명세서",
        "요구사항 명세서",
        "requirement",
        "명세서",
    )
    CONSTRUCTION_REQUIREMENT_TERMS = (
        "구축요건정의서",
        "구축요건 정의서",
        "rfp",
    )
    WBS_TERMS = ("wbs", "일정표", "작업계획", "작업 계획")
    SCREEN_DESIGN_TERMS = (
        "화면설계서",
        "화면 설계서",
        "화면설계",
        "화면 설계",
        "screen",
        "ui",
    )
    MEETING_TERMS = ("회의록", "회의 내용", "회의내용", "미팅 내용", "미팅내용")
    TODO_TERMS = ("할 일", "할일", "todo", "액션아이템", "action item")

    KOREAN_MEETING_TERMS = ("회의록", "회의 내용", "회의내용", "미팅 내용", "미팅내용")
    KOREAN_TODO_TERMS = ("할 일", "할일", "todo", "TODO", "액션아이템", "action item")
    TODO_TRIGGER_PHRASES = (
        "하기로 함",
        "까지 작성",
        "검토 필요",
        "담당",
        "다음 회의 전까지",
        "추후 확인",
        "보완 필요",
        "개발 필요",
        "테스트 필요",
        "공유 예정",
    )
    TODO_COMPLETION_TERMS = ("완료했어", "완료했습니다", "끝냈어", "처리했어", "done")

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
        compact_message = "".join(normalized.split())
        if self._looks_like_confirmation(normalized):
            return {"intent": "CONFIRM_PENDING_ACTION", "confidence": 0.85}
        if self._looks_like_cancellation(normalized):
            return {"intent": "CANCEL_PENDING_ACTION", "confidence": 0.85}
        if self._looks_like_todo_completion(normalized, compact_message):
            return {
                "intent": "COMPLETE_TODO",
                "todo_title_query": self._todo_completion_query(message),
                "confidence": 0.84,
            }

        source_document_ids = self._extract_source_document_ids(request_context)
        source_document_type = request_context.get("source_document_type")
        topic = self._detect_pm_topic(normalized, compact_message)
        if topic and self._looks_like_question(normalized, compact_message):
            return {
                "intent": "GENERAL_QA",
                "topic": topic,
                "confidence": 0.78,
            }

        if self._looks_like_todo_extraction(normalized, compact_message):
            return {
                "intent": "EXTRACT_ACTION_ITEMS",
                "source_document_ids": source_document_ids,
                "meeting_notes": message,
                "confidence": 0.84,
            }

        target_artifact_type = self._detect_artifact_target(
            normalized,
            compact_message,
        )
        if target_artifact_type and self._has_generation_signal(
            normalized,
            compact_message,
        ):
            default_source_document_type = None
            if target_artifact_type in {
                ArtifactType.WBS,
                ArtifactType.SCREEN_DESIGN,
            }:
                default_source_document_type = DocumentType.REQUIREMENT_SPEC.value
            elif self._contains_any(
                normalized,
                compact_message,
                self.CONSTRUCTION_REQUIREMENT_TERMS,
            ):
                default_source_document_type = (
                    DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value
                )

            return self._artifact_intent(
                target_artifact_type=target_artifact_type,
                source_document_ids=source_document_ids,
                source_document_type=(
                    source_document_type or default_source_document_type
                ),
                confidence=0.9,
            )

        if topic:
            return {
                "intent": "GENERAL_QA",
                "topic": topic,
                "confidence": 0.58,
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
            "required_source_document_types": self._required_source_document_types(
                target_artifact_type
            ),
            "confidence": confidence,
        }

    def _detect_artifact_target(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> ArtifactType | None:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.WBS_TERMS,
        ):
            return ArtifactType.WBS
        if self._contains_any(
            normalized_message,
            compact_message,
            self.SCREEN_DESIGN_TERMS,
        ):
            return ArtifactType.SCREEN_DESIGN
        if self._contains_any(
            normalized_message,
            compact_message,
            self.REQUIREMENT_TERMS,
        ):
            return ArtifactType.REQUIREMENT_SPEC
        return None

    def _detect_pm_topic(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> str | None:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.CONSTRUCTION_REQUIREMENT_TERMS,
        ):
            return DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value
        artifact_type = self._detect_artifact_target(
            normalized_message,
            compact_message,
        )
        if artifact_type is not None:
            return artifact_type.value
        if self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS,
        ):
            return "ACTION_ITEMS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.MEETING_TERMS,
        ):
            return "MEETING_NOTES"
        return None

    def _looks_like_question(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        has_generation_signal = self._has_generation_signal(
            normalized_message,
            compact_message,
        )
        if "?" in normalized_message and not has_generation_signal:
            return True
        return self._contains_any(
            normalized_message,
            compact_message,
            self.QUESTION_TOKENS,
        ) and not has_generation_signal

    def _looks_like_todo_extraction(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        has_meeting_source = self._contains_any(
            normalized_message,
            compact_message,
            self.MEETING_TERMS,
        ) or self._contains_any(
            normalized_message,
            compact_message,
            self.KOREAN_MEETING_TERMS,
        )
        has_todo_target = self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS,
        ) or self._contains_any(
            normalized_message,
            compact_message,
            self.KOREAN_TODO_TERMS,
        )
        has_todo_trigger = self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TRIGGER_PHRASES,
        )
        return (has_todo_target or has_todo_trigger) and (
            has_meeting_source
            or self._has_generation_signal(normalized_message, compact_message)
            or has_todo_trigger
        )

    def _looks_like_todo_completion(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        return self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_COMPLETION_TERMS,
        )

    def _todo_completion_query(self, message: str) -> str:
        query = message
        for term in self.TODO_COMPLETION_TERMS:
            query = query.replace(term, "")
        return query.strip(" .。!！")

    def _has_generation_signal(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        return self._contains_any(
            normalized_message,
            compact_message,
            self.GENERATION_TOKENS,
        )

    def _contains_any(
        self,
        normalized_message: str,
        compact_message: str,
        terms: tuple[str, ...],
    ) -> bool:
        for term in terms:
            normalized_term = term.lower()
            if normalized_term in normalized_message:
                return True
            if "".join(normalized_term.split()) in compact_message:
                return True
        return False

    def _required_source_document_types(
        self,
        target_artifact_type: ArtifactType,
    ) -> list[str]:
        if target_artifact_type == ArtifactType.REQUIREMENT_SPEC:
            return [DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value, "RFP"]
        if target_artifact_type in {
            ArtifactType.WBS,
            ArtifactType.SCREEN_DESIGN,
        }:
            return [DocumentType.REQUIREMENT_SPEC.value]
        return []

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
