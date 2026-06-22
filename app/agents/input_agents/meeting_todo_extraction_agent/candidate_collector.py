from __future__ import annotations

import html
import re

from app.agents.input_agents.meeting_todo_extraction_agent.schemas import (
    MeetingDocumentSection,
    MeetingTodoCandidate,
    StructuredMeetingDocument,
)


class MeetingTodoCandidateCollector:
    ACTION_SIGNALS = (
        "검토예정",
        "검토 예정",
        "정리 예정",
        "배포 예정",
        "공유 예정",
        "요청",
        "대응 요청",
        "빠른 대응 요청",
        "이슈로 제기 예정",
        "확정 예정",
        "확인 필요",
        "협의 필요",
        "정의 필요",
        "개발 필요",
        "필요",
        "우려",
        "완료하기로",
        "지연되고 있음",
        "까지",
        "담당",
    )
    SECTION_HINTS = (
        "관련",
        "협의",
        "이슈",
        "안건",
        "논의",
        "회의",
        "외규",
        "내규",
        "영업감사",
        "와이즈넷",
        "WiseNet",
    )
    NON_TODO_PATTERNS = (
        r"^\s*(?:No\.?|실행항목|담당자|기한)\s*(?:\||$)",
        r"^\s*\|?\s*(?:No\.?|실행항목|담당자|기한|\-+|\s*)\s*\|?\s*$",
        r"^\s*이번\s*회의에서\s*도출된\s*실행항목\s*$",
    )

    def structure(self, meeting_notes: str) -> StructuredMeetingDocument:
        text = self.normalize_text(meeting_notes)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        meeting_date = self._extract_meeting_date(text)
        sections: list[MeetingDocumentSection] = []
        current_title = "본문"
        current_lines: list[str] = []

        for line in lines:
            cleaned = self._strip_bullet(line)
            if self._looks_like_section_title(cleaned):
                self._append_section(sections, current_title, current_lines)
                current_title = cleaned
                current_lines = []
                continue
            current_lines.append(cleaned)
        self._append_section(sections, current_title, current_lines)

        if not sections:
            sections = [MeetingDocumentSection(title="본문", content=text)]

        return StructuredMeetingDocument(
            meeting_title=self._extract_labeled_value(text, ("회의명", "제목")),
            meeting_date=meeting_date,
            meeting_place=self._extract_labeled_value(text, ("장소", "회의장소")),
            agenda=self._extract_labeled_value(text, ("안건", "회의안건")),
            attendees=self._extract_attendees(text),
            sections=sections,
        )

    def collect(self, meeting_notes: str) -> tuple[StructuredMeetingDocument, list[MeetingTodoCandidate]]:
        document = self.structure(meeting_notes)
        candidates: list[MeetingTodoCandidate] = []

        for section in document.sections:
            sentences = self._section_sentences(section.content)
            for index, sentence in enumerate(sentences):
                if not self._is_candidate_sentence(sentence):
                    continue
                candidates.append(
                    self._candidate_from_sentence(
                        candidate_id=f"CAND-{len(candidates) + 1:03d}",
                        section_title=section.title,
                        sentence=sentence,
                        context_before=sentences[index - 1] if index > 0 else None,
                        context_after=sentences[index + 1]
                        if index + 1 < len(sentences)
                        else None,
                    )
                )
                if "빠른 대응 요청" in sentence and sentence.strip() != "빠른 대응 요청":
                    candidates.append(
                        self._candidate_from_sentence(
                            candidate_id=f"CAND-{len(candidates) + 1:03d}",
                            section_title=section.title,
                            sentence=sentence,
                            context_before=sentences[index - 1] if index > 0 else None,
                            context_after=sentences[index + 1]
                            if index + 1 < len(sentences)
                            else None,
                            forced_signals=["빠른 대응 요청"],
                        )
                    )

        return document, candidates

    def normalize_text(self, text: str) -> str:
        value = str(text or "")
        value = value.replace("\\r\\n", "\n").replace("\\n", "\n")
        value = value.replace("\\t", " ")
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    def _append_section(
        self,
        sections: list[MeetingDocumentSection],
        title: str,
        lines: list[str],
    ) -> None:
        content = "\n".join(line for line in lines if line.strip()).strip()
        if content:
            sections.append(MeetingDocumentSection(title=title or "본문", content=content))

    def _extract_meeting_date(self, text: str) -> str | None:
        patterns = (
            r"(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})",
            r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                year, month, day = (int(part) for part in match.groups())
                return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    def _extract_labeled_value(self, text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            match = re.search(rf"{label}\s*[:：]\s*(.+)", text)
            if match:
                return match.group(1).splitlines()[0].strip()
        return None

    def _extract_attendees(self, text: str) -> list[str]:
        value = self._extract_labeled_value(text, ("참석자", "참석"))
        if not value:
            return []
        return [
            attendee.strip()
            for attendee in re.split(r"[,/、]|및", value)
            if attendee.strip()
        ]

    def _strip_bullet(self, line: str) -> str:
        return re.sub(r"^\s*(?:[-*•]+|\d+[.)]\s+|[가-하][.)]\s+)", "", line).strip()

    def _looks_like_section_title(self, line: str) -> bool:
        if not line or len(line) > 80:
            return False
        if any(signal in line for signal in self.ACTION_SIGNALS):
            return False
        if re.search(r"[:：]\s*\S+", line):
            return False
        if line.endswith((":", "：")):
            return True
        return any(hint in line for hint in self.SECTION_HINTS) and not line.endswith(
            ("다", "요", "함", "됨")
        )

    def _section_sentences(self, content: str) -> list[str]:
        raw_parts: list[str] = []
        for line in content.splitlines():
            stripped = self._strip_bullet(line)
            raw_parts.extend(re.split(r"(?<=[.!?。])\s+|[;；]", stripped))
        return [
            sentence
            for sentence in (self._clean_sentence(part) for part in raw_parts)
            if sentence
        ]

    def _clean_sentence(self, sentence: str) -> str:
        value = self.normalize_text(sentence).strip(" \t-*•|")
        value = re.sub(r"^\d+[\).]\s+", "", value)
        return value.strip()

    def _is_candidate_sentence(self, sentence: str) -> bool:
        if not sentence or len(sentence) > 500:
            return False
        for pattern in self.NON_TODO_PATTERNS:
            if re.search(pattern, sentence):
                return False
        return any(signal in sentence for signal in self.ACTION_SIGNALS)

    def _candidate_from_sentence(
        self,
        *,
        candidate_id: str,
        section_title: str | None,
        sentence: str,
        context_before: str | None,
        context_after: str | None,
        forced_signals: list[str] | None = None,
    ) -> MeetingTodoCandidate:
        signals = forced_signals or [
            signal for signal in self.ACTION_SIGNALS if signal in sentence
        ]
        return MeetingTodoCandidate(
            candidate_id=candidate_id,
            section_title=section_title,
            source_sentence=sentence,
            context_before=context_before,
            context_after=context_after,
            signals=signals,
            raw_assignee_hint=self._extract_assignee_hint(sentence),
            raw_due_date_hint=self._extract_due_date_hint(sentence),
        )

    def _extract_assignee_hint(self, sentence: str) -> str | None:
        paren_match = re.search(
            r"\(([^()]{2,40}(?:PM|이사|감사역|팀장|개발팀|담당자|선임팀장))\)",
            sentence,
        )
        if paren_match:
            return paren_match.group(1).strip()
        team_match = re.search(r"(SI개발팀|영업감사부\s*담당자|영업감사부|[가-힣]{2,6}\s*(?:PM|이사|감사역|팀장|선임팀장))", sentence)
        return team_match.group(1).strip() if team_match else None

    def _extract_due_date_hint(self, sentence: str) -> str | None:
        patterns = (
            r"20\d{2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}",
            r"\d{1,2}\s*[./]\s*\d{1,2}\s*(?:\([^)]+\))?",
            r"\d{1,2}월\s*(?:중|\d{1,2}일)",
            r"다음\s*회의\s*전까지",
        )
        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return match.group(0).strip()
        return None
