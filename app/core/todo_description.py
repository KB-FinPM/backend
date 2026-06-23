from __future__ import annotations

import re
from typing import Any


GENERIC_DESCRIPTION_PATTERNS = (
    r"^\s*회의록(?:에서| 기반).*?(?:TODO|할\s*일|할일).*?$",
    r"^\s*WBS(?:에서| 기반| 기준).*?(?:TODO|할\s*일|할일|작업).*?$",
    r"^\s*자동\s*(?:추출|등록).*?(?:TODO|할\s*일|할일).*?$",
    r"^\s*(?:근거|출처)\s*[:：].*$",
)


def normalize_todo_description(
    todo: dict[str, Any],
    *,
    source_type: Any | None = None,
) -> str:
    normalized_source_type = str(source_type or todo.get("source_type") or "").upper()
    if "WBS" in normalized_source_type:
        return build_wbs_todo_description(
            todo,
            title=todo.get("title"),
            description=todo.get("description"),
        )
    return build_meeting_todo_description(
        title=todo.get("title"),
        description=todo.get("description"),
        source_sentence=todo.get("source_sentence")
        or todo.get("source_text")
        or todo.get("evidence"),
        context_before=todo.get("context_before"),
        context_after=todo.get("context_after"),
        assignee=todo.get("assignee") or todo.get("owner"),
        due_date_text=todo.get("due_date_text") or todo.get("due_date"),
    )


def build_meeting_todo_description(
    *,
    title: Any,
    source_sentence: Any | None = None,
    description: Any | None = None,
    context_before: Any | None = None,
    context_after: Any | None = None,
    assignee: Any | None = None,
    due_date_text: Any | None = None,
) -> str:
    existing = _usable_description(description)
    if existing:
        return existing

    sentence = _clean_text(source_sentence)
    if not sentence:
        return ""

    context = _meeting_context(
        title=title,
        source_sentence=sentence,
        context_before=context_before,
        context_after=context_after,
    )
    text = _clean_meeting_sentence(
        context or sentence,
        assignee=assignee,
        due_date_text=due_date_text,
    )
    if not text:
        return ""

    text = _polish_meeting_text(text)
    if _same_meaning(text, title):
        return ""
    return _truncate_description(_ensure_sentence(text))


def build_wbs_todo_description(
    task: dict[str, Any],
    *,
    title: Any,
    description: Any | None = None,
) -> str:
    existing = _usable_description(description)
    if existing:
        return existing

    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    task_title = _clean_text(title) or _clean_text(_task_value(task, metadata, "name", "task_name", "WBS명"))
    if not task_title:
        return ""

    phase = _task_value(
        task,
        metadata,
        "phase",
        "phase_name",
        "stage",
        "stage_name",
        "parent",
        "parent_name",
        "상위 단계",
        "단계명",
    )
    deliverable = _task_value(task, metadata, "artifact", "deliverable", "산출물")
    assignee = _task_value(task, metadata, "assignee", "owner", "worker", "담당자", "작업자")
    start_date = _task_value(task, metadata, "planned_start_date", "start_date", "시작일")
    end_date = _task_value(task, metadata, "planned_end_date", "end_date", "due_date", "종료일")
    dependency = _task_value(task, metadata, "dependency", "predecessor", "선행작업")
    note = _task_value(task, metadata, "note", "notes", "remark", "remarks", "비고")

    sentences: list[str] = []
    if phase:
        sentences.append(f"{phase} 단계에서 {task_title}을 수행한다.")
    else:
        sentences.append(f"{task_title}을 수행한다.")
    if deliverable:
        sentences.append(f"관련 산출물은 {deliverable}이다.")
    if start_date and end_date:
        sentences.append(f"계획 기간은 {start_date}부터 {end_date}까지이다.")
    elif end_date:
        sentences.append(f"기한은 {end_date}이다.")
    if assignee:
        sentences.append(f"담당자는 {assignee}이다.")
    if dependency:
        sentences.append(f"선행 작업은 {dependency}이다.")
    if note:
        sentences.append(_ensure_sentence(str(note)))

    return _truncate_description(" ".join(_clean_text(sentence) for sentence in sentences if sentence))


def is_generic_todo_description(value: Any) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in GENERIC_DESCRIPTION_PATTERNS)


def _usable_description(value: Any) -> str:
    text = _clean_text(value)
    if not text or is_generic_todo_description(text):
        return ""
    return _truncate_description(text)


def _meeting_context(
    *,
    title: Any,
    source_sentence: str,
    context_before: Any | None,
    context_after: Any | None,
) -> str:
    title_text = _clean_text(title)
    before = _clean_text(context_before)
    after = _clean_text(context_after)
    source = _clean_text(source_sentence)

    parts: list[str] = []
    if before and _is_supporting_context(before, title_text, source):
        parts.append(before)
    parts.append(source)
    if after and _is_supporting_context(after, title_text, source):
        parts.append(after)
    return " ".join(parts)


def _is_supporting_context(context: str, title: str, source_sentence: str) -> bool:
    if not context or context == source_sentence:
        return False
    if len(context) > 260:
        return False
    markers = (
        "때문",
        "위해",
        "위하여",
        "지연",
        "부재",
        "문제",
        "이슈",
        "비교",
        "확인",
        "결정",
        "정의",
        "검색",
        "Knowledge",
        "영업감사",
        "WiseNet",
        "layout",
    )
    if any(marker in context for marker in markers):
        return True
    title_tokens = set(_tokenize(title))
    context_tokens = set(_tokenize(context))
    return bool(title_tokens and len(title_tokens & context_tokens) >= 2)


def _clean_meeting_sentence(
    value: str,
    *,
    assignee: Any | None,
    due_date_text: Any | None,
) -> str:
    text = _clean_text(value)
    if assignee:
        assignee_text = re.escape(_clean_text(assignee))
        compact_assignee = re.escape(_clean_text(assignee).replace(" ", ""))
        text = re.sub(rf"\(\s*{assignee_text}\s*\)", " ", text)
        text = re.sub(rf"\(\s*{compact_assignee}\s*\)", " ", text)
        text = text.replace(_clean_text(assignee), " ")
    if due_date_text:
        text = text.replace(_clean_text(due_date_text), " ")

    text = re.sub(r"\([^)]*(?:월|일|금|목|수|화|월|PM|이사|감사역|팀장|개발팀|담당자|선임팀장)[^)]*\)", " ", text)
    text = re.sub(r"20\d{2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}", " ", text)
    text = re.sub(r"\d{1,2}\s*[./]\s*\d{1,2}(?:\s*\([^)]+\))?", " ", text)
    text = re.sub(r"\d{1,2}월\s*\d{1,2}일", " ", text)
    text = re.sub(r"\d{1,2}월\s*중", " ", text)
    text = re.sub(r"\s*(?:까지|까지는)\s*", " ", text)
    return _clean_text(text)


def _polish_meeting_text(value: str) -> str:
    text = _clean_text(value)
    replacements = {
        "가능여부": "가능 여부",
        "RPA를 통해": "RPA로",
        "주간보고시": "주간보고에서",
        "layout": "layout",
        "파악하고 있는 기준으로": "파악 중인 기준으로",
        "정리하여 배포": "정리하여 배포",
        "빠른 대응 요청": "빠른 대응을 요청한다",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    text = re.sub(r"\s*검토\s*예정", " 검토한다", text)
    text = re.sub(r"\s*정리\s*예정", " 정리한다", text)
    text = re.sub(r"\s*배포\s*예정", " 배포한다", text)
    text = re.sub(r"\s*공유\s*예정", " 공유한다", text)
    text = re.sub(r"\s*확정\s*예정", " 확정한다", text)
    text = re.sub(r"\s*제기\s*예정", " 제기한다", text)
    text = re.sub(r"\s*하기로\s*하였으나", "하기로 했으나", text)
    text = re.sub(r"\s*하기로\s*(?:함|하였다|했음)?", "한다", text)
    text = re.sub(r"\s*예정\s*$", "한다", text)
    text = re.sub(r"\s*필요\s*$", "필요 여부를 확인한다", text)
    text = re.sub(r"\s+", " ", text).strip(" -:：,，.")
    return text


def _same_meaning(left: Any, right: Any) -> bool:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return False
    return left_tokens == right_tokens or left_tokens <= right_tokens


def _tokenize(value: Any) -> list[str]:
    return [
        token
        for token in re.sub(r"[^0-9a-zA-Z가-힣]+", " ", str(value or "").lower()).split()
        if len(token) >= 2
    ]


def _task_value(task: dict[str, Any], metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = task.get(key)
        if value in (None, ""):
            value = metadata.get(key)
        if value not in (None, ""):
            return _clean_text(value)
    return ""


def _ensure_sentence(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if text.endswith((".", "!", "?", "다.")):
        return text
    if text.endswith("다"):
        return f"{text}."
    return f"{text}."


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate_description(value: str, max_length: int = 700) -> str:
    text = _clean_text(value)
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."
