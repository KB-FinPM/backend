"""Curated Korean PM command normalization.

This module is intentionally separate from document RAG. It normalizes short
user commands only, using reviewed typo/synonym replacements.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class CommandCorrection:
    source: str
    target: str
    type: str = "typo"

    def __iter__(self):
        yield "source", self.source
        yield "target", self.target
        yield "type", self.type


@dataclass(frozen=True)
class NormalizedCommand:
    original_text: str
    normalized_text: str
    corrections: list[CommandCorrection]


class KoreanCommandNormalizer:
    """Normalize high-signal PM domain command terms without touching names."""

    REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
        ("액션 아이탬", "액션아이템", "typo"),
        ("action items", "액션아이템", "synonym"),
        ("action item", "액션아이템", "synonym"),
        ("회이록", "회의록", "typo"),
        ("회으록", "회의록", "typo"),
        ("회의룩", "회의록", "typo"),
        ("회의녹", "회의록", "typo"),
        ("미팅록", "회의록", "synonym"),
        ("액션아이탬", "액션아이템", "typo"),
        ("액션아템", "액션아이템", "typo"),
        ("요구사항저의서", "요구사항정의서", "typo"),
        ("요구사항 저의서", "요구사항 정의서", "typo"),
        ("요구사항정위서", "요구사항정의서", "typo"),
        ("요구사항 명새서", "요구사항 명세서", "typo"),
        ("요구사항명새서", "요구사항명세서", "typo"),
        ("요구사향", "요구사항", "typo"),
        ("구축요건저의서", "구축요건정의서", "typo"),
        ("구축요건정위서", "구축요건정의서", "typo"),
        ("구축요건 졍의서", "구축요건 정의서", "typo"),
        ("RFP", "구축요건정의서", "synonym"),
        ("rfp", "구축요건정의서", "synonym"),
        ("화면 설개서", "화면설계서", "typo"),
        ("화면설꼐서", "화면설계서", "typo"),
        ("화면정의서", "화면설계서", "synonym"),
        ("UI설계서", "UI 설계서", "synonym"),
        ("UI 설계", "UI 설계서", "synonym"),
        ("ui설계서", "UI 설계서", "synonym"),
        ("ui 설계", "UI 설계서", "synonym"),
        ("단위태스트", "단위테스트", "typo"),
        ("태스트케이스", "테스트케이스", "typo"),
        ("테스트 캐이스", "테스트 케이스", "typo"),
        ("테스트캐이스", "테스트케이스", "typo"),
        ("이번쥬", "이번주", "typo"),
        ("금쥬", "이번주", "typo"),
        ("다음쥬", "다음주", "typo"),
        ("차쥬", "다음주", "synonym"),
        ("담주", "다음주", "synonym"),
        ("낼", "내일", "synonym"),
        ("완료햇어", "완료했어", "typo"),
        ("완뇨했어", "완료했어", "typo"),
        ("끝냇어", "끝냈어", "typo"),
        ("처리햇어", "처리했어", "typo"),
        ("반영햇어", "반영했어", "typo"),
        ("끗", "완료", "synonym"),
        ("블락", "BLOCKED", "synonym"),
        ("블록", "BLOCKED", "synonym"),
        ("막혔어", "BLOCKED", "synonym"),
        ("막힘", "BLOCKED", "synonym"),
        ("보류", "BLOCKED", "synonym"),
        ("진행 중", "진행중", "synonym"),
        ("ㅇㅋ", "확인", "synonym"),
        ("오키", "확인", "synonym"),
        ("오케이", "확인", "synonym"),
        ("ㄱㄱ", "진행", "synonym"),
        ("진행 ㄱ", "진행", "synonym"),
        ("ㄴㄴ", "취소", "synonym"),
        ("노노", "취소", "synonym"),
        ("ㄴ", "취소", "synonym"),
        ("취소 ㄱ", "취소", "synonym"),
        ("해야할일", "해야 할 일", "spacing"),
        ("할일", "할 일", "spacing"),
    )

    def normalize(self, message: str) -> NormalizedCommand:
        original = str(message or "")
        text = unicodedata.normalize("NFC", original).strip()
        text = self._normalize_punctuation(text)
        corrections: list[CommandCorrection] = []
        seen: set[tuple[str, str, str]] = set()

        for source, target, correction_type in self.REPLACEMENTS:
            if source not in text:
                continue
            text = text.replace(source, target)
            correction = (source, target, correction_type)
            if correction not in seen and source != target:
                corrections.append(CommandCorrection(*correction))
                seen.add(correction)

        text = self._normalize_spacing(text)
        text = text.replace("BLOCKED으로", "BLOCKED로")
        while "UI 설계서서" in text:
            text = text.replace("UI 설계서서", "UI 설계서")
        return NormalizedCommand(
            original_text=original,
            normalized_text=text,
            corrections=corrections,
        )

    def _normalize_punctuation(self, text: str) -> str:
        text = text.replace("，", ",").replace("。", ".")
        text = text.replace("？", "?").replace("！", "!")
        return text

    def _normalize_spacing(self, text: str) -> str:
        text = re.sub(r"\bWBS\b", "WBS", text, flags=re.IGNORECASE)
        text = re.sub(r"\bTODO\b", "TODO", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text
