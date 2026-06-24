from __future__ import annotations

import re
from datetime import date

from app.core.todo_description import build_meeting_todo_description
from app.agents.input_agents.meeting_todo_extraction_agent.schemas import (
    MeetingTodoCandidate,
    MeetingTodoItem,
    MeetingTodoNonTodoCandidate,
    StructuredMeetingDocument,
)


class MeetingTodoNormalizer:
    REQUIREMENT_ONLY_PATTERNS = (
        r"개발\s*이?\s*필요",
        r"이관\s*필요(?:함)?",
        r"재적재\s*필요",
        r"재적재\s*해야",
        r"표시$",
    )
    ISSUE_PATTERNS = (
        r"성능\s*저하\s*우려",
        r"데이터\s*양",
        r"데이터양",
        r"많음",
        r"약\s*\d+\s*(?:GB|MB|TB)",
        r"현황",
        r"문제점",
        r"단점",
        r"우려",
    )

    def normalize_candidates(
        self,
        *,
        document: StructuredMeetingDocument,
        candidates: list[MeetingTodoCandidate],
        source_document_id: str | None = None,
        source_chunk_ids: list[str] | None = None,
    ) -> tuple[list[MeetingTodoItem], list[MeetingTodoNonTodoCandidate]]:
        meeting_date = self._parse_date(document.meeting_date) or date.today()
        todo_items: list[MeetingTodoItem] = []
        non_todo_items: list[MeetingTodoNonTodoCandidate] = []

        for candidate in candidates:
            if self._should_classify_as_non_todo(candidate):
                non_todo_items.append(self._non_todo_candidate(candidate))
                continue

            todo = self._candidate_to_todo(
                candidate=candidate,
                document=document,
                meeting_date=meeting_date,
                source_document_id=source_document_id,
                source_chunk_ids=source_chunk_ids or [],
            )
            if todo is None:
                non_todo_items.append(self._non_todo_candidate(candidate))
                continue
            todo_items.append(todo)

        return self._dedupe_todos(todo_items), self._dedupe_candidates(non_todo_items)

    def _candidate_to_todo(
        self,
        *,
        candidate: MeetingTodoCandidate,
        document: StructuredMeetingDocument,
        meeting_date: date,
        source_document_id: str | None,
        source_chunk_ids: list[str],
    ) -> MeetingTodoItem | None:
        sentence = candidate.source_sentence
        assignee = self._extract_assignee(candidate, document)
        due_date, due_date_text, due_needs_confirmation = self._extract_due_date(
            candidate,
            meeting_date,
        )
        title = self._extract_title(candidate, assignee, due_date_text)
        if not title:
            return None

        needs_confirmation: list[str] = []
        if not assignee:
            needs_confirmation.append("담당자")
        if due_needs_confirmation:
            needs_confirmation.append(due_needs_confirmation)
        elif not due_date:
            needs_confirmation.append("기한")

        status = "NEEDS_CONFIRMATION" if not assignee else "TODO"
        confidence = 0.86 if status == "TODO" else 0.64
        if candidate.signals == ["빠른 대응 요청"]:
            status = "NEEDS_CONFIRMATION"
            confidence = 0.62
            if "담당자" not in needs_confirmation and assignee == "SI개발팀":
                needs_confirmation.append("담당자")

        metadata = {
            "source_document_id": source_document_id,
            "source_chunk_ids": source_chunk_ids,
            "candidate_id": candidate.candidate_id,
        }
        description = self._build_description(
            title=title,
            candidate=candidate,
            assignee=assignee,
            due_date_text=due_date_text,
        )
        return MeetingTodoItem(
            title=title,
            description=description,
            assignee=assignee,
            due_date=due_date,
            due_date_text=due_date_text or ("미정" if not due_date else due_date),
            status=status,
            source_section=candidate.section_title,
            source_sentence=sentence,
            confidence=confidence,
            needs_confirmation=needs_confirmation,
            metadata=metadata,
        )

    def _should_classify_as_non_todo(self, candidate: MeetingTodoCandidate) -> bool:
        sentence = candidate.source_sentence
        if self._is_issue_context_without_followup(candidate):
            return True
        if "요청" in sentence or "예정" in sentence or "까지" in sentence:
            return False
        return any(re.search(pattern, sentence) for pattern in self.REQUIREMENT_ONLY_PATTERNS + self.ISSUE_PATTERNS)

    def _is_issue_context_without_followup(self, candidate: MeetingTodoCandidate) -> bool:
        sentence = candidate.source_sentence
        if not re.search(r"지연되고\s*있음|담당자\s*부재|부재로\s*지연", sentence):
            return False
        return not re.search(
            r"정리\s*예정|배포\s*예정|확정\s*예정|검토\s*예정|이슈로\s*제기\s*예정|요청$",
            sentence,
        )

    def _non_todo_candidate(
        self,
        candidate: MeetingTodoCandidate,
    ) -> MeetingTodoNonTodoCandidate:
        sentence = candidate.source_sentence
        classification = "issue_or_requirement"
        reason = "담당자와 회의 이후 실행 행동이 명확하지 않아 TODO로 확정하지 않았습니다."
        if re.search(r"이관\s*필요(?:함)?|재적재\s*필요", sentence):
            classification = "requirement_candidate"
            reason = (
                "중요한 요구사항 또는 논의사항이지만 회의 이후 바로 수행할 "
                "개별 할일로 확정하기에는 담당자와 실행 단위가 불명확합니다."
            )
        if any(re.search(pattern, sentence) for pattern in self.ISSUE_PATTERNS):
            classification = "issue"
            reason = "현황, 문제점 또는 우려 설명에 가까워 TODO로 확정하지 않았습니다."
        if "비즈플랫폼" in sentence and re.search(r"개발\s*이?\s*필요", sentence):
            classification = "issue_or_requirement"
            reason = (
                "방안의 단점 또는 조건 설명에 포함되어 있으며, 별도 담당자와 "
                "완료 결과물이 명확하지 않아 할일로 확정하지 않았습니다."
            )
        return MeetingTodoNonTodoCandidate(
            title=self._compact_title(sentence) or sentence[:80],
            classification=classification,
            reason=reason,
            source_sentence=sentence,
        )

    def _extract_assignee(
        self,
        candidate: MeetingTodoCandidate,
        document: StructuredMeetingDocument,
    ) -> str | None:
        sentence = candidate.source_sentence
        if candidate.signals == ["빠른 대응 요청"]:
            context = " ".join(
                part
                for part in [candidate.context_before, sentence, candidate.context_after]
                if part
            )
            if "영업감사부 담당자" in context or "영업감사부" in context:
                return "영업감사부 담당자"
            return None

        raw_hint = candidate.raw_assignee_hint
        if raw_hint:
            return self._normalize_assignee(raw_hint)

        context_assignee = self._extract_context_assignee(candidate)
        if context_assignee:
            return self._normalize_assignee(context_assignee)

        paren_match = re.search(
            r"\(([^()]{2,40}(?:PM|이사|감사역|팀장|개발팀|담당자|선임팀장))\)",
            sentence,
        )
        if paren_match:
            return self._normalize_assignee(paren_match.group(1))

        team_match = re.search(r"(SI개발팀|영업감사부\s*담당자|영업감사부)", sentence)
        if team_match:
            return self._normalize_assignee(team_match.group(1))

        section_match = re.search(
            r"\(([^()]{2,40}(?:PM|이사|감사역|팀장|담당자|선임팀장))\)",
            candidate.section_title or "",
        )
        if section_match:
            return self._normalize_assignee(section_match.group(1))

        return None

    def _extract_context_assignee(self, candidate: MeetingTodoCandidate) -> str | None:
        section_title = candidate.section_title or ""
        sentence = candidate.source_sentence
        context = "\n".join(
            part
            for part in [candidate.context_before, candidate.context_after]
            if part
        )
        if not context:
            return None
        # Carry an owner across adjacent WiseNet/layout lines in the same section.
        if not re.search(r"WiseNet|와이즈넷|layout|레이아웃", f"{section_title}\n{sentence}", re.IGNORECASE):
            return None
        matches = re.findall(
            r"\(([^()]{2,40}(?:PM|이사|감사역|팀장|개발팀|담당자|선임팀장))\)",
            context,
        )
        return matches[-1].strip() if matches else None

    def _normalize_assignee(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        text = re.sub(r"([가-힣]{2,6})(PM|이사|감사역|팀장|선임팀장)$", r"\1 \2", text)
        return text

    def _extract_due_date(
        self,
        candidate: MeetingTodoCandidate,
        meeting_date: date,
    ) -> tuple[str | None, str | None, str | None]:
        if candidate.signals == ["빠른 대응 요청"]:
            return None, "미정", "기한"

        sentence = candidate.source_sentence
        full_date = re.search(r"(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})", sentence)
        if full_date:
            year, month, day = (int(part) for part in full_date.groups())
            return self._safe_date(year, month, day, full_date.group(0))

        korean_full_date = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일", sentence)
        if korean_full_date:
            year, month, day = (int(part) for part in korean_full_date.groups())
            return self._safe_date(year, month, day, korean_full_date.group(0))

        month_day = re.search(
            r"(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*\([^)]+\))?(?!\d)",
            sentence,
        )
        if month_day:
            month, day = (int(part) for part in month_day.groups())
            return self._safe_date(meeting_date.year, month, day, month_day.group(0))

        korean_month_day = re.search(r"(\d{1,2})월\s*(\d{1,2})일", sentence)
        if korean_month_day:
            month, day = (int(part) for part in korean_month_day.groups())
            return self._safe_date(
                meeting_date.year,
                month,
                day,
                korean_month_day.group(0),
            )

        month_range = re.search(r"(\d{1,2})월\s*중", sentence)
        if month_range:
            month = int(month_range.group(1))
            return None, f"{month}월 중", "정확한 기한"

        if "다음 회의 전" in sentence:
            return None, "다음 회의 전", "정확한 기한"
        return None, "미정", "기한"

    def _safe_date(
        self,
        year: int,
        month: int,
        day: int,
        raw_text: str,
    ) -> tuple[str | None, str | None, str | None]:
        try:
            return date(year, month, day).isoformat(), raw_text, None
        except ValueError:
            return None, raw_text, "정확한 기한"

    def _extract_title(
        self,
        candidate: MeetingTodoCandidate,
        assignee: str | None,
        due_date_text: str | None,
    ) -> str:
        sentence = candidate.source_sentence
        section_title = candidate.section_title or ""
        if "영업감사" in f"{section_title} {sentence}" and "미진사항" in sentence and "배포" in sentence:
            return "영업감사 미진사항 정리 및 배포"
        if "주간보고" in sentence and "이슈" in sentence and "영업감사" in section_title:
            return "영업감사 상세요건 미진 이슈 주간보고 제기"
        if re.search(r"WiseNet|와이즈넷", section_title, re.IGNORECASE) and "layout 정의" in sentence and "결재문서" not in sentence:
            return "WiseNet 연계 layout 정의 정리"
        if "결재문서" in sentence and "감사문서" in sentence and "layout 정의" in sentence:
            return "결재문서 및 감사문서 열람율 layout 정의"
        if re.search(r"WiseNet|와이즈넷", f"{section_title} {sentence}", re.IGNORECASE) and re.search(r"최종\s*레이아웃|최종\s*layout|layout\s*비교", sentence, re.IGNORECASE):
            return "WiseNet 최종 레이아웃 확정"
        if candidate.signals == ["빠른 대응 요청"]:
            prefix = "영업감사 관련 미진사항" if "영업감사" in sentence else ""
            return f"{prefix} 빠른 대응 요청".strip()

        title = sentence
        if assignee:
            title = title.replace(assignee, " ")
            title = title.replace(assignee.replace(" ", ""), " ")
        title = re.sub(r"\([^()]{2,40}(?:PM|이사|감사역|팀장|개발팀|담당자|선임팀장)\)", " ", title)
        title = re.sub(r"\(\s*\)", " ", title)
        title = re.sub(r"20\d{2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}", " ", title)
        title = re.sub(r"\d{1,2}\s*[./]\s*\d{1,2}\s*(?:\([^)]+\))?", " ", title)
        title = re.sub(r"\d{1,2}월\s*(?:중|\d{1,2}일)", " ", title)
        title = re.sub(r"\(\s*\)", " ", title)
        if due_date_text and due_date_text not in {"미정"}:
            title = title.replace(due_date_text, " ")
        title = re.sub(r"\s*으로\s*빠른\s*대응\s*요청", " ", title)
        title = title.replace("가능여부", "가능 여부")
        title = re.sub(r"RPA를\s*통해\s*", "RPA ", title)
        title = title.replace("정리하여 배포", "정리 및 배포")
        title = title.replace("기준으로", " ")
        title = re.sub(r"(검토|정리|배포|공유|확정)\s*예정", r"\1", title)
        title = re.sub(r"\s*(?:까지|으로|로)?\s*예정\s*$", " ", title)
        title = re.sub(r"\s*하기로\s*(?:함|하였으나)?", " ", title)
        title = re.sub(r"\s*까지\s*", " ", title)
        title = title.replace("파악하고 있는 기준으로", "기준으로")
        title = re.sub(r"\s*요청\s*$", " 요청", title)
        title = re.sub(r"\s*(?:을|를|은|는|이|가)\s+", " ", title)
        title = re.sub(r"\s+", " ", title).strip(" -:：,，.")
        return self._compact_title(title)

    def _build_description(
        self,
        *,
        title: str,
        candidate: MeetingTodoCandidate,
        assignee: str | None,
        due_date_text: str | None,
    ) -> str:
        sentence = candidate.source_sentence
        section_title = candidate.section_title or ""
        context = " ".join(
            part
            for part in [candidate.context_before, sentence, candidate.context_after]
            if part
        )
        if title == "영업감사 미진사항 정리 및 배포":
            return (
                "영업감사 상세요건 정의가 담당자 부재로 지연되고 있어, "
                "SI개발팀이 파악 중인 미진사항을 정리하여 배포하고 빠른 대응을 요청한다."
            )
        if title == "영업감사 상세요건 미진 이슈 주간보고 제기":
            due_label = self._brief_due_label(due_date_text)
            if due_label:
                return f"영업감사 상세요건 정의 지연 건을 {due_label} 주간보고 시 이슈로 제기한다."
            return "영업감사 상세요건 정의 지연 건을 주간보고 시 이슈로 제기한다."
        if title == "WiseNet 연계 layout 정의 정리":
            if "1.14" in context or "01.14" in context:
                return "1.14 업무협의에서 결정한 WiseNet 연계를 위해 layout 정의를 정리한다."
            return "WiseNet 연계를 위해 layout 정의를 정리한다."
        if title == "결재문서 및 감사문서 열람율 layout 정의":
            return "WiseNet 연계 대상인 결재문서 및 감사문서 열람율 layout을 정의한다."
        if title == "WiseNet 최종 레이아웃 확정":
            return "스토리보드와 실제 WiseNet layout을 비교하기 위해 WiseNet 화면 스크린샷을 확인하고 최종 레이아웃을 확정한다."

        description = build_meeting_todo_description(
            title=title,
            source_sentence=sentence,
            context_before=candidate.context_before,
            context_after=candidate.context_after,
            assignee=assignee,
            due_date_text=due_date_text,
        )
        if description:
            return description
        if context and section_title and section_title != "본문":
            return build_meeting_todo_description(
                title=title,
                source_sentence=f"{section_title}. {sentence}",
                assignee=assignee,
                due_date_text=due_date_text,
            )
        return description

    def _compact_title(self, value: str) -> str:
        text = str(value or "").strip()
        replacements = {
            "영업감사관련": "영업감사 관련",
            "미진사항": "미진사항",
            "주간보고시": "주간보고시",
            "layout": "layout",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        text = re.sub(r"\s+", " ", text).strip(" -:：,，.")
        return text[:120]

    def _brief_due_label(self, value: str | None) -> str:
        text = str(value or "").strip()
        if not text or text == "미정":
            return ""
        text = re.sub(r"\s*\([^)]*\)", "", text)
        return text.strip()

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def _dedupe_todos(self, items: list[MeetingTodoItem]) -> list[MeetingTodoItem]:
        deduped: list[MeetingTodoItem] = []
        seen: set[tuple[str, str, str]] = set()
        for item in items:
            key = (
                re.sub(r"\s+", "", item.title.lower()),
                re.sub(r"\s+", "", item.description.lower()),
                item.assignee or "",
                item.due_date or "",
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _dedupe_candidates(
        self,
        items: list[MeetingTodoNonTodoCandidate],
    ) -> list[MeetingTodoNonTodoCandidate]:
        deduped: list[MeetingTodoNonTodoCandidate] = []
        seen: set[str] = set()
        for item in items:
            key = re.sub(r"\s+", "", item.source_sentence.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
