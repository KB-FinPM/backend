# EN: Core agent adapter for lightweight schedule/todo management.
# KO: 회의록 기반 todo 중심 일정관리를 위한 Core Agent adapter입니다.

import re
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class ScheduleManagementAgent:
    """Extracts lightweight todo items from meeting notes without persistence."""

    AGENT_NAME = "ScheduleManagementAgent"
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
    RELATED_DOCUMENT_TERMS = (
        "요구사항 명세서",
        "요구사항명세서",
        "요구사항 정의서",
        "요구사항정의서",
        "화면설계서",
        "화면 설계서",
        "WBS",
        "테스트 케이스",
        "테스트케이스",
        "회의록",
        "주간보고서",
    )
    RELATIVE_DUE_DATE_PATTERN = re.compile(
        r"((?:이번|다음|차주|금주)\s*주?\s*"
        r"(?:월요일|화요일|수요일|목요일|금요일|토요일|일요일|월|화|수|목|금|토|일))"
    )

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate requested | "
            f"project_id={request.project_id}"
        )

        context = request.context or {}
        meeting_notes = str(context.get("meeting_notes") or "").strip()
        if not meeting_notes:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="meeting_notes is required",
            )

        source_document_id = self._extract_source_document_id(context, request.documents)
        source_chunk_ids = self._extract_source_chunk_ids(request.documents)
        todos = self._extract_todos(
            meeting_notes=meeting_notes,
            source_document_id=source_document_id,
            source_chunk_ids=source_chunk_ids,
        )
        if not todos:
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error="No action items were found in meeting notes",
            )

        return AgentResponse(
            agent_name=self.AGENT_NAME,
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "todos": todos,
                "metadata": {
                    "source": "meeting_notes",
                    "extraction_strategy": "rule_based_mvp",
                    "todo_count": len(todos),
                },
            },
        )

    def _extract_todos(
        self,
        *,
        meeting_notes: str,
        source_document_id: str | None,
        source_chunk_ids: list[str],
    ) -> list[dict[str, Any]]:
        todos: list[dict[str, Any]] = []
        for sentence in self._split_candidate_sentences(meeting_notes):
            if not self._is_action_candidate(sentence):
                continue

            assignee = self._extract_assignee(sentence)
            due_date, due_metadata = self._extract_due_date(sentence)
            title = self._extract_title(sentence, assignee, due_metadata.get("raw_text"))
            if not title:
                continue
            related_document = self._extract_related_document(sentence)
            status = "TODO" if assignee and due_date else "NEEDS_CONFIRMATION"

            metadata: dict[str, Any] = {
                "source_text": sentence,
                "extraction_strategy": "rule_based_mvp",
            }
            if due_metadata.get("unparsed_due_date_text"):
                metadata["unparsed_due_date_text"] = due_metadata[
                    "unparsed_due_date_text"
                ]
            if due_metadata.get("wbs_bucket"):
                metadata["wbs_bucket"] = due_metadata["wbs_bucket"]

            todos.append(
                {
                    "todo_id": f"TODO-{len(todos) + 1:03d}",
                    "project_id": "",
                    "title": title,
                    "description": sentence,
                    "assignee": assignee,
                    "due_date": due_date,
                    "related_document": related_document,
                    "source_type": "MEETING_MINUTES",
                    "status": status,
                    "source_document_id": source_document_id,
                    "source_chunk_ids": source_chunk_ids,
                    "metadata": metadata,
                }
            )

        return todos

    def _split_candidate_sentences(self, meeting_notes: str) -> list[str]:
        normalized = meeting_notes.replace("\r\n", "\n").replace("\r", "\n")
        parts = re.split(r"(?:\n+|(?<=[.!?。])\s+|[;；])", normalized)
        sentences: list[str] = []
        for part in parts:
            sentence = self._clean_sentence(part)
            if sentence:
                sentences.append(sentence)
        return sentences

    def _clean_sentence(self, sentence: str) -> str:
        sentence = sentence.strip(" \t-*•")
        sentence = re.sub(r"^\d+[\).]\s*", "", sentence)
        sentence = re.sub(
            r"^(?:회의록|회의 내용|미팅 내용)\s*[:：-]\s*",
            "",
            sentence,
        )
        return sentence.strip()

    def _is_action_candidate(self, sentence: str) -> bool:
        normalized = sentence.lower()
        if any(phrase.lower() in normalized for phrase in self.TODO_TRIGGER_PHRASES):
            return True
        has_action_keyword = any(keyword in normalized for keyword in self.ACTION_KEYWORDS)
        has_obligation = any(
            keyword in normalized for keyword in self.OBLIGATION_KEYWORDS
        )
        due_date, due_metadata = self._extract_due_date(sentence)
        has_due_signal = bool(due_date or due_metadata.get("unparsed_due_date_text"))
        return has_action_keyword and (
            has_obligation or has_due_signal or self._extract_assignee(sentence)
        )

    def _extract_assignee(self, sentence: str) -> str | None:
        korean_owner_match = re.search(
            r"(?:담당자?|owner)\s*[:：]?\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})",
            sentence,
            re.IGNORECASE,
        )
        if korean_owner_match:
            return korean_owner_match.group(1).strip()

        korean_subject_match = re.match(
            r"^\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})(?:은|는|이|가|님은|님이)\s+",
            sentence,
        )
        if korean_subject_match:
            candidate = korean_subject_match.group(1).strip()
            if not self._is_invalid_assignee(candidate):
                return candidate

        explicit_match = re.search(
            r"(?:담당자|담당|owner)\s*[:：]\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})",
            sentence,
            re.IGNORECASE,
        )
        if explicit_match:
            return explicit_match.group(1).strip()

        korean_subject_match = re.match(
            r"^\s*([가-힣A-Za-z][가-힣A-Za-z0-9._-]{1,30})(?:님)?(?:은|는|이|가)\s+",
            sentence,
        )
        if korean_subject_match:
            candidate = korean_subject_match.group(1).strip()
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
        }

    def _extract_due_date(self, sentence: str) -> tuple[str | None, dict[str, str]]:
        iso_match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", sentence)
        if iso_match:
            year, month, day = iso_match.groups()
            return (
                f"{int(year):04d}-{int(month):02d}-{int(day):02d}",
                {"raw_text": iso_match.group(0)},
            )

        month_day_match = re.search(r"(\d{1,2})월\s*(\d{1,2})일", sentence)
        if month_day_match:
            month, day = month_day_match.groups()
            raw_text = month_day_match.group(0)
            return (
                f"{int(month)}월 {int(day)}일",
                {"raw_text": raw_text},
            )

        if "다음 회의 전까지" in sentence or "다음 회의 전" in sentence:
            raw_text = "다음 회의 전까지" if "다음 회의 전까지" in sentence else "다음 회의 전"
            return (
                "다음 회의 전",
                {
                    "raw_text": raw_text,
                    "unparsed_due_date_text": "다음 회의 전",
                },
            )

        month_end_match = re.search(r"(\d{1,2})월\s*말", sentence)
        if month_end_match:
            raw_text = month_end_match.group(0)
            return (
                raw_text,
                {
                    "raw_text": raw_text,
                    "unparsed_due_date_text": raw_text,
                    "wbs_bucket": f"{raw_text} 마일스톤",
                },
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

        relative_match = self.RELATIVE_DUE_DATE_PATTERN.search(sentence)
        if relative_match:
            raw_text = relative_match.group(1).strip()
            return (
                None,
                {
                    "raw_text": raw_text,
                    "unparsed_due_date_text": raw_text,
                },
            )

        return None, {}

    def _extract_related_document(self, sentence: str) -> str:
        lowered = sentence.lower()
        for term in self.RELATED_DOCUMENT_TERMS:
            if term.lower() in lowered:
                return "WBS" if term.upper() == "WBS" else term.replace(" ", "")
        return "회의록 기반 신규 TODO"

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
                rf"^(?:담당자|담당|owner)\s*[:：]\s*{re.escape(assignee)}\s*",
                "",
                title,
                flags=re.IGNORECASE,
            )

        if due_text:
            title = title.replace(due_text, "")
        for phrase in self.TODO_TRIGGER_PHRASES:
            title = title.replace(phrase, "")
        title = re.sub(r"(?:까지|전까지)\s*", "", title)
        title = re.sub(r"(?:까지는|까지로|까지)", "", title)
        title = re.sub(
            r"\s*(?:진행|정리|검토|확인|작성|준비|공유|전달|완료|수정|보완|업데이트|협의|확정|검증|리뷰|개발|테스트|배포)"
            r"(?:한다|합니다|했다|했습니다|하기|할 것|해 주세요|해주세요|한다\.?)?\s*$",
            "",
            title,
        )
        title = re.sub(r"\s*(?:필요|필요함|해야 함|해야함)\s*$", "", title)
        title = re.sub(r"\s*(?:을|를)\s*$", "", title)
        title = re.sub(r"\s+", " ", title)
        return title.strip(" .,:：-")

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
        chunk_ids = []
        for document in documents:
            chunk_id = document.get("chunk_id")
            if chunk_id:
                chunk_ids.append(str(chunk_id))
        return chunk_ids


schedule_management_agent = ScheduleManagementAgent()
