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
        "만드",
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
        "차이",
        "언제",
        "어떻게",
        "어떤문서",
        "어떤 문서",
        "어떤 항목",
        "설명",
        "알려줘",
    )
    REQUIREMENT_TERMS = (
        "요구사항정의서",
        "요구사항 정의서",
        "요구사항명세서",
        "요구사항 명세서",
        "요구사항",
        "요구 사항",
        "요건정의서",
        "요건 정의서",
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
        "화면기획서",
        "화면 기획서",
        "화면설계",
        "화면 설계",
        "screen",
        "ui",
    )
    UNIT_TEST_TERMS = (
        "단위테스트케이스",
        "단위 테스트 케이스",
        "테스트케이스",
        "테스트 케이스",
        "unit test",
    )
    MEETING_TERMS = (
        "회의록",
        "회의 내용",
        "회의내용",
        "미팅 내용",
        "미팅내용",
        "주간회의",
        "주간 회의",
    )
    TODO_TERMS = ("할 일", "할일", "todo", "액션아이템", "action item")

    KOREAN_MEETING_TERMS = ("회의록", "회의 내용", "회의내용", "미팅 내용", "미팅내용")
    KOREAN_TODO_TERMS = ("할 일", "할일", "todo", "TODO", "액션아이템", "action item")
    TODO_TRIGGER_PHRASES = (
        "하기로 함",
        "하기로 했",
        "하기로 했습니다",
        "하기로했습니다",
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
    THIS_WEEK_TERMS = ("이번 주", "이번주", "금주")
    NEXT_WEEK_TERMS = ("다음 주", "다음주", "차주")
    LAST_WEEK_TERMS = ("지난 주", "지난주", "전주")
    TODAY_TERMS = ("오늘", "금일")
    CURRENT_WEEK_TERMS = ("몇 주차", "몇주차", "현재 주차", "지금 프로젝트")
    OVERDUE_TERMS = ("기한 지난", "지연", "overdue")
    BRIEFING_TERMS = ("브리핑", "보고", "정리", "요약")
    COMPARISON_TERMS = ("비교", "달라진", "변경사항", "변경 사항")

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

        normalized_query = self._normalize_query(message)
        normalized = normalized_query.lower()
        compact_message = "".join(normalized.split())
        if self._looks_like_confirmation(normalized):
            return {
                "intent": "CONFIRM_PENDING_ACTION",
                "action": "CONFIRM",
                "normalized_query": normalized_query,
                "confidence": 0.85,
            }
        if self._looks_like_cancellation(normalized):
            return {
                "intent": "CANCEL_PENDING_ACTION",
                "action": "CANCEL",
                "normalized_query": normalized_query,
                "confidence": 0.85,
            }

        schedule_action = self._detect_schedule_action(normalized, compact_message)
        if schedule_action == "COMPLETE_TODO":
            todo_title_query = self._todo_completion_query(message)
            return {
                "intent": "COMPLETE_TODO",
                "action": "UPDATE",
                "schedule_action": "COMPLETE_TODO",
                "todo_title_query": todo_title_query,
                "entities": {"todo_title": todo_title_query},
                "normalized_query": normalized_query,
                "confidence": 0.84,
            }

        source_document_ids = self._extract_source_document_ids(request_context)
        source_document_type = request_context.get("source_document_type")
        if schedule_action == "EXTRACT_TODOS_FROM_MEETING":
            missing_slots = [] if self._has_embedded_meeting_notes(message) else [
                "meeting_notes"
            ]
            return {
                "intent": "EXTRACT_ACTION_ITEMS",
                "action": "CREATE",
                "schedule_action": "EXTRACT_TODOS_FROM_MEETING",
                "schedule_intent": "SCHEDULE_ASSISTANT",
                "source_document_ids": source_document_ids,
                "meeting_notes": message,
                "required_slots": ["meeting_notes"],
                "missing_slots": missing_slots,
                "needs_context": ["MEETING_NOTES", "TODO_LIST"],
                "entities": self._schedule_entities(message, schedule_action),
                "normalized_query": normalized_query,
                "confidence": 0.84,
            }

        if schedule_action:
            return {
                "intent": "SCHEDULE_QUERY",
                "action": "QUERY",
                "schedule_action": schedule_action,
                "schedule_intent": "SCHEDULE_ASSISTANT",
                "needs_context": self._schedule_needs_context(schedule_action),
                "required_slots": [],
                "missing_slots": [],
                "entities": self._schedule_entities(message, schedule_action),
                "normalized_query": normalized_query,
                "confidence": 0.82,
            }

        topic = self._detect_pm_topic(normalized, compact_message)
        if topic and self._looks_like_question(normalized, compact_message):
            return {
                "intent": "GENERAL_QA",
                "action": "EXPLAIN",
                "topic": topic,
                "qa_type": "ASK_PM_CONCEPT",
                "normalized_query": normalized_query,
                "confidence": 0.78,
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
                ArtifactType.UNITTEST_SPEC,
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
                normalized_query=normalized_query,
                confidence=0.9,
            )

        if topic:
            return {
                "intent": "GENERAL_QA",
                "action": "EXPLAIN",
                "topic": topic,
                "qa_type": "ASK_PM_CONCEPT",
                "normalized_query": normalized_query,
                "confidence": 0.58,
            }

        return {
            "intent": "GENERAL_QA",
            "action": "EXPLAIN",
            "normalized_query": normalized_query,
            "confidence": 0.5,
        }

    def _artifact_intent(
        self,
        *,
        target_artifact_type: ArtifactType,
        source_document_ids: list[str],
        source_document_type: str | None,
        normalized_query: str,
        confidence: float,
    ) -> dict[str, Any]:
        required_slots = ["source_document_ids"]
        missing_slots = [] if source_document_ids else ["source_document_ids"]
        return {
            "intent": "GENERATE_ARTIFACT",
            "action": "CREATE",
            "artifact_type": target_artifact_type.value,
            "target_artifact_type": target_artifact_type.value,
            "source_document_ids": source_document_ids,
            "source_document_type": source_document_type,
            "required_source_document_types": self._required_source_document_types(
                target_artifact_type
            ),
            "required_slots": required_slots,
            "missing_slots": missing_slots,
            "schedule_action": None,
            "normalized_query": normalized_query,
            "entities": {},
            "recommended_commands": self._recommended_commands_for_artifact(
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
            self.UNIT_TEST_TERMS,
        ):
            return ArtifactType.UNITTEST_SPEC
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
        strong_question_tokens = ("뭐야", "뭘", "차이", "언제", "어떤항목", "다음에는")
        if self._contains_any(
            normalized_message,
            compact_message,
            strong_question_tokens,
        ):
            return True
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

    def _detect_schedule_action(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> str | None:
        if self._looks_like_todo_completion(normalized_message, compact_message):
            return "COMPLETE_TODO"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.OVERDUE_TERMS,
        ):
            return "SHOW_OVERDUE_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.COMPARISON_TERMS,
        ) and (
            self._contains_any(normalized_message, compact_message, self.MEETING_TERMS)
            or self._contains_any(normalized_message, compact_message, self.TODO_TERMS)
        ):
            return "COMPARE_WEEKLY_MEETING_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.CURRENT_WEEK_TERMS,
        ):
            return "SHOW_CURRENT_WEEK"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.TODAY_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS + ("업무", "챙길", "해야"),
        ):
            return "SHOW_TODAY_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.NEXT_WEEK_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS + ("업무", "해야", "일정", "뭐"),
        ):
            return "SHOW_NEXT_WEEK_TODOS"
        if (
            ("이번주" in compact_message or "금주" in compact_message)
            and (
                "todo" in compact_message
                or "해야" in compact_message
                or "업무" in compact_message
                or "일정" in compact_message
            )
        ):
            return "SHOW_THIS_WEEK_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.THIS_WEEK_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS + ("업무", "해야", "일정"),
        ):
            return "SHOW_THIS_WEEK_TODOS"
        if self._looks_like_assignee_todo_query(normalized_message, compact_message):
            return "SHOW_ASSIGNEE_TODOS"
        if (
            self._contains_any(normalized_message, compact_message, self.WBS_TERMS)
            and self._contains_any(
                normalized_message,
                compact_message,
                self.BRIEFING_TERMS + ("일정", "해야", "할일"),
            )
            and not self._has_generation_signal(normalized_message, compact_message)
        ):
            return "ASSISTANT_BRIEFING"
        if self._looks_like_todo_extraction(normalized_message, compact_message):
            return "EXTRACT_TODOS_FROM_MEETING"
        return None

    def _schedule_entities(
        self,
        message: str,
        schedule_action: str,
    ) -> dict[str, Any]:
        if schedule_action == "COMPLETE_TODO":
            return {"todo_title": self._todo_completion_query(message)}
        normalized = self._normalize_query(message).lower()
        compact_message = "".join(normalized.split())
        entities: dict[str, Any] = {}
        if schedule_action in {"SHOW_THIS_WEEK_TODOS", "ASSISTANT_BRIEFING"}:
            entities["time_range"] = "THIS_WEEK"
        elif schedule_action == "SHOW_NEXT_WEEK_TODOS":
            entities["time_range"] = "NEXT_WEEK"
        elif schedule_action == "SHOW_TODAY_TODOS":
            entities["time_range"] = "TODAY"
        elif self._contains_any(normalized, compact_message, self.LAST_WEEK_TERMS):
            entities["time_range"] = "LAST_WEEK"
        if self._contains_any(normalized, compact_message, self.WBS_TERMS):
            entities["source"] = "WBS"
        if self._contains_any(normalized, compact_message, self.MEETING_TERMS):
            entities["source"] = "MEETING_NOTES"
        assignee = self._extract_assignee_query(message)
        if assignee:
            entities["assignee"] = assignee
        return entities

    def _schedule_needs_context(self, schedule_action: str) -> list[str]:
        if schedule_action == "EXTRACT_TODOS_FROM_MEETING":
            return ["MEETING_NOTES", "TODO_LIST"]
        if schedule_action in {
            "SHOW_CURRENT_WEEK",
            "SHOW_THIS_WEEK_TODOS",
            "SHOW_NEXT_WEEK_TODOS",
            "SHOW_TODAY_TODOS",
            "ASSISTANT_BRIEFING",
        }:
            return ["WBS", "MEETING_NOTES", "TODO_LIST"]
        if schedule_action == "COMPARE_WEEKLY_MEETING_TODOS":
            return ["MEETING_NOTES", "TODO_LIST"]
        return ["TODO_LIST"]

    def _looks_like_assignee_todo_query(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        return self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS + ("업무",),
        ) and self._contains_any(
            normalized_message,
            compact_message,
            ("남았", "남은", "담당", "뭐"),
        )

    def _extract_assignee_query(self, message: str) -> str | None:
        compact = str(message or "").strip()
        for suffix in ("할 일", "할일", "업무", "TODO", "todo"):
            marker_index = compact.find(suffix)
            if marker_index > 0:
                candidate = compact[:marker_index].strip(" 은는이가의,")
                if 1 < len(candidate) <= 30 and " " not in candidate:
                    return candidate
        return None

    def _has_embedded_meeting_notes(self, message: str) -> bool:
        text = str(message or "").strip()
        if ":" in text or "：" in text:
            return True
        return self._contains_any(
            self._normalize_query(text).lower(),
            "".join(self._normalize_query(text).lower().split()),
            self.TODO_TRIGGER_PHRASES,
        )

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
        if target_artifact_type == ArtifactType.UNITTEST_SPEC:
            return [DocumentType.REQUIREMENT_SPEC.value, "SCREEN_DESIGN"]
        return []

    def _recommended_commands_for_artifact(
        self,
        target_artifact_type: ArtifactType,
    ) -> list[dict[str, str]]:
        if target_artifact_type == ArtifactType.REQUIREMENT_SPEC:
            return [
                {
                    "label": "WBS 생성",
                    "command": "요구사항 정의서를 기준으로 WBS 생성해줘",
                    "reason": "요구사항 정의서 다음 단계",
                },
                {
                    "label": "화면설계서 생성",
                    "command": "요구사항 정의서를 기준으로 화면설계서 생성해줘",
                    "reason": "요구사항 기반 후속 산출물",
                },
            ]
        return []

    def _normalize_query(self, message: str) -> str:
        normalized = str(message or "").strip()
        replacements = (
            ("요구 사항", "요구사항"),
            ("요구사항정의서", "요구사항 정의서"),
            ("요구사항명세서", "요구사항 명세서"),
            ("구축 요건 정의서", "구축요건 정의서"),
            ("구축요건정의서", "구축요건 정의서"),
            ("요건정의서", "구축요건 정의서"),
            ("화면 설계서", "화면설계서"),
            ("화면기획서", "화면설계서"),
            ("단위 테스트 케이스", "단위테스트케이스"),
            ("테스트케이스", "단위테스트케이스"),
            ("회의록 할일", "회의록 TODO"),
            ("할 일", "TODO"),
            ("할일", "TODO"),
        )
        for source, target in replacements:
            normalized = normalized.replace(source, target)
        return " ".join(normalized.split())

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
            "만들어줘",
            "진행해",
            "계속",
            "오케이",
        }
        return compact_message in confirmation_tokens

    def _looks_like_cancellation(self, normalized_message: str) -> bool:
        compact_message = "".join(normalized_message.split())
        cancellation_tokens = {
            "아니",
            "취소",
            "그만",
            "하지마",
            "중단",
            "생성하지마",
            "no",
            "cancel",
        }
        return compact_message in cancellation_tokens


chat_input_agent = ChatInputAgent()
