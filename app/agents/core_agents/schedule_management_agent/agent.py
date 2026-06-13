# EN: Core agent adapter for lightweight schedule/todo management.
# KO: 회의록 기반 TODO와 주차 조회를 위한 Core Agent adapter입니다.

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class ScheduleManagementAgent:
    """Returns structured schedule results without touching persistence."""

    AGENT_NAME = "ScheduleManagementAgent"
    DEFAULT_ACTION = "EXTRACT_TODOS_FROM_MEETING"
    SUPPORTED_ACTIONS = {
        "EXTRACT_TODOS_FROM_MEETING",
        "SHOW_CURRENT_WEEK",
        "SHOW_THIS_WEEK_TODOS",
        "SHOW_NEXT_WEEK_TODOS",
        "SHOW_TODAY_TODOS",
        "SHOW_OVERDUE_TODOS",
        "SHOW_TODO_STATUS",
        "SHOW_ASSIGNEE_TODOS",
        "ASSISTANT_BRIEFING",
        "COMPARE_WEEKLY_MEETING_TODOS",
        "COMPLETE_TODO",
        "UPDATE_TODO_DUE_DATE",
        "UPDATE_TODO_ASSIGNEE",
    }
    ACTION_KEYWORDS = (
        "검토",
        "정리",
        "확인",
        "작성",
        "준비",
        "진행",
        "공유",
        "전달",
        "완료",
        "수정",
        "보완",
        "업데이트",
        "협의",
        "확정",
        "검증",
        "리뷰",
        "개발",
        "테스트",
        "배포",
    )
    OBLIGATION_KEYWORDS = (
        "필요",
        "해야",
        "하기",
        "담당",
        "까지",
        "todo",
        "할 일",
        "할일",
        "액션아이템",
        "action item",
    )
    TODO_TRIGGER_PHRASES = (
        "하기로 함",
        "하기로 했",
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
    RELATED_ARTIFACT_TERMS = (
        ("요구사항 명세서", "요구사항 정의서"),
        ("요구사항명세서", "요구사항 정의서"),
        ("요구사항 정의서", "요구사항 정의서"),
        ("요구사항정의서", "요구사항 정의서"),
        ("화면설계서", "화면설계서"),
        ("화면 설계서", "화면설계서"),
        ("WBS", "WBS"),
        ("테스트 케이스", "단위테스트케이스"),
        ("테스트케이스", "단위테스트케이스"),
        ("회의록", "회의록"),
        ("주간보고서", "주간보고서"),
    )
    WEEKDAY_INDEX = {
        "월요일": 0,
        "월": 0,
        "화요일": 1,
        "화": 1,
        "수요일": 2,
        "수": 2,
        "목요일": 3,
        "목": 3,
        "금요일": 4,
        "금": 4,
        "토요일": 5,
        "토": 5,
        "일요일": 6,
        "일": 6,
    }
    WBS_PHASE_TITLES = (
        "요구사항정의",
        "요구사항 정의",
        "분석",
        "설계",
        "구현",
        "테스트",
        "이행",
        "안정화",
    )
    PLACEHOLDER_ASSIGNEES = {"작업자", "담당자", "owner", "담당", "미정", "tbd", "-"}
    STATUS_ALIASES = {
        "완료": "DONE",
        "done": "DONE",
        "종료": "DONE",
        "진행중": "IN_PROGRESS",
        "진행": "IN_PROGRESS",
        "in progress": "IN_PROGRESS",
        "미착수": "NOT_STARTED",
        "시작전": "NOT_STARTED",
        "not started": "NOT_STARTED",
        "지연": "OVERDUE",
        "delay": "OVERDUE",
        "overdue": "OVERDUE",
        "보류": "ON_HOLD",
        "hold": "ON_HOLD",
    }

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate requested | "
            f"project_id={request.project_id}"
        )

        context = request.context or {}
        action = self._normalize_action(context)
        if action not in self.SUPPORTED_ACTIONS:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error=f"unsupported schedule action: {action}",
            )

        try:
            if action == "EXTRACT_TODOS_FROM_MEETING":
                return self._generate_todo_extraction(request, context)
            if action == "SHOW_CURRENT_WEEK":
                return self._success(self._current_week_result(context))
            if action == "SHOW_THIS_WEEK_TODOS":
                return self._success(self._this_week_todos_result(context))
            if action == "SHOW_NEXT_WEEK_TODOS":
                return self._success(
                    self._period_todos_result(context, action, "NEXT_WEEK")
                )
            if action == "SHOW_TODAY_TODOS":
                return self._success(self._period_todos_result(context, action, "TODAY"))
            if action == "ASSISTANT_BRIEFING":
                return self._success(
                    self._period_todos_result(context, action, "THIS_WEEK")
                )
            if action == "SHOW_OVERDUE_TODOS":
                return self._success(self._overdue_todos_result(context))
            if action == "SHOW_ASSIGNEE_TODOS":
                return self._success(self._assignee_todos_result(context))
            if action == "COMPARE_WEEKLY_MEETING_TODOS":
                return self._success(self._weekly_meeting_comparison_result(context))
            if action == "COMPLETE_TODO":
                return self._success(self._complete_todo_result(context))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "[%s] schedule context fallback returned required info | action=%s | error=%s",
                self.AGENT_NAME,
                action,
                exc,
                exc_info=True,
            )
            return self._success(self._schedule_context_error_result(action, exc))

        return self._success(
            {
                "action": action,
                "status": "REQUIRED_INFO",
                "missing_fields": ["supported_action_handler"],
                "metadata": {"message_key": "ACTION_NOT_IMPLEMENTED"},
            }
        )

    def _generate_todo_extraction(
        self,
        request: AgentRequest,
        context: dict[str, Any],
    ) -> AgentResponse:
        meeting_notes = str(context.get("meeting_notes") or "").strip()
        if not meeting_notes:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="meeting_notes is required",
            )

        source_document_id = self._extract_source_document_id(context, request.documents)
        source_chunk_ids = self._extract_source_chunk_ids(request.documents)
        current_date = self._current_date(context)
        todos = self._extract_todos(
            meeting_notes=meeting_notes,
            source_document_id=source_document_id,
            source_chunk_ids=source_chunk_ids,
            current_date=current_date,
        )
        if not todos:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="No action items were found in meeting notes",
            )

        needs_confirmation_count = sum(
            1 for todo in todos if todo.get("status") == "NEEDS_CONFIRMATION"
        )
        return self._success(
            {
                "artifact_type": "SCHEDULE_TODO_LIST",
                "action": "EXTRACT_TODOS_FROM_MEETING",
                "status": "SUCCESS",
                "todos": todos,
                "needs_confirmation": [
                    todo for todo in todos if todo.get("status") == "NEEDS_CONFIRMATION"
                ],
                "needs_confirmation_count": needs_confirmation_count,
                "missing_fields": [],
                "candidates": [],
                "metadata": {
                    "source": "meeting_notes",
                    "extraction_strategy": "rule_based_schedule_agent",
                    "todo_count": len(todos),
                    "needs_confirmation_count": needs_confirmation_count,
                },
            }
        )

    def _extract_todos(
        self,
        *,
        meeting_notes: str,
        source_document_id: str | None,
        source_chunk_ids: list[str],
        current_date: date,
    ) -> list[dict[str, Any]]:
        todos: list[dict[str, Any]] = []
        for sentence in self._split_candidate_sentences(meeting_notes):
            if not self._is_action_candidate(sentence, current_date):
                continue

            assignee = self._extract_assignee(sentence)
            due_date, due_metadata = self._extract_due_date(sentence, current_date)
            title = self._extract_title(sentence, assignee, due_metadata.get("raw_text"))
            if not title:
                continue

            related_artifact = self._extract_related_artifact(sentence)
            status = "TODO" if assignee and due_date else "NEEDS_CONFIRMATION"
            confidence = 0.86 if status == "TODO" else 0.62
            metadata: dict[str, Any] = {
                "source_text": sentence,
                "extraction_strategy": "rule_based_schedule_agent",
            }
            if due_metadata.get("unparsed_due_date_text"):
                metadata["unparsed_due_date_text"] = due_metadata[
                    "unparsed_due_date_text"
                ]

            todos.append(
                {
                    "todo_id": f"TODO-TEMP-{len(todos) + 1:03d}",
                    "project_id": "",
                    "title": title,
                    "description": "회의록에서 추출된 TODO",
                    "assignee": assignee,
                    "due_date": due_date,
                    "related_artifact": related_artifact,
                    "related_document": related_artifact or "회의록 기반 신규 TODO",
                    "source_type": "MEETING_NOTE",
                    "status": status,
                    "confidence": confidence,
                    "evidence": sentence,
                    "source_document_id": source_document_id,
                    "source_chunk_ids": source_chunk_ids,
                    "metadata": metadata,
                }
            )

        return todos

    def _split_candidate_sentences(self, meeting_notes: str) -> list[str]:
        normalized = meeting_notes.replace("\r\n", "\n").replace("\r", "\n")
        parts = re.split(r"(?:\n+|(?<=[.!?。])\s+|[;；])", normalized)
        return [
            sentence
            for sentence in (self._clean_sentence(part) for part in parts)
            if sentence
        ]

    def _clean_sentence(self, sentence: str) -> str:
        sentence = sentence.strip(" \t-*•")
        sentence = re.sub(r"^\d+[\).]\s*", "", sentence)
        sentence = re.sub(
            r"^(?:회의록|회의 내용|미팅 내용)\s*[:：-]\s*",
            "",
            sentence,
        )
        return sentence.strip()

    def _is_action_candidate(self, sentence: str, current_date: date) -> bool:
        normalized = sentence.lower()
        if any(phrase.lower() in normalized for phrase in self.TODO_TRIGGER_PHRASES):
            return True
        has_action_keyword = any(keyword in normalized for keyword in self.ACTION_KEYWORDS)
        has_obligation = any(
            keyword in normalized for keyword in self.OBLIGATION_KEYWORDS
        )
        due_date, due_metadata = self._extract_due_date(sentence, current_date)
        has_due_signal = bool(due_date or due_metadata.get("unparsed_due_date_text"))
        assignee = self._extract_assignee(sentence)
        if "현황" in sentence and "공유" in sentence and not has_obligation and not assignee:
            return False
        return has_action_keyword and (has_obligation or has_due_signal or assignee)

    def _extract_assignee(self, sentence: str) -> str | None:
        explicit_match = re.search(
            r"(?:담당자?|owner)\s*[:：]?\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})",
            sentence,
            re.IGNORECASE,
        )
        if explicit_match:
            return explicit_match.group(1).strip()

        subject_match = re.match(
            r"^\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})(?:님)?(?:은|는|이|가)\s+",
            sentence,
        )
        if subject_match:
            candidate = subject_match.group(1).strip()
            if not self._is_invalid_assignee(candidate):
                return candidate

        english_subject_match = re.match(
            r"^\s*([A-Z][A-Za-z0-9._-]{1,30})\s+(?:owns|will|should|to)\b",
            sentence,
        )
        if english_subject_match:
            return english_subject_match.group(1).strip()

        return None

    def _is_invalid_assignee(self, candidate: str) -> bool:
        return candidate.endswith("에서") or candidate in {
            "회의",
            "미팅",
            "오늘",
            "내일",
            "이번",
            "다음",
            "개발팀은",
        }

    def _extract_due_date(
        self,
        sentence: str,
        current_date: date,
    ) -> tuple[str | None, dict[str, str]]:
        iso_match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", sentence)
        if iso_match:
            year, month, day = iso_match.groups()
            return (
                f"{int(year):04d}-{int(month):02d}-{int(day):02d}",
                {"raw_text": iso_match.group(0)},
            )

        korean_date_match = re.search(
            r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일",
            sentence,
        )
        if korean_date_match:
            year, month, day = korean_date_match.groups()
            return (
                f"{int(year):04d}-{int(month):02d}-{int(day):02d}",
                {"raw_text": korean_date_match.group(0)},
            )

        slash_month_day_match = re.search(
            r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
            sentence,
        )
        if slash_month_day_match:
            month, day = slash_month_day_match.groups()
            return (
                f"{current_date.year:04d}-{int(month):02d}-{int(day):02d}",
                {"raw_text": slash_month_day_match.group(0)},
            )

        month_day_match = re.search(r"(\d{1,2})월\s*(\d{1,2})일", sentence)
        if month_day_match:
            month, day = month_day_match.groups()
            return (
                f"{current_date.year:04d}-{int(month):02d}-{int(day):02d}",
                {"raw_text": month_day_match.group(0)},
            )

        if "내일" in sentence:
            return (
                (current_date + timedelta(days=1)).isoformat(),
                {"raw_text": "내일"},
            )
        if "오늘" in sentence:
            return (current_date.isoformat(), {"raw_text": "오늘"})

        week_day_match = re.search(
            r"((?:이번|금|다음|차)\s*주)\s*(월요일|화요일|수요일|목요일|금요일|토요일|일요일|월|화|수|목|금|토|일)",
            sentence,
        )
        if week_day_match:
            week_text, weekday_text = week_day_match.groups()
            return (
                self._week_relative_date(current_date, week_text, weekday_text),
                {"raw_text": week_day_match.group(0)},
            )

        if "금주 중" in sentence or "이번 주까지" in sentence or "이번주까지" in sentence:
            return (
                self._week_bounds(current_date)[1].isoformat(),
                {"raw_text": "금주 중" if "금주 중" in sentence else "이번 주까지"},
            )

        if "다음 주까지" in sentence or "다음주까지" in sentence:
            next_week_start = self._week_bounds(current_date)[0] + timedelta(days=7)
            return (
                (next_week_start + timedelta(days=6)).isoformat(),
                {"raw_text": "다음 주까지"},
            )

        if "월말" in sentence:
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            return (
                date(current_date.year, current_date.month, last_day).isoformat(),
                {"raw_text": "월말"},
            )

        if "다음 회의 전까지" in sentence or "다음 회의 전" in sentence:
            raw_text = "다음 회의 전까지" if "다음 회의 전까지" in sentence else "다음 회의 전"
            return (
                None,
                {
                    "raw_text": raw_text,
                    "unparsed_due_date_text": "다음 회의 전",
                },
            )

        return None, {}

    def _week_relative_date(
        self,
        current_date: date,
        week_text: str,
        weekday_text: str,
    ) -> str:
        week_start, _ = self._week_bounds(current_date)
        if "다음" in week_text or "차" in week_text:
            week_start += timedelta(days=7)
        weekday_index = self.WEEKDAY_INDEX[weekday_text]
        return (week_start + timedelta(days=weekday_index)).isoformat()

    def _extract_related_artifact(self, sentence: str) -> str | None:
        lowered = sentence.lower()
        for term, label in self.RELATED_ARTIFACT_TERMS:
            if term.lower() in lowered:
                return label
        return None

    def _extract_title(
        self,
        sentence: str,
        assignee: str | None,
        due_text: str | None,
    ) -> str:
        title = sentence
        if assignee:
            title = re.sub(
                rf"^\s*{re.escape(assignee)}(?:님)?(?:은|는|이|가)\s+",
                "",
                title,
            )
            title = re.sub(
                rf"^(?:담당자|담당|owner)\s*[:：]?\s*{re.escape(assignee)}\s*",
                "",
                title,
                flags=re.IGNORECASE,
            )

        if due_text:
            title = title.replace(due_text, "")
        title = re.sub(r"(?:까지|전까지|까지는|까지로)\s*", "", title)
        for phrase in self.TODO_TRIGGER_PHRASES:
            if phrase.startswith("하기로"):
                continue
            title = title.replace(phrase, "")
        title = re.sub(r"\s*(?:하기로|하기)\s*(?:했|하였|함|했습니다|했습니다\.)?.*$", "", title)
        title = re.sub(r"\s*(?:한다|합니다|했다|했습니다|할 것|해 주세요|해주세요)\.?\s*$", "", title)
        title = re.sub(r"\s*(?:필요|필요함|해야 함|해야함)\s*$", "", title)
        title = re.sub(
            r"\s+(?:진행|공유|전달|완료|수정|보완|업데이트|협의|확정|검증|리뷰|개발|테스트|배포)\s*$",
            "",
            title,
        )
        title = re.sub(r"\s*(?:을|를)\s+", " ", title)
        title = re.sub(r"\s*(?:을|를)\s*$", "", title)
        title = re.sub(r"\s+", " ", title)
        return title.strip(" .,:：-")

    def _current_week_result(self, context: dict[str, Any]) -> dict[str, Any]:
        week_context, missing_fields, status = self._project_week_context(context)
        if self._requires_wbs_context(context, "SHOW_CURRENT_WEEK") and not self._has_wbs_context(
            context
        ):
            return self._required_context_result(
                action="SHOW_CURRENT_WEEK",
                required_context="WBS",
                missing_fields=["wbs"],
                week_context=week_context,
            )
        result = {
            "action": "SHOW_CURRENT_WEEK",
            "status": status,
            "week_context": week_context,
            "missing_fields": missing_fields,
            "metadata": {},
        }
        return result

    def _this_week_todos_result(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._period_todos_result(context, "SHOW_THIS_WEEK_TODOS", "THIS_WEEK")

    def _period_todos_result(
        self,
        context: dict[str, Any],
        action: str,
        period: str,
    ) -> dict[str, Any]:
        wbs_tasks = self._context_wbs_tasks(context)
        week_context, missing_fields, status = self._project_week_context(context)
        if self._requires_wbs_context(context, action) and not wbs_tasks:
            return self._required_context_result(
                action=action,
                required_context="WBS",
                missing_fields=["wbs"],
                week_context=week_context,
            )
        if missing_fields:
            return {
                "artifact_type": "SCHEDULE_TODO_LIST",
                "action": action,
                "status": status,
                "todos": [],
                "needs_confirmation": [],
                "week_context": week_context,
                "missing_fields": missing_fields,
                "assistant_message": self._missing_period_context_message(
                    missing_fields
                ),
                "metadata": {
                    "required_context": "PROJECT_SCHEDULE",
                    "message_key": "PERIOD_CONTEXT_REQUIRED",
                },
            }

        week_start, week_end = self._period_bounds(
            week_context,
            period,
            wbs_tasks=wbs_tasks,
        )
        todos = []
        needs_confirmation = []
        for todo in self._context_todos(context):
            due_date = self._parse_date(todo.get("due_date"))
            normalized_todo = self._normalize_todo(todo)
            if due_date and week_start <= due_date <= week_end:
                todos.append(normalized_todo)
            elif not due_date and normalized_todo.get("status") == "NEEDS_CONFIRMATION":
                needs_confirmation.append(normalized_todo)

        include_ongoing_tasks = self._include_ongoing_tasks(context)
        project_bounds = self._wbs_project_bounds(wbs_tasks, week_context)
        planned_tasks = []
        ongoing_management_tasks = []
        for task in wbs_tasks:
            if not self._wbs_task_overlaps(task, week_start, week_end):
                continue
            normalized_task = self._normalize_wbs_task(task)
            if self._is_phase_title(str(normalized_task.get("title") or "")):
                continue
            if self._is_ongoing_management_task(normalized_task, project_bounds):
                ongoing_management_tasks.append(normalized_task)
                if include_ongoing_tasks:
                    planned_tasks.append(normalized_task)
                continue
            planned_tasks.append(normalized_task)
        todos.extend(planned_tasks)

        current_phase = self._current_phase(wbs_tasks, self._current_date(context))
        assistant_message = self._schedule_assistant_message(
            action=action,
            period=period,
            week_context=week_context,
            current_phase=current_phase,
            planned_tasks=planned_tasks,
            ongoing_management_tasks=ongoing_management_tasks,
            period_start=week_start,
            period_end=week_end,
        )

        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": action,
            "status": "SUCCESS",
            "todos": todos,
            "needs_confirmation": needs_confirmation,
            "needs_confirmation_count": len(needs_confirmation),
            "week_context": week_context,
            "current_phase": current_phase or {},
            "planned_tasks": planned_tasks,
            "ongoing_management_tasks": ongoing_management_tasks,
            "assistant_message": assistant_message,
            "missing_fields": [],
            "metadata": {
                "todo_count": len(todos),
                "wbs_task_count": len(planned_tasks),
                "ongoing_management_task_count": len(ongoing_management_tasks),
                "period": period,
            },
        }

    def _assignee_todos_result(self, context: dict[str, Any]) -> dict[str, Any]:
        normalized_input = context.get("normalized_input") or {}
        entities = normalized_input.get("entities") or {}
        assignee = str(entities.get("assignee") or context.get("assignee") or "").strip()
        if not assignee:
            return self._required_context_result(
                action="SHOW_ASSIGNEE_TODOS",
                required_context="ASSIGNEE",
                missing_fields=["assignee"],
            )

        todos = [
            self._normalize_todo(todo)
            for todo in self._context_todos(context)
            if str(todo.get("assignee") or todo.get("owner") or "").strip() == assignee
            and todo.get("status") != "DONE"
        ]
        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": "SHOW_ASSIGNEE_TODOS",
            "status": "SUCCESS",
            "todos": todos,
            "needs_confirmation": [],
            "missing_fields": [],
            "metadata": {"assignee": assignee, "todo_count": len(todos)},
        }

    def _weekly_meeting_comparison_result(self, context: dict[str, Any]) -> dict[str, Any]:
        previous_todos = context.get("previous_meeting_todos") or []
        current_todos = context.get("current_meeting_todos") or []
        if not previous_todos and not current_todos:
            return self._required_context_result(
                action="COMPARE_WEEKLY_MEETING_TODOS",
                required_context="MEETING_NOTES",
                missing_fields=["previous_meeting_notes", "current_meeting_notes"],
            )
        previous_items = [
            self._normalize_todo(todo) for todo in previous_todos if isinstance(todo, dict)
        ]
        current_items = [
            self._normalize_todo(todo) for todo in current_todos if isinstance(todo, dict)
        ]
        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": "COMPARE_WEEKLY_MEETING_TODOS",
            "status": "SUCCESS",
            "todos": current_items,
            "needs_confirmation": [
                item for item in current_items if item.get("status") == "NEEDS_CONFIRMATION"
            ],
            "missing_fields": [],
            "metadata": {
                "previous_todo_count": len(previous_items),
                "current_todo_count": len(current_items),
                "comparison": {
                    "previous": previous_items,
                    "current": current_items,
                },
            },
        }

    def _overdue_todos_result(self, context: dict[str, Any]) -> dict[str, Any]:
        current_date = self._current_date(context)
        todos = []
        for todo in self._context_todos(context):
            due_date = self._parse_date(todo.get("due_date"))
            if due_date and due_date < current_date and todo.get("status") != "DONE":
                overdue = self._normalize_todo(todo)
                overdue["status"] = "OVERDUE"
                todos.append(overdue)
        for task in self._context_wbs_tasks(context):
            normalized_task = self._normalize_wbs_task(task)
            planned_end_date = self._parse_date(normalized_task.get("planned_end_date"))
            if (
                planned_end_date
                and planned_end_date < current_date
                and self._is_wbs_overdue_candidate(normalized_task)
            ):
                normalized_task["status"] = "OVERDUE"
                normalized_task["status_display"] = "지연"
                todos.append(normalized_task)
        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": "SHOW_OVERDUE_TODOS",
            "status": "SUCCESS",
            "todos": todos,
            "needs_confirmation": [],
            "missing_fields": [],
            "metadata": {"todo_count": len(todos)},
        }

    def _required_context_result(
        self,
        *,
        action: str,
        required_context: str,
        missing_fields: list[str],
        week_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": action,
            "status": "REQUIRED_INFO",
            "todos": [],
            "needs_confirmation": [],
            "missing_fields": missing_fields,
            "week_context": week_context or {},
            "metadata": {"required_context": required_context},
        }

    def _schedule_context_error_result(
        self,
        action: str,
        exc: Exception,
    ) -> dict[str, Any]:
        return {
            "artifact_type": "SCHEDULE_TODO_LIST",
            "action": action,
            "status": "REQUIRED_INFO",
            "todos": [],
            "needs_confirmation": [],
            "missing_fields": ["schedule_context"],
            "week_context": {},
            "assistant_message": (
                "WBS 또는 프로젝트 일정 기준 정보가 부족해 이번 주 범위를 계산할 수 없습니다. "
                "프로젝트 시작일을 설정하거나 기간이 포함된 WBS를 생성/업로드해 주세요."
            ),
            "metadata": {
                "required_context": "PROJECT_SCHEDULE",
                "message_key": "SCHEDULE_CONTEXT_INVALID",
                "error_type": type(exc).__name__,
            },
        }

    def _missing_period_context_message(self, missing_fields: list[str]) -> str:
        if "wbs.task_period" in missing_fields:
            return (
                "WBS는 확인했지만 작업 기간 정보가 없어 이번 주 할 일을 계산할 수 없습니다. "
                "작업 시작일과 종료일이 포함된 WBS를 사용해 주세요."
            )
        return (
            "WBS는 확인했지만 프로젝트 시작일 또는 작업 기간 정보가 없어 이번 주 범위를 "
            "계산할 수 없습니다. 프로젝트 시작일을 먼저 설정해 주세요."
        )

    def _period_bounds(
        self,
        week_context: dict[str, Any] | None,
        period: str,
        *,
        wbs_tasks: list[dict[str, Any]] | None = None,
    ) -> tuple[date, date]:
        week_context = week_context or {}
        current_date = self._parse_date(week_context.get("current_date")) or date.today()
        if period == "TODAY":
            return current_date, current_date
        week_start = self._parse_date(week_context.get("week_start_date"))
        week_end = self._parse_date(week_context.get("week_end_date"))
        if week_start is None or week_end is None:
            project_start = self._parse_date(week_context.get("project_start_date"))
            if project_start is None and wbs_tasks:
                project_start, _ = self._wbs_project_bounds(wbs_tasks)
            if project_start is not None:
                week_start, week_end, _ = self._project_week_bounds(
                    project_start=project_start,
                    current_date=current_date,
                )
            else:
                week_start, week_end = self._week_bounds(current_date)
        if period == "NEXT_WEEK":
            next_week_start = week_end + timedelta(days=1)
            return next_week_start, next_week_start + timedelta(days=6)
        return week_start, week_end

    def _requires_wbs_context(self, context: dict[str, Any], action: str) -> bool:
        normalized_input = context.get("normalized_input") or {}
        needs_context = normalized_input.get("needs_context") or []
        entities = normalized_input.get("entities") or {}
        if entities.get("source") == "WBS":
            return True
        if action in {
            "SHOW_CURRENT_WEEK",
            "SHOW_THIS_WEEK_TODOS",
            "SHOW_NEXT_WEEK_TODOS",
            "SHOW_TODAY_TODOS",
            "ASSISTANT_BRIEFING",
        }:
            return "WBS" in needs_context
        return False

    def _has_wbs_context(self, context: dict[str, Any]) -> bool:
        return bool(self._context_wbs_tasks(context))

    def _context_wbs_tasks(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        wbs_context = context.get("wbs_context") if isinstance(context.get("wbs_context"), dict) else {}
        raw_sources = [
            context.get("wbs_tasks"),
            context.get("wbs_items"),
            (context.get("wbs") or {}).get("tasks")
            if isinstance(context.get("wbs"), dict)
            else None,
            wbs_context.get("tasks"),
            wbs_context.get("rows"),
        ]
        tasks: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for raw in raw_sources:
            if isinstance(raw, list):
                for task in raw:
                    if not isinstance(task, dict):
                        continue
                    if not self._task_value(
                        task,
                        "title",
                        "name",
                        "task_name",
                        "WBS명",
                    ):
                        continue
                    key = self._wbs_identity_key(task)
                    if key in seen:
                        continue
                    seen.add(key)
                    tasks.append(task)
        return tasks

    def _wbs_task_overlaps(
        self,
        task: dict[str, Any],
        period_start: date,
        period_end: date,
    ) -> bool:
        start_date, end_date = self._wbs_task_dates(task)
        if start_date and end_date:
            return start_date <= period_end and end_date >= period_start
        if end_date:
            return period_start <= end_date <= period_end
        if start_date:
            return period_start <= start_date <= period_end
        return False

    def _normalize_wbs_task(self, task: dict[str, Any]) -> dict[str, Any]:
        start_date, end_date = self._wbs_task_dates(task)
        raw_assignee = self._task_value(
            task,
            "raw_assignee",
            "assignee",
            "owner",
            "worker",
            "담당자",
            "작업자",
        )
        assignee, assignee_display = self._normalize_assignee(raw_assignee)
        actual_start_date = self._parse_date(
            self._task_value(task, "actual_start_date", "actualStartDate", "실제시작일")
        )
        actual_end_date = self._parse_date(
            self._task_value(task, "actual_end_date", "actualEndDate", "실제종료일")
        )
        status = self._normalize_wbs_status(
            self._task_value(task, "raw_status", "status", "work_status", "작업상태"),
            actual_start_date=actual_start_date,
            actual_end_date=actual_end_date,
        )
        row_number = self._task_value(task, "row_number", "rowNumber")
        wbs_id = self._task_value(task, "wbs_id", "id", "ID")
        title = str(
            self._task_value(task, "title", "name", "task_name", "WBS명")
            or "WBS 작업"
        )
        source_document_name = self._task_value(
            task,
            "source_document_name",
            "sourceDocumentName",
            "related_document",
        )
        basis = task.get("basis")
        if not basis and source_document_name and row_number:
            basis = [f"{source_document_name} row {row_number}"]
        elif not basis and source_document_name:
            basis = [str(source_document_name)]

        todo_id = (
            task.get("todo_id")
            or task.get("task_id")
            or self._wbs_row_todo_id(row_number=row_number, wbs_id=wbs_id, title=title)
        )
        return {
            "todo_id": todo_id,
            "project_id": task.get("project_id"),
            "source_document_id": task.get("source_document_id"),
            "source_document_name": source_document_name,
            "source_artifact_id": task.get("source_artifact_id"),
            "row_number": row_number,
            "wbs_id": wbs_id,
            "title": title,
            "description": task.get("description") or "WBS 기준 이번 기간 작업",
            "raw_assignee": raw_assignee,
            "assignee": assignee,
            "assignee_display": assignee_display,
            "planned_start_date": start_date.isoformat() if start_date else None,
            "planned_end_date": end_date.isoformat() if end_date else None,
            "actual_start_date": actual_start_date.isoformat()
            if actual_start_date
            else None,
            "actual_end_date": actual_end_date.isoformat() if actual_end_date else None,
            "due_date": end_date.isoformat() if end_date else None,
            "artifact": self._task_value(task, "artifact", "deliverable", "산출물"),
            "related_artifact": "WBS",
            "related_document": source_document_name or "WBS",
            "source_type": "WBS",
            "status": status,
            "status_display": self._wbs_status_display(status),
            "metadata": {
                **(task.get("metadata") or {}),
                "basis": basis or ["WBS"],
            },
        }

    def _task_value(self, task: dict[str, Any], *keys: str) -> Any:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        for key in keys:
            value = task.get(key)
            if value in (None, ""):
                value = metadata.get(key)
            if value not in (None, ""):
                return value
        return None

    def _wbs_identity_key(self, task: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(self._task_value(task, "row_number", "rowNumber") or ""),
            str(self._task_value(task, "wbs_id", "id", "ID", "task_id") or ""),
            str(self._task_value(task, "title", "name", "task_name", "WBS명") or ""),
        )

    def _wbs_row_todo_id(
        self,
        *,
        row_number: Any,
        wbs_id: Any,
        title: str,
    ) -> str:
        if row_number not in (None, ""):
            return f"WBS-ROW-{row_number}-{self._safe_identifier(wbs_id or title)}"
        return f"WBS-{self._safe_identifier(wbs_id or title)}"

    def _safe_identifier(self, value: Any) -> str:
        normalized = re.sub(r"[^0-9A-Za-z가-힣.-]+", "-", str(value or "").strip())
        return normalized.strip("-") or "TASK"

    def _wbs_task_dates(self, task: dict[str, Any]) -> tuple[date | None, date | None]:
        start_date = self._parse_date(
            self._task_value(
                task,
                "planned_start_date",
                "start_date",
                "startDate",
                "planned_start",
                "시작예정일",
            )
        )
        end_date = self._parse_date(
            self._task_value(
                task,
                "planned_end_date",
                "end_date",
                "endDate",
                "planned_end",
                "due_date",
                "종료예정일",
            )
        )
        return start_date, end_date

    def _normalize_assignee(self, raw_assignee: Any) -> tuple[str | None, str]:
        assignee = str(raw_assignee or "").strip()
        if not assignee:
            return None, "확인 필요"
        if assignee.lower() in self.PLACEHOLDER_ASSIGNEES:
            return None, "확인 필요"
        return assignee, assignee

    def _normalize_wbs_status(
        self,
        raw_status: Any,
        *,
        actual_start_date: date | None,
        actual_end_date: date | None,
    ) -> str:
        status_text = str(raw_status or "").strip()
        if status_text:
            return self.STATUS_ALIASES.get(status_text.lower(), status_text.upper())
        if actual_end_date:
            return "DONE"
        if actual_start_date:
            return "IN_PROGRESS"
        return "PLANNED_OR_UNKNOWN"

    def _wbs_status_display(self, status: str) -> str:
        return {
            "DONE": "완료",
            "IN_PROGRESS": "진행 중",
            "NOT_STARTED": "미착수",
            "OVERDUE": "지연",
            "ON_HOLD": "보류",
            "PLANNED_OR_UNKNOWN": "확인 필요",
        }.get(status, "확인 필요")

    def _is_wbs_overdue_candidate(self, task: dict[str, Any]) -> bool:
        status = str(task.get("status") or "")
        if status in {"IN_PROGRESS", "NOT_STARTED", "OVERDUE"}:
            return True
        return bool(task.get("actual_start_date") and not task.get("actual_end_date"))

    def _include_ongoing_tasks(self, context: dict[str, Any]) -> bool:
        normalized_input = context.get("normalized_input") or {}
        query = " ".join(
            str(value or "")
            for value in [
                context.get("raw_message"),
                normalized_input.get("raw_message"),
                normalized_input.get("normalized_query"),
            ]
        )
        return any(
            token in query
            for token in ("전체", "모두", "다 보여", "관리 업무", "상시 업무", "상시")
        )

    def _wbs_project_bounds(
        self,
        tasks: list[dict[str, Any]],
        week_context: dict[str, Any] | None = None,
    ) -> tuple[date | None, date | None]:
        starts: list[date] = []
        ends: list[date] = []
        if week_context:
            start = self._parse_date(week_context.get("project_start_date"))
            end = self._parse_date(week_context.get("project_end_date"))
            if start:
                starts.append(start)
            if end:
                ends.append(end)
        for task in tasks:
            start, end = self._wbs_task_dates(task)
            if start:
                starts.append(start)
            if end:
                ends.append(end)
        return (min(starts) if starts else None, max(ends) if ends else None)

    def _is_ongoing_management_task(
        self,
        task: dict[str, Any],
        project_bounds: tuple[date | None, date | None],
    ) -> bool:
        project_start, project_end = project_bounds
        task_start = self._parse_date(task.get("planned_start_date"))
        task_end = self._parse_date(task.get("planned_end_date"))
        if not project_start or not project_end or not task_start or not task_end:
            return False
        project_days = max((project_end - project_start).days + 1, 1)
        task_days = max((task_end - task_start).days + 1, 1)
        return task_days / project_days >= 0.8

    def _current_phase(
        self,
        tasks: list[dict[str, Any]],
        current_date: date,
    ) -> dict[str, Any] | None:
        phase_candidates = []
        for task in tasks:
            title = str(
                self._task_value(task, "title", "name", "task_name", "WBS명")
                or ""
            ).strip()
            if not self._is_phase_title(title):
                continue
            start_date, end_date = self._wbs_task_dates(task)
            if not start_date or not end_date or not (start_date <= current_date <= end_date):
                continue
            level = self._parse_int(self._task_value(task, "level", "레벨")) or 99
            duration = (end_date - start_date).days
            phase_candidates.append((level, duration, title, start_date, end_date))

        if not phase_candidates:
            return None

        _, _, title, start_date, end_date = sorted(phase_candidates)[0]
        return {
            "title": title,
            "planned_start_date": start_date.isoformat(),
            "planned_end_date": end_date.isoformat(),
        }

    def _is_phase_title(self, title: str) -> bool:
        compact_title = title.replace(" ", "").replace("단계", "")
        return compact_title in {
            phase.replace(" ", "").replace("단계", "")
            for phase in self.WBS_PHASE_TITLES
        }

    def _parse_int(self, value: Any) -> int | None:
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None

    def _schedule_assistant_message(
        self,
        *,
        action: str,
        period: str,
        week_context: dict[str, Any],
        current_phase: dict[str, Any] | None,
        planned_tasks: list[dict[str, Any]],
        ongoing_management_tasks: list[dict[str, Any]],
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> str:
        if period_start is None or period_end is None:
            period_start, period_end = self._period_bounds(
                week_context,
                period,
                wbs_tasks=planned_tasks + ongoing_management_tasks,
            )
        period_label = {
            "TODAY": "오늘",
            "NEXT_WEEK": "다음 주",
        }.get(period, "이번 주")
        lines = [
            f"WBS 기준으로 보면 현재 프로젝트는 {week_context.get('current_week')}주차입니다.",
            f"{period_label} 범위는 {period_start.isoformat()}부터 {period_end.isoformat()}까지입니다.",
        ]
        if current_phase:
            lines.extend(
                [
                    "",
                    f"현재 핵심 단계는 {current_phase.get('title')} 단계입니다.",
                    (
                        f"WBS상 {current_phase.get('title')} 단계는 "
                        f"{current_phase.get('planned_start_date')}부터 "
                        f"{current_phase.get('planned_end_date')}까지 계획되어 있습니다."
                    ),
                ]
            )

        if planned_tasks:
            lines.extend(["", f"{period_label}에 우선 챙길 업무는 다음과 같습니다."])
            for index, task in enumerate(planned_tasks[:8], start=1):
                start_date = task.get("planned_start_date") or "기간 확인 필요"
                end_date = task.get("planned_end_date") or "기간 확인 필요"
                lines.extend(
                    [
                        "",
                        f"{index}. {task.get('title')}",
                        f"   - 기간: {start_date} ~ {end_date}",
                        f"   - 담당자: {task.get('assignee_display') or '확인 필요'}",
                        f"   - 상태: {task.get('status_display') or '확인 필요'}",
                    ]
                )
        else:
            lines.extend(["", f"{period_label}에 바로 표시할 WBS 핵심 업무는 없습니다."])

        if ongoing_management_tasks:
            ongoing_titles = ", ".join(
                str(task.get("title"))
                for task in ongoing_management_tasks[:5]
                if task.get("title")
            )
            if ongoing_titles:
                lines.extend(
                    [
                        "",
                        (
                            f"{ongoing_titles}은 전체 기간에 걸친 상시 업무로 보여 "
                            "별도 관리 항목으로 분리했습니다."
                        ),
                    ]
                )

        if action == "ASSISTANT_BRIEFING":
            lines.append("")
            lines.append("회의록 TODO가 함께 있으면 계획 대비 실제 진행 상황까지 이어서 확인할 수 있습니다.")

        return "\n".join(lines)

    def _complete_todo_result(self, context: dict[str, Any]) -> dict[str, Any]:
        target_text = str(context.get("target_text") or "").strip()
        todos = [self._normalize_todo(todo) for todo in self._context_todos(context)]
        if not todos:
            return {
                "action": "COMPLETE_TODO",
                "status": "NOT_FOUND",
                "message_key": "TODO_NOT_FOUND",
                "candidates": [],
                "missing_fields": ["todos"],
            }

        todo_id_match = re.search(r"TODO-[A-Za-z0-9-]+", target_text, re.IGNORECASE)
        if todo_id_match:
            todo_id = todo_id_match.group(0).upper()
            for todo in todos:
                if str(todo.get("todo_id") or "").upper() == todo_id:
                    return {
                        "action": "COMPLETE_TODO",
                        "status": "READY_TO_UPDATE",
                        "matched_todo": self._matched_todo(todo),
                        "candidates": [],
                    }

        scored = [
            (self._todo_match_score(target_text, todo), todo)
            for todo in todos
            if todo.get("status") != "DONE"
        ]
        candidates = [todo for score, todo in scored if score >= 2]
        if len(candidates) == 1:
            return {
                "action": "COMPLETE_TODO",
                "status": "READY_TO_UPDATE",
                "matched_todo": self._matched_todo(candidates[0]),
                "candidates": [],
            }
        if len(candidates) > 1:
            return {
                "action": "COMPLETE_TODO",
                "status": "CLARIFICATION_REQUIRED",
                "message_key": "AMBIGUOUS_TODO_MATCH",
                "candidates": [
                    {
                        "todo_id": todo.get("todo_id"),
                        "title": todo.get("title"),
                        "assignee": todo.get("assignee"),
                        "due_date": todo.get("due_date"),
                        "status": todo.get("status"),
                    }
                    for todo in candidates
                ],
            }
        return {
            "action": "COMPLETE_TODO",
            "status": "NOT_FOUND",
            "message_key": "TODO_NOT_FOUND",
            "candidates": [],
        }

    def _matched_todo(self, todo: dict[str, Any]) -> dict[str, Any]:
        return {
            "todo_id": todo.get("todo_id"),
            "title": todo.get("title"),
            "next_status": "DONE",
        }

    def _todo_match_score(self, target_text: str, todo: dict[str, Any]) -> int:
        query = self._normalize_match_text(target_text)
        title = self._normalize_match_text(str(todo.get("title") or ""))
        if not query or not title:
            return 0
        if title in query or query in title:
            return max(len(query), len(title))
        compact_query = self._compact_match_text(query)
        compact_title = self._compact_match_text(title)
        if compact_query and compact_title and (
            compact_title in compact_query or compact_query in compact_title
        ):
            return max(len(compact_query), len(compact_title))
        query_tokens = self._match_tokens(query)
        title_tokens = self._match_tokens(title)
        return len(query_tokens & title_tokens)

    def _normalize_match_text(self, value: str) -> str:
        text = str(value or "").lower()
        for token in (
            "완료했습니다",
            "완료했어",
            "완료",
            "끝났어",
            "끝냈어",
            "끝났습니다",
            "끝",
            "처리했습니다",
            "처리했어",
            "처리",
            "했습니다",
            "했어",
            "했어요",
            "업무",
            "todo",
            "done",
            "complete",
        ):
            text = text.replace(token, " ")
        return " ".join(text.split())

    def _compact_match_text(self, value: str) -> str:
        compact = re.sub(r"[^0-9a-z가-힣]+", "", self._normalize_match_text(value))
        for token in ("그리고", "및", "and", "와", "과"):
            compact = compact.replace(token, "")
        return compact

    def _match_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in re.split(r"[^0-9a-z가-힣]+", value)
            if len(token) >= 2
        }

    def _project_week_context(
        self,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str], str]:
        project = context.get("project") if isinstance(context.get("project"), dict) else {}
        start_date = self._parse_date(
            project.get("start_date")
            or project.get("startDate")
            or context.get("project_start_date")
            or context.get("projectStartDate")
        )
        current_date = self._current_date(context)
        wbs_tasks = self._context_wbs_tasks(context)
        inferred_start_date, inferred_end_date = self._wbs_project_bounds(wbs_tasks)
        if start_date is None:
            start_date = inferred_start_date
        if start_date is None:
            missing_field = "wbs.task_period" if wbs_tasks else "project.start_date"
            return (
                {
                    "current_date": current_date.isoformat(),
                    "project_start_date": None,
                    "project_end_date": inferred_end_date.isoformat()
                    if inferred_end_date
                    else None,
                    "wbs_task_count": len(wbs_tasks),
                },
                [missing_field],
                "REQUIRED_INFO",
            )

        end_date = self._parse_date(project.get("end_date") or project.get("endDate"))
        if end_date is None:
            end_date = inferred_end_date
        week_start, week_end, current_week = self._project_week_bounds(
            project_start=start_date,
            current_date=current_date,
        )
        week_context = {
            "project_start_date": start_date.isoformat(),
            "project_end_date": end_date.isoformat() if end_date else None,
            "current_date": current_date.isoformat(),
            "current_week": current_week,
            "current_week_no": current_week,
            "week_start_date": week_start.isoformat(),
            "week_end_date": week_end.isoformat(),
            "wbs_task_count": len(wbs_tasks),
        }
        if current_date < start_date:
            return (week_context, [], "BEFORE_PROJECT_START")
        if end_date and current_date > end_date:
            return (week_context, [], "AFTER_PROJECT_END")

        return (week_context, [], "SUCCESS")

    def _project_week_bounds(
        self,
        *,
        project_start: date,
        current_date: date,
    ) -> tuple[date, date, int]:
        current_week = max(((current_date - project_start).days // 7) + 1, 1)
        week_start = project_start + timedelta(days=(current_week - 1) * 7)
        return week_start, week_start + timedelta(days=6), current_week

    def _week_bounds(self, current_date: date) -> tuple[date, date]:
        week_start = current_date - timedelta(days=current_date.weekday())
        return week_start, week_start + timedelta(days=6)

    def _current_date(self, context: dict[str, Any]) -> date:
        return self._parse_date(context.get("current_date")) or date.today()

    def _parse_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)) and 1 <= float(value) <= 100000:
            return date(1899, 12, 30) + timedelta(days=int(float(value)))
        text = str(value).strip()
        if not text:
            return None
        text = text.split("T", 1)[0].strip()
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

        patterns = [
            r"^(20\d{2})[./-](\d{1,2})[./-](\d{1,2})$",
            r"^(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                year, month, day = (int(part) for part in match.groups())
                try:
                    return date(year, month, day)
                except ValueError:
                    return None

        month_day_match = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})$", text)
        if month_day_match:
            month, day = (int(part) for part in month_day_match.groups())
            try:
                return date(date.today().year, month, day)
            except ValueError:
                return None

        return None

    def _context_todos(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        todos = context.get("todos") or []
        if isinstance(todos, list):
            return [todo for todo in todos if isinstance(todo, dict)]
        return []

    def _normalize_todo(self, todo: dict[str, Any]) -> dict[str, Any]:
        related_artifact = todo.get("related_artifact") or todo.get("related_document")
        return {
            "todo_id": todo.get("todo_id") or todo.get("action_item_id"),
            "title": todo.get("title") or "제목 없음",
            "description": todo.get("description") or "",
            "assignee": todo.get("assignee") or todo.get("owner"),
            "due_date": todo.get("due_date"),
            "related_artifact": related_artifact,
            "related_document": todo.get("related_document") or related_artifact,
            "source_type": todo.get("source_type") or "MEETING_NOTE",
            "status": todo.get("status") or "TODO",
            "metadata": todo.get("metadata") or {},
        }

    def _normalize_action(self, context: dict[str, Any]) -> str:
        normalized_input = context.get("normalized_input") or {}
        action = (
            context.get("action")
            or context.get("schedule_action")
            or normalized_input.get("schedule_action")
            or self.DEFAULT_ACTION
        )
        return str(action or self.DEFAULT_ACTION).upper()

    def _extract_source_document_id(
        self,
        context: dict[str, Any],
        documents: list[dict],
    ) -> str | None:
        source_document_ids = context.get("source_document_ids") or []
        if isinstance(source_document_ids, str):
            return source_document_ids
        if isinstance(source_document_ids, list) and source_document_ids:
            return str(source_document_ids[0])

        for document in documents:
            document_id = document.get("document_id")
            if document_id:
                return str(document_id)
        return None

    def _extract_source_chunk_ids(self, documents: list[dict]) -> list[str]:
        return [
            str(document.get("chunk_id"))
            for document in documents
            if document.get("chunk_id")
        ]

    def _success(self, result: dict[str, Any]) -> AgentResponse:
        return AgentResponse(agent_name=self.AGENT_NAME, result=result)


schedule_management_agent = ScheduleManagementAgent()
