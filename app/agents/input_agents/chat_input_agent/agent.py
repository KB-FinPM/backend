# EN: Input agent for converting natural chat text into structured intent JSON.

import re
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
    """Semantic parser for PM chat text.

    This agent only returns normalized intent/slot data. It must not call
    generation, schedule, validation, or output agents; orchestration and
    downstream agent selection belong to the PM orchestrator.
    """

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
    WBS_TERMS = (
        "wbs",
        "일정표",
        "일정관리",
        "작업계획",
        "작업 계획",
        "작업일정",
        "작업 일정",
        "업무일정",
        "작업분해도",
    )
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
        "단위테스트계획서",
        "단위 테스트 계획서",
        "단위테스트 계획서",
        "테스트계획서",
        "테스트 계획서",
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
        "미팅록",
        "미팅 메모",
        "회의 메모",
        "회의 결과",
        "회의결과",
        "주간회의",
        "주간 회의",
    )
    TODO_TERMS = (
        "할 일",
        "할일",
        "해야 할 일",
        "해야할일",
        "todo",
        "to-do",
        "to do",
        "액션아이템",
        "액션 아이템",
        "action item",
        "후속작업",
        "후속 작업",
        "체크리스트",
    )

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
    TODO_COMPLETION_TERMS = (
        "완료했습니다",
        "완료했어요",
        "완료했어",
        "완료함",
        "완료",
        "끝냈습니다",
        "끝냈어요",
        "끝냈어",
        "끝났습니다",
        "끝났어요",
        "끝났어",
        "끝",
        "처리했습니다",
        "처리했어요",
        "처리했어",
        "처리",
        "반영했습니다",
        "반영했어요",
        "반영했어",
        "반영",
        "체크해줘",
        "완료로 바꿔줘",
        "done",
        "complete",
    )
    THIS_WEEK_TERMS = ("이번 주", "이번주", "금주")
    NEXT_WEEK_TERMS = ("다음 주", "다음주", "차주")
    LAST_WEEK_TERMS = ("지난 주", "지난주", "전주")
    TODAY_TERMS = ("오늘", "금일")
    CURRENT_WEEK_TERMS = (
        "몇 주차",
        "몇주차",
        "현재 주차",
        "지금 주차",
        "프로젝트 주차",
        "프로젝트 몇 주차",
        "지금 프로젝트",
        "이번주는 몇 주차",
        "이번 주는 몇 주차",
    )
    OVERDUE_TERMS = ("기한 지난", "지연", "overdue")
    BRIEFING_TERMS = ("브리핑", "보고", "정리", "요약")
    COMPARISON_TERMS = ("비교", "달라진", "변경사항", "변경 사항")
    SHOW_TERMS = ("알려줘", "알려", "보여줘", "보여", "정리해줘", "브리핑", "뭐", "뭐야")
    EXTRACT_TERMS = ("뽑아줘", "추출", "추려줘", "정리해줘", "나눠줘")
    UPLOAD_TERMS = ("업로드", "올려", "첨부", "등록")
    GENERATE_ACTION_TERMS = ("만들", "생성", "작성", "만드")
    LOW_CONFIDENCE_ACTION_TERMS = ("해줘", "알려줘", "보여줘", "정리해줘")

    KO_GENERATION_TERMS = ("만들", "생성", "작성", "뽑", "추출", "정리", "짜")
    KO_QUESTION_TERMS = ("뭐야", "무엇", "차이", "언제", "어떤", "설명")
    KO_REQUIREMENT_TERMS = (
        "요구사항정의서",
        "요구사항 정의서",
        "요구사항저의서",
        "요구사항 저의서",
        "요구사항명세서",
        "요구사항 명세서",
        "요구사항",
        "요건정의서",
        "요건 정의서",
    )
    KO_CONSTRUCTION_REQUIREMENT_TERMS = (
        "구축요건정의서",
        "구축요건 정의서",
        "RFP",
    )
    KO_WBS_TERMS = ("WBS", "wbs", "일정표", "작업계획", "작업 계획")
    KO_SCREEN_DESIGN_TERMS = (
        "화면설계서",
        "화면 설계서",
        "화면설계",
        "화면 설계",
        "UI 설계서",
        "ui 설계서",
    )
    KO_UNIT_TEST_TERMS = (
        "테스트케이스",
        "테스트 케이스",
        "단위테스트",
        "단위 테스트",
        "단위테스트계획서",
    )
    KO_MEETING_TERMS = ("회의록", "회의 내용", "회의내용", "미팅 내용", "미팅내용")
    KO_TODO_TERMS = (
        "할 일",
        "할일",
        "해야 할 일",
        "TODO",
        "todo",
        "액션아이템",
        "액션 아이템",
        "업무",
    )
    KO_COMPLETION_TERMS = ("완료", "완료했어", "완료 처리", "처리해줘")
    KO_THIS_WEEK_TERMS = ("이번 주", "이번주", "금주")
    KO_NEXT_WEEK_TERMS = ("다음 주", "다음주", "차주")
    KO_TODAY_TERMS = ("오늘", "금일")
    KO_OVERDUE_TERMS = ("기한 지난", "지연", "연체")
    KO_SHOW_TERMS = ("알려줘", "보여줘", "보여", "뭐야")
    KO_EXTRACT_TERMS = ("뽑아줘", "추출", "정리", "찾아줘")
    KO_DOWNLOAD_TERMS = ("다운로드", "내려줘", "내려받기", "받아볼래", "파일")
    KO_STATUS_UPDATE_TERMS = ("상태", "진행중", "진행 중", "차단", "보류", "취소", "완료")
    KO_STATUS_UPDATE_ACTION_TERMS = ("바꿔", "변경", "처리", "해줘", "수정")
    KO_LOW_CONFIDENCE_ACTION_TERMS = ("해줘", "만들어줘", "생성해줘", "작성해줘")

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

        slots = self.extract_semantic_slots(message, request_context)
        return self._classify_semantic_intent(
            message=message,
            request_context=request_context,
            slots=slots,
        )

    def normalize_text(self, message: str) -> str:
        text = str(message or "").strip()
        typo_replacements = (
            ("요구사항저의서", "요구사항정의서"),
            ("요구사항 저의서", "요구사항 정의서"),
            ("요구사항저의서", "요구사항정의서"),
            ("요구사항 명새서", "요구사항 명세서"),
            ("요구사항명새서", "요구사항명세서"),
            ("구축요건저의서", "구축요건정의서"),
            ("할릴", "할일"),
            ("뽀바줘", "뽑아줘"),
            ("머해", "뭐해"),
            ("완료햇어", "완료했어"),
            ("끝낫어", "끝났어"),
            ("처리햇어", "처리했어"),
        )
        synonym_replacements = (
            ("To-do", "TODO"),
            ("to-do", "TODO"),
            ("to do", "TODO"),
            ("액션 아이템", "액션아이템"),
            ("후속 작업", "후속작업"),
            ("회의 내용", "회의내용"),
            ("미팅 내용", "미팅내용"),
            ("회의 메모", "회의록"),
            ("미팅 메모", "회의록"),
            ("작업분해도", "WBS"),
            ("작업 일정", "WBS"),
            ("작업일정", "WBS"),
            ("업무일정", "WBS"),
        )
        for source, target in typo_replacements + synonym_replacements:
            text = text.replace(source, target)
        text = re.sub(r"\bwbs\b", "WBS", text, flags=re.IGNORECASE)
        return " ".join(text.split())

    def extract_semantic_slots(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_context = context or {}
        normalized_query = self._normalize_query(self.normalize_text(message))
        normalized = normalized_query.lower()
        compact_message = "".join(normalized.split())
        context_snapshot = self._context_snapshot(request_context)
        large_document_hint = self._large_document_hint(request_context)
        source_type = self._detect_source_type(
            normalized,
            compact_message,
            context_snapshot,
        )
        artifact_target = self._detect_artifact_target(normalized, compact_message)
        action = self._detect_semantic_action(
            normalized,
            compact_message,
            source_type=source_type,
            artifact_target=artifact_target,
            context_snapshot=context_snapshot,
        )
        target_type = self._detect_target_type(
            normalized,
            compact_message,
            action=action,
            artifact_target=artifact_target,
        )
        time_range = self._detect_time_range(normalized, compact_message)
        assignee = self._extract_assignee_query(message)
        todo_target = (
            self._todo_completion_query(normalized_query)
            if action == "COMPLETE"
            else None
        )
        schedule_action = self._schedule_action_from_slots(
            normalized,
            compact_message,
            source_type=source_type,
            target_type=target_type,
            action=action,
            time_range=time_range,
            assignee=assignee,
        )
        artifact_type = artifact_target.value if artifact_target is not None else None
        download_requested = self._looks_like_download_request(
            normalized,
            compact_message,
        )
        download_artifact = self._resolve_download_artifact(
            message=message,
            context=request_context,
            artifact_target=artifact_target,
        )
        export_format = self._detect_export_format(normalized, compact_message)
        confidence = self._semantic_confidence(
            source_type=source_type,
            target_type=target_type,
            action=action,
            artifact_type=artifact_type,
            schedule_action=schedule_action,
            context_snapshot=context_snapshot,
        )
        clarification_required = (
            confidence <= 0.55
            and self._contains_any(
                normalized,
                compact_message,
                self.LOW_CONFIDENCE_ACTION_TERMS + self.KO_LOW_CONFIDENCE_ACTION_TERMS,
            )
        )
        return {
            "normalized_query": normalized_query,
            "normalized": normalized,
            "compact": compact_message,
            "source_type": source_type,
            "target_type": target_type,
            "action": action,
            "time_range": time_range,
            "assignee": assignee,
            "artifact_type": artifact_type,
            "artifact_id": download_artifact.get("artifact_id"),
            "artifact_ref": download_artifact,
            "download_requested": download_requested,
            "export_format": export_format,
            "large_document_hint": large_document_hint,
            "todo_target": todo_target,
            "schedule_action": schedule_action,
            "confidence": confidence,
            "clarification_required": clarification_required,
            "clarification_question": (
                "어떤 문서나 업무를 기준으로 처리할까요?"
                if clarification_required
                else None
            ),
            "context_snapshot": context_snapshot,
        }

    def _classify_semantic_intent(
        self,
        *,
        message: str,
        request_context: dict[str, Any],
        slots: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_query = str(slots.get("normalized_query") or "")
        normalized = str(slots.get("normalized") or "").lower()
        compact_message = str(slots.get("compact") or "")
        semantic_payload = self._semantic_payload(slots)

        if self._looks_like_confirmation(normalized):
            return {
                "intent": "CONFIRM_PENDING_ACTION",
                "action": "CONFIRM",
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": 0.85,
            }
        if self._looks_like_cancellation(normalized):
            return {
                "intent": "CANCEL_PENDING_ACTION",
                "action": "CANCEL",
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": 0.85,
            }

        if slots.get("download_requested"):
            return self._download_intent(
                slots=slots,
                normalized_query=normalized_query,
            )

        if self._looks_like_ambiguous_creation(normalized, compact_message, slots):
            return {
                "intent": "CLARIFICATION_REQUIRED",
                "action": "ASK_CLARIFICATION",
                "normalized_query": normalized_query,
                "clarification_required": True,
                "clarification_question": "어떤 산출물이나 일정을 처리할까요?",
                **semantic_payload,
                "confidence": float(slots.get("confidence") or 0.45),
            }

        source_document_ids = self._resolve_source_document_ids(
            request_context,
            slots,
        )
        source_type_for_document = slots.get("source_type")
        if (
            slots.get("action") == "GENERATE"
            and source_type_for_document == slots.get("artifact_type")
        ):
            source_type_for_document = None
        source_document_type = (
            request_context.get("source_document_type")
            or self._source_document_type_from_slot(source_type_for_document)
            or self._default_source_document_type(slots.get("artifact_type"))
        )
        schedule_action = slots.get("schedule_action")
        topic = self._detect_pm_topic(normalized, compact_message)

        if (
            topic
            and self._looks_like_question(normalized, compact_message)
            and slots.get("target_type") == "ARTIFACT"
        ):
            return {
                "intent": "GENERAL_QA",
                "action": "EXPLAIN",
                "topic": topic,
                "qa_type": "ASK_PM_CONCEPT",
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.78),
            }

        if schedule_action == "UPDATE_TODO_STATUS":
            target_status = self._detect_requested_status(normalized, compact_message)
            return {
                "intent": "UPDATE_TODO_STATUS",
                "action": "UPDATE",
                "schedule_action": "UPDATE_TODO_STATUS",
                "todo_title_query": str(slots.get("todo_target") or "").strip(),
                "entities": {
                    "status": target_status,
                    **self._slot_entities(slots),
                },
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.84),
            }

        if schedule_action == "COMPLETE_TODO":
            todo_title_query = (
                str(slots.get("todo_target") or "").strip()
                or self._todo_completion_query(message)
            )
            return {
                "intent": "COMPLETE_TODO",
                "action": "UPDATE",
                "schedule_action": "COMPLETE_TODO",
                "todo_title_query": todo_title_query,
                "entities": {
                    "todo_title": todo_title_query,
                    **self._slot_entities(slots),
                },
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.84),
            }

        if schedule_action == "EXTRACT_TODOS_FROM_MEETING":
            has_meeting_context = bool(
                source_document_ids
                or self._has_context_type(slots, "MEETING_NOTES")
                or self._has_embedded_meeting_notes(message)
            )
            missing_slots = [] if has_meeting_context else ["meeting_notes"]
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
                "entities": {
                    **self._schedule_entities(message, schedule_action),
                    **self._slot_entities(slots),
                },
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.84),
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
                "entities": {
                    **self._schedule_entities(message, schedule_action),
                    **self._slot_entities(slots),
                },
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.82),
            }

        target_artifact_type = self._artifact_type_from_slot(slots.get("artifact_type"))
        if target_artifact_type and slots.get("action") == "GENERATE":
            return {
                **self._artifact_intent(
                    target_artifact_type=target_artifact_type,
                    source_document_ids=source_document_ids,
                    source_document_type=source_document_type,
                    normalized_query=normalized_query,
                    confidence=max(float(slots.get("confidence") or 0.0), 0.9),
                ),
                **semantic_payload,
            }

        if topic and self._looks_like_question(normalized, compact_message):
            return {
                "intent": "GENERAL_QA",
                "action": "EXPLAIN",
                "topic": topic,
                "qa_type": "ASK_PM_CONCEPT",
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.78),
            }

        if slots.get("clarification_required"):
            return {
                "intent": "CLARIFICATION_REQUIRED",
                "action": "ASK_CLARIFICATION",
                "normalized_query": normalized_query,
                "clarification_required": True,
                "clarification_question": slots.get("clarification_question"),
                **semantic_payload,
                "confidence": float(slots.get("confidence") or 0.0),
            }

        if topic:
            return {
                "intent": "GENERAL_QA",
                "action": "EXPLAIN",
                "topic": topic,
                "qa_type": "ASK_PM_CONCEPT",
                "normalized_query": normalized_query,
                **semantic_payload,
                "confidence": max(float(slots.get("confidence") or 0.0), 0.58),
            }

        return {
            "intent": "GENERAL_QA",
            "action": "EXPLAIN",
            "normalized_query": normalized_query,
            **semantic_payload,
            "confidence": float(slots.get("confidence") or 0.5),
        }

    def _looks_like_ambiguous_creation(
        self,
        normalized_message: str,
        compact_message: str,
        slots: dict[str, Any],
    ) -> bool:
        if not self._has_generation_signal(normalized_message, compact_message):
            return False
        if slots.get("artifact_type"):
            return False
        if self._contains_any(
            normalized_message,
            compact_message,
            self.AMBIGUOUS_DOCUMENT_TERMS
            if hasattr(self, "AMBIGUOUS_DOCUMENT_TERMS")
            else ("문서", "산출물"),
        ):
            return True
        if (
            self._contains_any(normalized_message, compact_message, ("일정",))
            and not self._contains_any(normalized_message, compact_message, ("일정표",))
        ):
            return True
        return False

    def _detect_source_type(
        self,
        normalized_message: str,
        compact_message: str,
        context_snapshot: dict[str, Any],
    ) -> str | None:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.MEETING_TERMS + self.KO_MEETING_TERMS,
        ):
            return "MEETING_NOTES"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.CONSTRUCTION_REQUIREMENT_TERMS
            + self.KO_CONSTRUCTION_REQUIREMENT_TERMS,
        ):
            return DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value
        if self._contains_any(
            normalized_message,
            compact_message,
            self.WBS_TERMS + self.KO_WBS_TERMS,
        ):
            return DocumentType.WBS.value
        if self._contains_any(
            normalized_message,
            compact_message,
            self.SCREEN_DESIGN_TERMS + self.KO_SCREEN_DESIGN_TERMS,
        ):
            return ArtifactType.SCREEN_DESIGN.value
        if self._contains_any(
            normalized_message,
            compact_message,
            self.REQUIREMENT_TERMS + self.KO_REQUIREMENT_TERMS,
        ):
            return DocumentType.REQUIREMENT_SPEC.value
        if self._contains_any(
            normalized_message,
            compact_message,
            ("업로드한", "올린", "첨부한"),
        ):
            return "UPLOADED_DOCUMENT"
        if self._contains_any(
            normalized_message,
            compact_message,
            ("생성된", "만든", "방금 만든"),
        ):
            return "GENERATED_ARTIFACT"
        if self._contains_any(
            normalized_message,
            compact_message,
            ("이거", "그거", "아까거", "아까 거", "방금", "선택한"),
        ):
            if context_snapshot.get("pending_action"):
                return "PENDING_ACTION"
            if context_snapshot.get("selected_document_ids"):
                return "UPLOADED_DOCUMENT"
            if context_snapshot.get("generated_artifact_types"):
                return "GENERATED_ARTIFACT"
            if context_snapshot.get("last_agent_response_summary"):
                return "LAST_AGENT_RESPONSE"
        return None

    def _detect_target_type(
        self,
        normalized_message: str,
        compact_message: str,
        *,
        action: str | None,
        artifact_target: ArtifactType | None,
    ) -> str | None:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODO_TERMS,
        ):
            return "TODO"
        if self._contains_any(
            normalized_message,
            compact_message,
            ("일정", "마감", "업무", "작업", "주차"),
        ):
            return "SCHEDULE"
        if self._contains_any(normalized_message, compact_message, self.TODO_TERMS):
            return "TODO"
        if self._contains_any(
            normalized_message,
            compact_message,
            ("일정", "스케줄", "마감", "업무", "작업", "주차"),
        ):
            return "SCHEDULE"
        if artifact_target is not None and action == "GENERATE":
            return artifact_target.value
        if artifact_target is not None:
            return "ARTIFACT"
        return None

    def _detect_semantic_action(
        self,
        normalized_message: str,
        compact_message: str,
        *,
        source_type: str | None,
        artifact_target: ArtifactType | None,
        context_snapshot: dict[str, Any],
    ) -> str | None:
        if self._looks_like_status_update(normalized_message, compact_message):
            return "UPDATE_STATUS"
        if self._looks_like_todo_completion(normalized_message, compact_message):
            return "COMPLETE"
        has_todo = self._contains_any(
            normalized_message,
            compact_message,
            self.TODO_TERMS + self.KO_TODO_TERMS,
        )
        has_meeting = source_type == "MEETING_NOTES"
        if has_meeting and has_todo and self._contains_any(
            normalized_message,
            compact_message,
            self.EXTRACT_TERMS
            + self.SHOW_TERMS
            + self.KO_EXTRACT_TERMS
            + self.KO_SHOW_TERMS,
        ):
            return "EXTRACT"
        if artifact_target is not None and self._has_generation_signal(
            normalized_message,
            compact_message,
        ):
            if not self._looks_like_question(normalized_message, compact_message):
                return "GENERATE"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.EXTRACT_TERMS + self.KO_EXTRACT_TERMS,
        ):
            return "EXTRACT"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.SHOW_TERMS + self.KO_SHOW_TERMS,
        ):
            return "SHOW"
        if (
            context_snapshot.get("pending_action")
            and self._contains_any(
                normalized_message,
                compact_message,
                ("진행", "계속", "확인", "해줘"),
            )
        ):
            return "SELECT"
        return None

    def _looks_like_status_update(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        has_status_word = self._contains_any(
            normalized_message,
            compact_message,
            self.KO_STATUS_UPDATE_TERMS,
        )
        has_update_action = self._contains_any(
            normalized_message,
            compact_message,
            self.KO_STATUS_UPDATE_ACTION_TERMS,
        )
        return has_status_word and has_update_action

    def _detect_requested_status(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> str | None:
        status_terms = (
            ("IN_PROGRESS", ("진행중", "진행 중", "in progress")),
            ("DONE", ("완료", "done", "complete")),
            ("BLOCKED", ("차단", "막힘", "보류", "blocked")),
            ("CANCELLED", ("취소", "cancel", "cancelled", "canceled")),
            ("TODO", ("예정", "할 일", "todo")),
        )
        for status, terms in status_terms:
            if self._contains_any(normalized_message, compact_message, terms):
                return status
        return None

    def _detect_time_range(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> str | None:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.OVERDUE_TERMS + self.KO_OVERDUE_TERMS,
        ):
            return "OVERDUE"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.CURRENT_WEEK_TERMS,
        ):
            return "CURRENT_WEEK"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.TODAY_TERMS + self.KO_TODAY_TERMS,
        ):
            return "TODAY"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.NEXT_WEEK_TERMS + self.KO_NEXT_WEEK_TERMS,
        ):
            return "NEXT_WEEK"
        if self._contains_any(normalized_message, compact_message, self.LAST_WEEK_TERMS):
            return "LAST_WEEK"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.THIS_WEEK_TERMS + self.KO_THIS_WEEK_TERMS,
        ):
            return "THIS_WEEK"
        if self._contains_any(
            normalized_message,
            compact_message,
            ("다가오는", "임박", "예정"),
        ):
            return "UPCOMING"
        return None

    def _schedule_action_from_slots(
        self,
        normalized_message: str,
        compact_message: str,
        *,
        source_type: str | None,
        target_type: str | None,
        action: str | None,
        time_range: str | None,
        assignee: str | None,
    ) -> str | None:
        if action == "UPDATE_STATUS":
            return "UPDATE_TODO_STATUS"
        if action == "COMPLETE":
            return "COMPLETE_TODO"
        if (
            source_type == "MEETING_NOTES"
            and target_type == "TODO"
            and action in {"EXTRACT", "SHOW", "GENERATE"}
        ):
            return "EXTRACT_TODOS_FROM_MEETING"
        detected = self._detect_schedule_action(normalized_message, compact_message)
        if detected == "EXTRACT_TODOS_FROM_MEETING" and source_type != "MEETING_NOTES":
            return None
        if detected:
            return detected
        if assignee and target_type in {"TODO", "SCHEDULE"}:
            return "SHOW_ASSIGNEE_TODOS"
        if target_type in {"TODO", "SCHEDULE"} and action == "SHOW":
            if time_range == "TODAY":
                return "SHOW_TODAY_TODOS"
            if time_range == "NEXT_WEEK":
                return "SHOW_NEXT_WEEK_TODOS"
            if time_range == "OVERDUE":
                return "SHOW_OVERDUE_TODOS"
            if time_range == "CURRENT_WEEK":
                return "SHOW_CURRENT_WEEK"
            if time_range in {"THIS_WEEK", None} and source_type == "WBS":
                return "ASSISTANT_BRIEFING"
            if time_range in {"THIS_WEEK", None}:
                return "SHOW_THIS_WEEK_TODOS"
        if target_type in {"TODO", "SCHEDULE"} and action is None:
            if time_range == "TODAY":
                return "SHOW_TODAY_TODOS"
            if time_range == "NEXT_WEEK":
                return "SHOW_NEXT_WEEK_TODOS"
            if time_range == "OVERDUE":
                return "SHOW_OVERDUE_TODOS"
            if time_range == "CURRENT_WEEK":
                return "SHOW_CURRENT_WEEK"
            if source_type == "WBS":
                return "ASSISTANT_BRIEFING"
            return "SHOW_THIS_WEEK_TODOS"
        if source_type == "WBS" and action == "SHOW":
            return "ASSISTANT_BRIEFING"
        return None

    def _semantic_confidence(
        self,
        *,
        source_type: str | None,
        target_type: str | None,
        action: str | None,
        artifact_type: str | None,
        schedule_action: str | None,
        context_snapshot: dict[str, Any],
    ) -> float:
        score = 0.35
        if action:
            score += 0.2
        if source_type:
            score += 0.12
        if target_type:
            score += 0.12
        if artifact_type:
            score += 0.08
        if schedule_action:
            score += 0.16
        if (
            context_snapshot.get("uploaded_document_types")
            or context_snapshot.get("generated_artifact_types")
            or context_snapshot.get("recent_todo_count")
            or context_snapshot.get("pending_action")
            or context_snapshot.get("last_agent_response_summary")
        ):
            score += 0.05
        return min(score, 0.98)

    def _semantic_payload(self, slots: dict[str, Any]) -> dict[str, Any]:
        semantic_slots = {
            "source_type": slots.get("source_type"),
            "target_type": slots.get("target_type"),
            "action": slots.get("action"),
            "time_range": slots.get("time_range"),
            "assignee": slots.get("assignee"),
            "artifact_type": slots.get("artifact_type"),
            "todo_target": slots.get("todo_target"),
            "confidence": slots.get("confidence"),
            "clarification_required": slots.get("clarification_required"),
            "clarification_question": slots.get("clarification_question"),
        }
        return {
            "semantic_slots": semantic_slots,
            "context_snapshot": slots.get("context_snapshot") or {},
            "large_document_hint": slots.get("large_document_hint")
            or {"is_large_document": False},
            "source_type": slots.get("source_type"),
            "target_type": slots.get("target_type"),
            "time_range": slots.get("time_range"),
            "artifact_type_slot": slots.get("artifact_type"),
        }

    def _slot_entities(self, slots: dict[str, Any]) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        if slots.get("source_type"):
            entities["source"] = slots.get("source_type")
        if slots.get("artifact_id"):
            entities["artifact_id"] = slots.get("artifact_id")
        if slots.get("export_format"):
            entities["export_format"] = slots.get("export_format")
        if slots.get("time_range"):
            entities["time_range"] = slots.get("time_range")
        if slots.get("assignee"):
            entities["assignee"] = slots.get("assignee")
        if slots.get("todo_target"):
            entities["todo_title"] = slots.get("todo_target")
        return entities

    def _context_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        uploaded_documents = self._context_items(
            context,
            ("uploaded_documents", "documents", "selected_documents"),
        )
        generated_artifacts = self._context_items(
            context,
            ("generated_artifacts", "artifacts"),
        )
        recent_todos = self._context_items(
            context,
            ("recent_todos", "todos", "current_week_todos"),
        )
        selected_document_ids = self._extract_source_document_ids(context)
        pending_action = context.get("pending_action")
        last_agent_response_summary = context.get("last_agent_response_summary")
        return {
            "current_project_id": context.get("current_project_id")
            or context.get("project_id"),
            "uploaded_document_types": self._context_types(
                uploaded_documents,
                "document_type",
            ),
            "uploaded_document_ids": self._context_ids(
                uploaded_documents,
                ("document_id", "id", "file_id"),
            ),
            "generated_artifact_types": self._context_types(
                generated_artifacts,
                "artifact_type",
            ),
            "generated_artifact_ids": self._context_ids(
                generated_artifacts,
                ("artifact_id", "id"),
            ),
            "recent_todo_count": len(recent_todos),
            "pending_action": self._summarize_pending_action(pending_action),
            "last_agent_response_summary": (
                last_agent_response_summary
                if isinstance(last_agent_response_summary, dict)
                else None
            ),
            "selected_document_ids": selected_document_ids,
        }

    def _context_items(
        self,
        context: dict[str, Any],
        keys: tuple[str, ...],
    ) -> list[Any]:
        for key in keys:
            raw_items = context.get(key)
            if isinstance(raw_items, list):
                return raw_items
        return []

    def _context_types(self, items: list[Any], key: str) -> list[str]:
        types = []
        for item in items:
            value = self._item_value(item, key)
            if value:
                types.append(str(value).upper())
        return types

    def _context_ids(
        self,
        items: list[Any],
        keys: tuple[str, ...],
    ) -> list[str]:
        ids = []
        for item in items:
            for key in keys:
                value = self._item_value(item, key)
                if value:
                    ids.append(str(value))
                    break
        return ids

    def _large_document_hint(self, context: dict[str, Any]) -> dict[str, Any]:
        documents = self._context_items(
            context,
            ("selected_documents", "uploaded_documents", "documents"),
        )
        chunk_counts = [
            self._document_number(
                document,
                (
                    "chunk_count",
                    "chunks_count",
                    "total_chunks",
                    "chunk_total",
                    "estimated_chunk_count",
                ),
            )
            for document in documents
        ]
        file_sizes = [
            self._document_number(
                document,
                ("file_size_bytes", "size_bytes", "file_size", "size"),
            )
            for document in documents
        ]
        chunk_counts = [count for count in chunk_counts if count is not None]
        file_sizes = [size for size in file_sizes if size is not None]
        max_chunk_count = max(chunk_counts) if chunk_counts else None
        max_file_size = max(file_sizes) if file_sizes else None
        is_large_document = bool(
            (max_chunk_count is not None and max_chunk_count >= 200)
            or (max_file_size is not None and max_file_size >= 10 * 1024 * 1024)
        )
        return {
            "is_large_document": is_large_document,
            "chunk_count": max_chunk_count,
            "file_size_bytes": max_file_size,
            "message": (
                "문서가 큰 경우 chunk/batch 처리에 시간이 걸릴 수 있습니다."
                if is_large_document
                else None
            ),
        }

    def _document_number(self, document: Any, keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = self._item_value(document, key)
            if value is None:
                metadata = self._item_value(document, "metadata")
                if isinstance(metadata, dict):
                    value = metadata.get(key)
            try:
                if value is not None and value != "":
                    return int(float(value))
            except (TypeError, ValueError):
                continue
        return None

    def _summarize_pending_action(self, pending_action: Any) -> dict[str, Any] | None:
        if not pending_action:
            return None
        return {
            "action_id": self._item_value(pending_action, "action_id"),
            "action_type": self._item_value(pending_action, "action_type"),
            "status": self._item_value(pending_action, "status"),
        }

    def _item_value(self, item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _has_context_type(self, slots: dict[str, Any], context_type: str) -> bool:
        snapshot = slots.get("context_snapshot") or {}
        wanted = str(context_type or "").upper()
        return wanted in (snapshot.get("uploaded_document_types") or []) or wanted in (
            snapshot.get("generated_artifact_types") or []
        )

    def _resolve_source_document_ids(
        self,
        context: dict[str, Any],
        slots: dict[str, Any],
    ) -> list[str]:
        explicit_ids = self._extract_source_document_ids(context)
        if explicit_ids:
            return explicit_ids
        source_type_slot = slots.get("source_type")
        if (
            slots.get("action") == "GENERATE"
            and source_type_slot == slots.get("artifact_type")
        ):
            source_type_slot = None
        source_type = self._source_document_type_from_slot(source_type_slot)
        if not source_type:
            source_type = self._default_source_document_type(slots.get("artifact_type"))
        if not source_type:
            return []
        uploaded_documents = self._context_items(
            context,
            ("uploaded_documents", "documents", "selected_documents"),
        )
        matches = []
        for document in uploaded_documents:
            document_type = str(
                self._item_value(document, "document_type") or ""
            ).upper()
            if document_type != source_type:
                continue
            document_id = (
                self._item_value(document, "document_id")
                or self._item_value(document, "id")
                or self._item_value(document, "file_id")
            )
            if document_id:
                matches.append(str(document_id))
        return matches

    def _source_document_type_from_slot(self, source_type: Any) -> str | None:
        if not source_type:
            return None
        normalized = str(source_type).upper()
        if normalized in {
            DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value,
            DocumentType.REQUIREMENT_SPEC.value,
            DocumentType.MEETING_NOTES.value,
            DocumentType.WBS.value,
        }:
            return normalized
        return None

    def _default_source_document_type(self, artifact_type: Any) -> str | None:
        normalized = str(artifact_type or "").upper()
        if normalized == ArtifactType.REQUIREMENT_SPEC.value:
            return DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value
        if normalized in {
            ArtifactType.WBS.value,
            ArtifactType.SCREEN_DESIGN.value,
            ArtifactType.UNITTEST_SPEC.value,
        }:
            return DocumentType.REQUIREMENT_SPEC.value
        return None

    def _artifact_type_from_slot(self, artifact_type: Any) -> ArtifactType | None:
        if not artifact_type:
            return None
        try:
            return ArtifactType(str(artifact_type).upper())
        except ValueError:
            return None

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

    def _download_intent(
        self,
        *,
        slots: dict[str, Any],
        normalized_query: str,
    ) -> dict[str, Any]:
        artifact_ref = slots.get("artifact_ref") or {}
        artifact_id = artifact_ref.get("artifact_id")
        missing_slots = [] if artifact_id else ["artifact_id"]
        return {
            "intent": "DOWNLOAD_ARTIFACT",
            "action": "DOWNLOAD",
            "artifact_id": artifact_id,
            "artifact_type": artifact_ref.get("artifact_type")
            or slots.get("artifact_type"),
            "artifact_ref": artifact_ref,
            "export_format": slots.get("export_format"),
            "required_slots": ["artifact_id"],
            "missing_slots": missing_slots,
            "available_artifact_ids": (
                (slots.get("context_snapshot") or {}).get("generated_artifact_ids")
                or []
            ),
            "entities": self._slot_entities(slots),
            "normalized_query": normalized_query,
            **self._semantic_payload(slots),
            "confidence": max(float(slots.get("confidence") or 0.0), 0.82),
        }

    def _looks_like_download_request(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_DOWNLOAD_TERMS,
        ):
            return True
        return self._contains_any(
            normalized_message,
            compact_message,
            (
                "download",
                "export",
                "file",
                "xlsx",
                "pptx",
                "pdf",
                "다운로드",
                "내보내기",
                "파일",
                "받아",
                "저장",
                "엑셀",
                "피피티",
            ),
        )

    def _detect_export_format(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> str | None:
        korean_format_tokens = (
            ("xlsx", ("엑셀", "excel")),
            ("pptx", ("ppt", "피피티", "파워포인트")),
            ("pdf", ("pdf",)),
            ("docx", ("워드", "word")),
        )
        for export_format, tokens in korean_format_tokens:
            if self._contains_any(normalized_message, compact_message, tokens):
                return export_format
        format_tokens = (
            ("xlsx", ("xlsx", "excel", "엑셀")),
            ("pptx", ("pptx", "ppt", "powerpoint", "피피티", "파워포인트")),
            ("pdf", ("pdf",)),
            ("docx", ("docx", "word", "워드")),
            ("markdown", ("markdown", "md")),
        )
        for export_format, tokens in format_tokens:
            if self._contains_any(normalized_message, compact_message, tokens):
                return export_format
        return None

    def _resolve_download_artifact(
        self,
        *,
        message: str,
        context: dict[str, Any],
        artifact_target: ArtifactType | None,
    ) -> dict[str, Any]:
        explicit_artifact_id = self._extract_artifact_id(message)
        generated_artifacts = self._context_items(
            context,
            ("generated_artifacts", "artifacts"),
        )

        def to_ref(item: Any) -> dict[str, Any]:
            return {
                "artifact_id": self._item_value(item, "artifact_id")
                or self._item_value(item, "id"),
                "artifact_type": self._item_value(item, "artifact_type"),
                "name": self._item_value(item, "name"),
                "file_name": self._item_value(item, "file_name"),
            }

        if explicit_artifact_id:
            for artifact in generated_artifacts:
                artifact_ref = to_ref(artifact)
                if str(artifact_ref.get("artifact_id") or "").upper() == (
                    explicit_artifact_id.upper()
                ):
                    return artifact_ref
            return {"artifact_id": explicit_artifact_id}

        if artifact_target is not None:
            matching_artifacts = [
                to_ref(artifact)
                for artifact in generated_artifacts
                if str(self._item_value(artifact, "artifact_type") or "").upper()
                == artifact_target.value
            ]
            if len(matching_artifacts) == 1:
                return matching_artifacts[0]

        artifact_refs = [to_ref(artifact) for artifact in generated_artifacts]
        artifact_refs = [
            artifact_ref
            for artifact_ref in artifact_refs
            if artifact_ref.get("artifact_id")
        ]
        if len(artifact_refs) == 1:
            return artifact_refs[0]
        return {}

    def _extract_artifact_id(self, message: str) -> str | None:
        match = re.search(r"\bART-[A-Za-z0-9_-]+\b", str(message or ""))
        return match.group(0).upper() if match else None

    def _detect_artifact_target(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> ArtifactType | None:
        if self._contains_any(normalized_message, compact_message, self.KO_WBS_TERMS):
            return ArtifactType.WBS
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_UNIT_TEST_TERMS,
        ):
            return ArtifactType.UNITTEST_SPEC
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_SCREEN_DESIGN_TERMS,
        ):
            return ArtifactType.SCREEN_DESIGN
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_REQUIREMENT_TERMS,
        ):
            return ArtifactType.REQUIREMENT_SPEC
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
            self.KO_CONSTRUCTION_REQUIREMENT_TERMS,
        ):
            return DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value
        if self._contains_any(normalized_message, compact_message, self.KO_TODO_TERMS):
            return "ACTION_ITEMS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_MEETING_TERMS,
        ):
            return "MEETING_NOTES"
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
        if self._looks_like_status_update(normalized_message, compact_message):
            return "UPDATE_TODO_STATUS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.COMPARISON_TERMS,
        ) and (
            self._contains_any(
                normalized_message,
                compact_message,
                self.MEETING_TERMS + self.KO_MEETING_TERMS,
            )
            and self._contains_any(
                normalized_message,
                compact_message,
                self.TODO_TERMS + self.KO_TODO_TERMS,
            )
        ):
            return "COMPARE_WEEKLY_MEETING_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_OVERDUE_TERMS,
        ):
            return "SHOW_OVERDUE_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_MEETING_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODO_TERMS,
        ):
            return "EXTRACT_TODOS_FROM_MEETING"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODAY_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODO_TERMS,
        ):
            return "SHOW_TODAY_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_NEXT_WEEK_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODO_TERMS + ("일정",),
        ):
            return "SHOW_NEXT_WEEK_TODOS"
        if self._contains_any(
            normalized_message,
            compact_message,
            self.KO_THIS_WEEK_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.KO_TODO_TERMS + ("일정",),
        ):
            return "SHOW_THIS_WEEK_TODOS"
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
            self.MEETING_TERMS,
        ) and self._contains_any(
            normalized_message,
            compact_message,
            self.UPLOAD_TERMS,
        ):
            return "EXTRACT_TODOS_FROM_MEETING"
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
        ) and (
            self._contains_any(
                normalized_message,
                compact_message,
                self.TODO_TERMS + ("업무", "해야", "일정", "뭐"),
            )
            or "뭐해야" in compact_message
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
        compact = self.normalize_text(message)
        normalized = compact.lower()
        real_korean_match = re.search(
            r"([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})\s*(?:할 일|할일|업무|TODO|todo)",
            compact,
        )
        if real_korean_match:
            candidate = real_korean_match.group(1).strip()
            ignored = {
                "이번",
                "다음",
                "오늘",
                "WBS",
                "wbs",
                "기준으로",
                "기반으로",
            }
            if candidate not in ignored and "기준" not in candidate:
                return candidate
        explicit_match = re.search(
            r"담당자\s*[:：은는이가]?\s*([0-9A-Za-z가-힣_]{1,30})",
            compact,
        )
        if explicit_match:
            return explicit_match.group(1).strip()
        if re.search(r"(?:내|나의|나)\s*(?:todo|TODO|할\s*일|업무)", compact):
            return "나"
        for suffix in ("할 일", "할일", "업무", "TODO", "todo"):
            marker_index = compact.find(suffix)
            if marker_index > 0:
                candidate = compact[:marker_index].strip(" 은는이가의,")
                ignored = {
                    "이번주",
                    "이번 주",
                    "다음주",
                    "다음 주",
                    "오늘",
                    "금주",
                    "지난주",
                    "지난 주",
                    "wbs",
                    "WBS",
                }
                if (
                    1 < len(candidate) <= 30
                    and " " not in candidate
                    and candidate not in ignored
                    and candidate.lower() not in ignored
                    and "기준" not in normalized[:marker_index]
                ):
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
            self.TODO_COMPLETION_TERMS + self.KO_COMPLETION_TERMS,
        )

    def _todo_completion_query(self, message: str) -> str:
        query = self.normalize_text(message)
        for term in self.TODO_COMPLETION_TERMS:
            query = query.replace(term, "")
        query = re.sub(r"\b(done|complete)\b", " ", query, flags=re.IGNORECASE)
        query = re.sub(r"(?:이\s*)?(?:업무|항목|일|todo|TODO)\s*$", " ", query)
        return " ".join(query.strip(" .。!！").split())

    def _has_generation_signal(
        self,
        normalized_message: str,
        compact_message: str,
    ) -> bool:
        return self._contains_any(
            normalized_message,
            compact_message,
            self.GENERATION_TOKENS + self.KO_GENERATION_TERMS,
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
        if target_artifact_type == ArtifactType.WBS:
            return [DocumentType.REQUIREMENT_SPEC.value]
        if target_artifact_type == ArtifactType.SCREEN_DESIGN:
            return [
                DocumentType.REQUIREMENT_SPEC.value,
                DocumentType.CONSTRUCTION_REQUIREMENT_DEFINITION.value,
                "RFP",
                "PLANNING_DOC",
            ]
        if target_artifact_type == ArtifactType.UNITTEST_SPEC:
            return [
                DocumentType.REQUIREMENT_SPEC.value,
                "PROGRAM_LIST",
                "PROGRAM_DESIGN",
                "SCREEN_DESIGN",
            ]
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
        normalized = self.normalize_text(message)
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
            ("단위 테스트 계획서", "단위테스트계획서"),
            ("단위테스트 계획서", "단위테스트계획서"),
            ("테스트 계획서", "테스트계획서"),
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
        if compact_message in {
            "응",
            "응진행해",
            "그래",
            "그래생성해",
            "확인",
            "진행해",
            "계속해",
        }:
            return True
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
        if compact_message in {
            "아니",
            "아니취소",
            "취소",
            "방금거취소",
            "그만",
            "중단",
        }:
            return True
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
