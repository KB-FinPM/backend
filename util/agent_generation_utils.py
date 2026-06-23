# EN: Shared helper functions for core artifact-generation agents.
# KO: core artifact 생성 Agent들이 공유하는 유틸리티 함수입니다.

import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable

from util.agent_template_utils import load_output_mapper, get_nested


INFRA_KEYWORDS = [
    "OCP",
    "OpenShift",
    "PaaS",
    "Kafka",
    "EFK",
    "Elastic",
    "Kibana",
    "CDC",
    "Service Mesh",
    "cluster",
    "클러스터",
    "server",
    "서버",
    "infra",
    "인프라",
    "Gateway",
    "API Gateway",
    "monitoring",
    "모니터링",
    "logging",
    "로그",
    "backup",
    "백업",
    "DB",
    "database",
    "보안",
]

DEV_KEYWORDS = [
    "화면",
    "UI",
    "UX",
    "API",
    "업무",
    "기능",
    "관리",
    "조회",
    "등록",
    "수정",
    "삭제",
    "승인",
    "결재",
    "배치",
    "프론트엔드",
    "백엔드",
]

SCREEN_KEYWORDS = [
    "화면",
    "UI",
    "UX",
    "페이지",
    "목록",
    "상세",
    "조회",
    "등록",
    "수정",
    "삭제",
    "승인",
    "결재",
    "관리",
    "검색",
    "폼",
    "대시보드",
]

NON_SCREEN_KEYWORDS = [
    "인프라",
    "서버",
    "클러스터",
    "백업",
    "배치",
    "Kafka",
    "EFK",
    "CDC",
    "Service Mesh",
    "API Gateway",
    "모니터링",
    "로그",
    "보안",
]


@dataclass
class RequirementAtom:
    requirement_id: str = ""
    title: str = ""
    requirement_name: str = ""
    description: str = ""
    priority: str = "SHOULD"
    category: str = "기능"
    requirement_type: str = "기능요구사항"
    biz_requirement_id: str = ""
    biz_requirement_name: str = ""
    domain: str = ""
    feature: str = ""
    source_document_id: str | None = None
    source_chunk_ids: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def clean_json_response(raw: str) -> str:
    value = (raw or "").strip()
    if value.startswith("```json"):
        value = value.replace("```json", "", 1).strip()
    if value.startswith("```"):
        value = value.replace("```", "", 1).strip()
    if value.endswith("```"):
        value = value[:-3].strip()
    return value


def parse_json_object(raw: str) -> dict[str, Any] | None:
    value = clean_json_response(raw)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_json_array(raw: str) -> list[dict[str, Any]]:
    value = clean_json_response(raw)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", value, flags=re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def truncate_text(text: Any, max_chars: int = 500) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    candidate = value[:max_chars]
    boundaries = [candidate.rfind(token) for token in [". ", "? ", "! ", "\n", "다.", "요.", " ", ","]]
    boundary = max(boundaries)
    if boundary > int(max_chars * 0.65):
        candidate = candidate[: boundary + 1]
    return candidate.rstrip() + "..."


def build_title(text: str, fallback: str) -> str:
    first_line = str(text or "").splitlines()[0].strip() if str(text or "").strip() else ""
    first_sentence = first_line.split(".")[0].strip()
    return truncate_text(first_sentence or fallback, 80)


def normalize_requirement_atoms(result: Any, documents: list[dict[str, Any]] | None = None) -> list[RequirementAtom]:
    if isinstance(result, dict) and isinstance(result.get("requirements"), list):
        raw_items = result["requirements"]
    elif isinstance(result, list):
        raw_items = result
    else:
        raw_items = []

    atoms: list[RequirementAtom] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or item.get("id") or f"RQ-{index:03d}").strip()
        title = _clean_requirement_name_text(str(
            item.get("requirement_name")
            or item.get("title")
            or item.get("feature")
            or item.get("description")
            or f"Requirement {requirement_id}"
        ))
        description = str(item.get("description") or item.get("raw_text") or title).strip()
        source_chunk_ids = item.get("source_chunk_ids") or []
        if isinstance(source_chunk_ids, str):
            source_chunk_ids = [source_chunk_ids]
        source_chunk_id = item.get("source_chunk_id")
        if source_chunk_id and source_chunk_id not in source_chunk_ids:
            source_chunk_ids.append(source_chunk_id)
        acceptance_criteria = item.get("acceptance_criteria") or []
        if isinstance(acceptance_criteria, str):
            acceptance_criteria = [acceptance_criteria]
        atoms.append(
            RequirementAtom(
                requirement_id=requirement_id,
                title=truncate_text(title, 120),
                requirement_name=truncate_text(
                    _clean_requirement_name_text(str(item.get("requirement_name") or title)),
                    120,
                ),
                description=truncate_text(description, 700),
                priority=str(item.get("priority") or "SHOULD"),
                category=str(item.get("category") or item.get("requirement_type") or "기능"),
                requirement_type=str(item.get("requirement_type") or "기능요구사항"),
                biz_requirement_id=str(item.get("biz_requirement_id") or ""),
                biz_requirement_name=str(item.get("biz_requirement_name") or item.get("domain") or item.get("category") or "공통"),
                domain=str(item.get("domain") or item.get("biz_requirement_name") or item.get("category") or "공통"),
                feature=str(item.get("feature") or title),
                source_document_id=item.get("source_document_id") or item.get("source_doc") or item.get("document_id"),
                source_chunk_ids=[str(x) for x in source_chunk_ids if x],
                acceptance_criteria=[str(x) for x in acceptance_criteria if x] or [f"{requirement_id} 요구사항이 충족된다."],
                rationale=str(item.get("rationale") or item.get("note") or "Generated from source document context."),
                metadata={k: v for k, v in item.items() if k not in {"requirement_id", "title", "description", "priority", "acceptance_criteria"}},
            )
        )

    if atoms:
        return atoms

    if documents:
        json_items: list[dict[str, Any]] = []
        for document in documents:
            metadata = document.get("metadata") or {}
            requirement = metadata.get("requirement")
            if isinstance(requirement, dict):
                json_items.append(requirement)
                continue
            parsed = parse_json_object(str(document.get("text", "")))
            if parsed and isinstance(parsed.get("requirements"), list):
                json_items.extend(
                    item for item in parsed["requirements"] if isinstance(item, dict)
                )
        if json_items:
            return normalize_requirement_atoms(json_items, documents=None)

    if not documents:
        return atoms

    for index, document in enumerate(documents, start=1):
        text = str(document.get("text", "")).strip()
        if not text:
            continue
        requirement_id = f"RQ-{index:03d}"
        chunk_id = document.get("chunk_id")
        atoms.append(
            RequirementAtom(
                requirement_id=requirement_id,
                title=build_title(text, f"Requirement {requirement_id}"),
                requirement_name=build_title(text, f"Requirement {requirement_id}"),
                description=truncate_text(text, 700),
                biz_requirement_name=str(document.get("section_title") or "공통"),
                domain=str(document.get("section_title") or "공통"),
                feature=build_title(text, f"Requirement {requirement_id}"),
                source_document_id=document.get("document_id"),
                source_chunk_ids=[str(chunk_id)] if chunk_id else [],
                acceptance_criteria=[f"{requirement_id} 요구사항이 충족된다."],
                rationale="Drafted from retrieved project document chunk.",
            )
        )
    return atoms


def _requirement_description(atom: RequirementAtom) -> str:
    return (
        str(atom.description or "").strip()
        or str(atom.title or "").strip()
        or str(atom.requirement_name or "").strip()
        or str(atom.feature or "").strip()
        or str(atom.biz_requirement_name or "").strip()
        or str(atom.requirement_id or "").strip()
        or "요구사항 상세 설명 확인 필요"
    )


def looks_like_requirement_identifier(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) > 40:
        return False
    # Titles/business names are often repeated and must not become requirement IDs.
    if re.search(r"[가-힣]{2,}", text):
        return False
    return bool(
        re.fullmatch(
            r"(?:BFE|BSR|REQ|RQ|FR|NFR|IF|UI|UT|WBS)[-_]?\d+(?:[-_]\d+)?",
            text,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(r"\d{1,8}", text)
    )


def atoms_to_requirement_artifact(atoms: list[RequirementAtom], project_id: str, generated_by: str) -> dict[str, Any]:
    return {
        "artifact_type": "REQUIREMENT_SPEC",
        "requirements": [
            {
                "requirement_id": atom.requirement_id,
                "title": atom.title,
                "description": _requirement_description(atom),
                "priority": atom.priority,
                "source_document_id": atom.source_document_id,
                "source_chunk_ids": atom.source_chunk_ids,
                "acceptance_criteria": atom.acceptance_criteria,
                "rationale": atom.rationale,
                "metadata": {
                    **atom.metadata,
                    "category": atom.category,
                    "requirement_type": atom.requirement_type,
                    "biz_requirement_id": atom.biz_requirement_id,
                    "biz_requirement_name": atom.biz_requirement_name,
                    "domain": atom.domain,
                    "feature": atom.feature,
                    "requirement_name": atom.requirement_name or atom.title,
                },
            }
            for atom in atoms
        ],
        "metadata": {
            "project_id": project_id,
            "generated_by": generated_by,
            "source_requirement_count": len(atoms),
        },
    }


def classify_project_type(text: str = "", atoms: Iterable[RequirementAtom] = (), configured: str = "auto") -> str:
    if configured and configured != "auto":
        return configured
    corpus = text or ""
    for atom in atoms or []:
        corpus += f" {atom.category} {atom.domain} {atom.feature} {atom.title} {atom.description}"
    infra_score = sum(1 for keyword in INFRA_KEYWORDS if keyword.lower() in corpus.lower())
    dev_score = sum(1 for keyword in DEV_KEYWORDS if keyword.lower() in corpus.lower())
    if infra_score >= 3 and dev_score >= 3:
        return "hybrid"
    if infra_score > dev_score:
        return "infra"
    if dev_score > 0:
        return "development"
    return "hybrid"


def phase_names(project_type: str) -> list[str]:
    if project_type == "infra":
        return ["분석", "설계", "개발환경 구축", "스테이징 구축", "운영 구축"]
    if project_type == "development":
        return ["분석", "설계", "개발", "테스트", "운영 이행"]
    return ["분석", "설계", "개발/구축", "스테이징 검증", "운영 이행"]


def group_atoms_by_biz(atoms: Iterable[RequirementAtom]) -> OrderedDict[str, list[RequirementAtom]]:
    grouped: OrderedDict[str, list[RequirementAtom]] = OrderedDict()
    for atom in atoms:
        key = (atom.biz_requirement_name or atom.domain or atom.category or "공통").strip() or "공통"
        grouped.setdefault(key, []).append(atom)
    return grouped


def is_screen_related(atom: RequirementAtom) -> bool:
    corpus = f"{atom.category} {atom.requirement_type} {atom.biz_requirement_name} {atom.domain} {atom.feature} {atom.title} {atom.description}"
    score = sum(1 for keyword in SCREEN_KEYWORDS if keyword.lower() in corpus.lower())
    non_screen_score = sum(1 for keyword in NON_SCREEN_KEYWORDS if keyword.lower() in corpus.lower())
    return score > 0 and non_screen_score < 3


def _requirement_dedupe_key(atom: RequirementAtom) -> tuple[str, str, str, str, str]:
    return (
        str(atom.category or '').strip(),
        str(atom.biz_requirement_name or atom.domain or '').strip(),
        str(atom.requirement_name or atom.title or '').strip(),
        str(atom.requirement_type or '').strip(),
        str(atom.description or '').strip()[:120],
    )


def _build_requirement_acceptance_criteria(atom: RequirementAtom) -> list[str]:
    corpus = " ".join(
        str(value or "").lower()
        for value in (
            atom.requirement_name,
            atom.title,
            atom.description,
            atom.biz_requirement_name,
            atom.domain,
            atom.feature,
        )
    )
    criteria: list[str] = []
    if any(keyword in corpus for keyword in ("조회", "검색", "list", "find")):
        criteria.extend(
            [
                "검색 조건을 입력하면 대상 데이터 목록을 조회할 수 있다.",
                "조회 결과는 목록 또는 응답으로 정상 표시된다.",
            ]
        )
    if any(keyword in corpus for keyword in ("등록", "저장", "추가", "create", "insert")):
        criteria.extend(
            [
                "필수 항목 검증 후 등록 또는 저장 처리를 수행할 수 있다.",
                "저장 완료 시 신규 데이터가 즉시 반영된다.",
            ]
        )
    if any(keyword in corpus for keyword in ("수정", "변경", "update", "edit")):
        criteria.extend(
            [
                "선택한 대상의 정보를 수정할 수 있다.",
                "수정 결과는 목록 또는 상세 화면에 반영된다.",
            ]
        )
    if any(keyword in corpus for keyword in ("삭제", "remove", "delete")):
        criteria.extend(
            [
                "삭제 대상 선택 후 삭제 처리를 수행할 수 있다.",
                "삭제 완료 시 대상 데이터가 목록에서 제거된다.",
            ]
        )
    if any(keyword in corpus for keyword in ("승인", "반려", "결재", "approve", "reject")):
        criteria.extend(
            [
                "승인 권한이 있는 사용자만 승인 또는 반려 처리를 할 수 있다.",
                "승인 또는 반려 시 처리 결과와 사유가 저장된다.",
            ]
        )
    if any(keyword in corpus for keyword in ("권한", "인증", "보안")):
        criteria.append("권한이 없는 사용자는 해당 기능에 접근할 수 없다.")
    if not criteria:
        criteria.append(f"{atom.requirement_id} 요구사항이 충족된다.")

    unique: list[str] = []
    for item in criteria:
        if item not in unique:
            unique.append(item)
    return unique[:4]


def _normalize_header_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").replace("\n", "").strip()).lower()



BULLET_MARKER_PATTERN = r"(?:[-*•ㅇ○·]|[oO]|\d+[.)]|[①②③④⑤⑥⑦⑧⑨⑩]|[ㄱ-ㅎ]\.)"
BULLET_LINE_PATTERN = re.compile(
    rf"^(\s*)({BULLET_MARKER_PATTERN})(?:\s+|(?=[가-힣A-Z]))(.+)$"
)
COMPOUND_SPLIT_PATTERN = re.compile(
    rf"(?=(?:^|\n|\s){BULLET_MARKER_PATTERN}(?:\s+|(?=[가-힣A-Z])))"
)


def _clean_cell_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\\n", "\n")).strip()


def _clean_description_cell_text(value: str) -> str:
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _looks_like_requirement_detail(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    keywords = [
        "구축", "설계", "개발", "구현", "제공", "적용", "연계", "개선", "관리", "처리", "지원", "확대",
        "모니터링", "로그", "백업", "보안", "API", "화면", "조회", "등록", "수정", "삭제", "검색",
        "기능", "입력", "거래",
    ]
    return any(keyword.lower() in value.lower() for keyword in keywords)


EXCLUDED_REQUIREMENT_SECTION_KEYWORDS = [
    "개요",
    "범위",
    "배경",
    "일정",
    "조직도",
    "별첨",
]

TARGET_REQUIREMENT_SECTION_KEYWORDS = [
    "개정이력",
    "목차",
    "기간",
    "상세요건",
    "상세 요건",
    "수립방안",
    "수립 방안",
    "개발상세",
    "개발 상세",
    "요건내용",
    "요건 내용",
    "요구사항",
    "상세",
]


def _normalize_section_title(value: Any) -> str:
    title = str(value or "").strip()
    title = re.sub(r"^#{1,6}\s*", "", title)
    title = re.sub(r"^\d+(?:\.\d+)*\s*", "", title)
    title = title.rstrip(":：>").strip()
    return title


def _is_excluded_requirement_section(title: Any) -> bool:
    normalized = _normalize_section_title(title)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in EXCLUDED_REQUIREMENT_SECTION_KEYWORDS)


def _is_target_requirement_section(title: Any) -> bool:
    normalized = _normalize_section_title(title)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in TARGET_REQUIREMENT_SECTION_KEYWORDS)


def _looks_like_heading_line(line: str) -> bool:
    value = str(line or "").strip()
    if not value or "|" in value:
        return False
    if _looks_like_note_line(value):
        return False
    if len(value) > 80:
        return False
    return bool(
        re.match(r"^(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*\s*)?[가-힣A-Za-z0-9][가-힣A-Za-z0-9\s/_()·.-]*(?:[:：>])?$", value)
    )


def _looks_like_note_line(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(re.match(r"^(?:주|주석|note)\s*\d+\s*[\).:：]", text, flags=re.IGNORECASE))


def _looks_like_table_title_line(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or "|" in text or _looks_like_note_line(text):
        return False
    text = text.lstrip("-•ㅇ○· ").strip()
    return bool(text) and len(text) <= 100


def _is_table_divider_row(cells: list[str]) -> bool:
    values = [cell.strip() for cell in cells if cell.strip()]
    return bool(values) and all(re.fullmatch(r"[-: ]{2,}", value) for value in values)


def _is_generic_table_header(cells: list[str]) -> bool:
    normalized = {_normalize_header_name(cell) for cell in cells if cell.strip()}
    header_tokens = {
        "구분",
        "업무",
        "업무명",
        "기능구분",
        "주요내용",
        "상세",
        "상세내용",
        "기능/비기능요구사항",
        "기능비기능요구사항",
        "내용",
        "요건명",
        "요건내용",
        "요구사항명",
        "요구사항내용",
    }
    return bool(normalized) and len(normalized.intersection(header_tokens)) >= min(2, len(normalized))


def _compact_non_empty_cells(cells: list[str]) -> list[str]:
    return [cell.strip() for cell in cells if cell and cell.strip()]


def _compact_generic_cells(raw_cells: list[str]) -> list[str]:
    indices = [idx for idx, cell in enumerate(raw_cells) if _clean_cell_text(cell)]
    if len(indices) >= 3:
        return [
            _clean_cell_text(raw_cells[indices[0]]),
            _clean_cell_text(raw_cells[indices[1]]),
            _clean_description_cell_text(raw_cells[indices[2]]),
        ]
    if len(indices) == 2:
        return [
            _clean_cell_text(raw_cells[indices[0]]),
            _clean_description_cell_text(raw_cells[indices[1]]),
        ]
    return []


def _split_two_column_requirement_content(value: str) -> tuple[str, str]:
    items = _split_two_column_requirement_items(value)
    if not items:
        return "", ""
    return items[0]


def _split_requirement_name_description_items(
    requirement_name: str,
    description_value: str,
) -> list[tuple[str, str]]:
    base_name = _clean_requirement_name_text(requirement_name)
    text = str(description_value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        text = "\n".join(_restore_inline_bullet_lines(text))
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [(base_name, "")]

    items: list[tuple[str, list[str]]] = [(base_name, [])] if base_name else []
    for line in lines:
        parsed = _parse_bullet_line(line)
        if parsed is not None:
            _, marker, body = parsed
            if marker in {"o", "ㅇ"}:
                items.append((_clean_requirement_name_text(body), []))
                continue
        if not items:
            items.append((base_name or _clean_requirement_name_text(line), []))
            continue
        items[-1][1].append(line.strip())

    result: list[tuple[str, str]] = []
    for name, descriptions in items:
        description = "\n".join(descriptions).strip()
        result.append((name, description))
    return result


def _bullet_marker_group(marker: str) -> str:
    if marker in {"o", "O", "ㅇ", "○"}:
        return "circle"
    if marker in {"-", "—", "–"}:
        return "dash"
    if marker in {"*", "•", "·"}:
        return "dot"
    return marker


def _split_description_by_top_bullet(value: str) -> list[tuple[str, str]]:
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        text = "\n".join(_restore_inline_bullet_lines(text))
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    top_group = ""
    for line in lines:
        parsed = _parse_bullet_line(line)
        if parsed is not None:
            _, marker, _ = parsed
            top_group = _bullet_marker_group(marker)
            break
    if top_group != "circle":
        return []

    items: list[tuple[str, list[str]]] = []
    for line in lines:
        parsed = _parse_bullet_line(line)
        if parsed is not None:
            _, marker, body = parsed
            if _bullet_marker_group(marker) == top_group:
                items.append((_clean_requirement_name_text(body), []))
                continue
        if items:
            items[-1][1].append(line.strip())

    return [(name, "\n".join(descriptions).strip()) for name, descriptions in items if name]


def _split_two_column_requirement_items(value: str) -> list[tuple[str, str]]:
    text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        text = "\n".join(_restore_inline_bullet_lines(text))
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    first = _parse_bullet_line(lines[0])
    if first is None:
        requirement_name = _clean_requirement_name_text(lines[0])
        description = _clean_description_cell_text("\n".join(lines[1:]))
        return [(requirement_name, description or requirement_name)]

    _, _, first_text = first
    items: list[tuple[str, list[str]]] = [
        (_clean_requirement_name_text(first_text), [])
    ]
    for line in lines[1:]:
        parsed = _parse_bullet_line(line)
        if parsed is not None:
            _, _, body = parsed
            items.append((_clean_requirement_name_text(body), []))
            continue
        if items:
            items[-1][1].append(line.strip())

    result: list[tuple[str, str]] = []
    for requirement_name, descriptions in items:
        description = "\n".join(descriptions).strip()
        result.append((requirement_name, description or requirement_name))
    return result


def _restore_inline_bullet_lines(text: str) -> list[str]:
    value = str(text or "").strip()
    marker_regex = re.compile(rf"(^|\s+)({BULLET_MARKER_PATTERN})(?:\s+|(?=[가-힣A-Z]))")
    matches = list(marker_regex.finditer(value))
    if not matches:
        return [value] if value else []

    lines: list[str] = []
    first = matches[0]
    if value[: first.start()].strip():
        lines.append(value[: first.start()].strip())

    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        body = value[match.end():next_start].strip()
        if not body:
            continue
        leading = match.group(1) or ""
        indent = 0 if match.start() == 0 else max(0, len(leading) - 1)
        lines.append(f"{' ' * indent}{match.group(2)} {body}")
    return lines


def _clean_requirement_name_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(rf"^{BULLET_MARKER_PATTERN}(?:\s+|(?=[가-힣A-Z]))", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_bullet_line(value: str) -> tuple[int, str, str] | None:
    match = BULLET_LINE_PATTERN.match(str(value or ""))
    if not match:
        return None
    marker = match.group(2)
    if marker in {"o", "O"}:
        marker = "o"
    elif re.fullmatch(r"\d+[.)]", marker):
        marker = "num"
    elif marker in "①②③④⑤⑥⑦⑧⑨⑩":
        marker = "circled_num"
    return len(match.group(1).replace("\t", "    ")), marker, match.group(3).strip()


def split_requirement_detail_items(text: str) -> list[str]:
    """Split a compound requirement detail into atomic bullet-like statements.

    sample_0605 extracted atoms chunk-by-chunk and instructed the model to split
    one requirement per atom. In backend ingestion, DOCX table cell newlines can
    be flattened; this deterministic splitter restores atom-level rows for common
    구축요건정의서 patterns before the LLM fallback is used.
    """
    value = str(text or "").strip()
    if not value:
        return []
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(rf"\s*[/|]\s*(?={BULLET_MARKER_PATTERN}\s+)", "\n", value)
    value = re.sub(rf"\s+(?={BULLET_MARKER_PATTERN}\s+)", "\n", value)
    # Keep explanatory sub-bullets together unless the text is clearly very long.
    parts = [part.strip(" \n\t-•ㅇ○·") for part in re.split(COMPOUND_SPLIT_PATTERN, value) if part.strip(" \n\t-•ㅇ○·")]
    if len(parts) <= 1:
        # Split by sentence-like boundaries only for very long merged cells.
        if len(value) > 500:
            candidates = re.split(r"(?<=[다요함됨임음])\s+(?=[가-힣A-Za-z0-9])", value)
            parts = [c.strip(" -•ㅇ○·") for c in candidates if c.strip(" -•ㅇ○·")]
        else:
            parts = [value]
    result: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if len(part) < 4:
            continue
        result.append(part)
    return result or [value]


def _make_atom_from_table_row(
    *,
    document: dict[str, Any],
    chunk_id: Any,
    category: str,
    biz_requirement_id: str,
    biz_requirement_name: str,
    requirement_id: str,
    requirement_name: str,
    description: str,
    metadata: dict[str, Any],
) -> RequirementAtom:
    category = category or _classify_category(f"{biz_requirement_name} {requirement_name} {description}")
    req_type = "비기능요구사항" if category in {"비기능", "인프라", "보안", "운영"} else "기능요구사항"
    clean_requirement_name = _clean_requirement_name_text(requirement_name)
    title = truncate_text(clean_requirement_name or description or biz_requirement_name or requirement_id, 120)
    final_description = (
        str(description or "").strip()
        or str(title or "").strip()
        or str(clean_requirement_name or "").strip()
        or str(biz_requirement_name or "").strip()
        or str(requirement_id or "").strip()
        or "요구사항 상세 설명 확인 필요"
    )
    source_file_name = (document.get("metadata") or {}).get("source_file_name")
    work = metadata.get("work") or metadata.get("section_title") or metadata.get("domain") or ""
    section_category = metadata.get("section_category") or metadata.get("section_title") or metadata.get("domain") or ""
    return RequirementAtom(
        requirement_id=requirement_id,
        title=title,
        requirement_name=title,
        description=final_description,
        priority="SHOULD",
        category=category,
        requirement_type=req_type,
        biz_requirement_id=biz_requirement_id,
        biz_requirement_name=biz_requirement_name or category or "공통",
        domain=biz_requirement_name or category or "공통",
        feature=clean_requirement_name or biz_requirement_name or title,
        source_document_id=document.get("document_id"),
        source_chunk_ids=[str(chunk_id)] if chunk_id else [],
        acceptance_criteria=[f"{requirement_id or title} 요구사항이 충족된다."],
        rationale=metadata.get("note") or "Extracted from source requirement table.",
        metadata={
            **metadata,
            "category": category,
            "biz_requirement_id": biz_requirement_id,
            "biz_requirement_name": biz_requirement_name,
            "work": work,
            "section_category": section_category,
            "requirement_id": requirement_id,
            "requirement_name": title,
            "requirement_type": req_type,
            "description": final_description,
            "creation_stage": metadata.get("creation_stage") or "요구사항정의",
            "status": metadata.get("status") or "신규",
            "source": metadata.get("source") or "구축요건정의서",
            "source_file_name": source_file_name,
            "source_doc": metadata.get("source_doc") or source_file_name,
        },
    )


def _classify_category(text: str) -> str:
    value = str(text or "")
    if any(keyword.lower() in value.lower() for keyword in ["OCP", "인프라", "클러스터", "서버", "모니터링", "Service Mesh", "백업", "보안"]):
        return "인프라"
    if any(keyword.lower() in value.lower() for keyword in ["API", "EAI", "연계", "인터페이스", "Gateway"]):
        return "인터페이스"
    if any(keyword in value for keyword in ["성능", "장애", "운영", "로그", "권한", "감사"]):
        return "비기능"
    return "기능"


def _split_pipe_row(line: str) -> list[str]:
    return [cell.strip() for cell in str(line or "").split("|")]


def _find_header_indices(cells: list[str]) -> dict[str, int]:
    aliases = {
        "biz_requirement_id": ["biz요건id", "biz요건아이디", "biz요건번호", "bizid"],
        "biz_requirement_name": ["biz요건명", "biz요건", "업무", "업무명"],
        "category": ["요구사항구분", "구분", "요건구분"],
        "creation_stage": ["생성단계", "단계"],
        "status": ["상태구분", "상태"],
        "source": ["출처", "원천", "source"],
        "requirement_id": ["요구사항id", "요구사항아이디", "요구사항번호", "id"],
        "requirement_name": ["요구사항명", "요건명"],
        "description": ["기능/비기능요구사항", "기능비기능요구사항", "요구사항내용", "요구사항", "내용", "상세내용"],
        "user_auth_requirement": ["사용자권한요구사항", "권한요구사항"],
        "request_dept": ["의뢰부서", "요청부서"],
        "owner_team": ["요구사항처리담당팀", "담당팀", "처리담당팀"],
        "review_status": ["검토상태"],
        "note": ["검토의견", "비고", "note"],
        "change_requirement_id": ["변경요구사항id", "변경요구사항아이디"],
        "change_date": ["변경일"],
        "source_doc": ["근기문서", "근거문서", "근거문서명"],
        "ace": ["ace"],
    }
    normalized = [_normalize_header_name(cell) for cell in cells]
    indices: dict[str, int] = {}
    for field, names in aliases.items():
        for idx, header in enumerate(normalized):
            if header in names:
                indices[field] = idx
                break
    required = {"biz_requirement_id", "biz_requirement_name", "requirement_id", "requirement_name"}
    if len(required.intersection(indices)) < 2:
        return {}
    return indices


def extract_requirement_atoms_from_pipe_tables(documents: list[dict[str, Any]] | None) -> list[RequirementAtom]:
    """Extract requirement atoms from pipe-table text produced by DOCX parsing.

    Supports both legacy requirement-spec tables and 구축요건정의서 tables such as
    ``기능구분 | 주요내용 | 상세``. The latter is the pattern that previously
    became one large merged requirement in the integrated backend.
    """
    atoms: list[RequirementAtom] = []
    header_indices: dict[str, int] = {}
    generic_table_mode = False
    generic_indices: dict[str, int] = {}
    generic_table_kind = ""

    for document in documents or []:
        document_start_count = len(atoms)
        metadata = document.get("metadata") or {}
        chunk_id = document.get("chunk_id")
        section_title = _normalize_section_title(document.get("section_title") or "")
        current_table_title = section_title if section_title and section_title != "ROOT" else ""
        section_is_excluded = _is_excluded_requirement_section(section_title)
        has_target_section = _is_target_requirement_section(section_title)
        for raw_line in str(document.get("text") or "").splitlines():
            stripped_line = str(raw_line or "").strip()
            if not stripped_line:
                continue
            if _looks_like_note_line(stripped_line):
                continue
            if "|" not in raw_line:
                if _looks_like_table_title_line(stripped_line):
                    current_table_title = _normalize_section_title(
                        stripped_line.lstrip("-•ㅇ○· ").strip()
                    )
                    section_is_excluded = _is_excluded_requirement_section(current_table_title)
                    has_target_section = (
                        has_target_section
                        or _is_target_requirement_section(current_table_title)
                    )
                    header_indices = {}
                    generic_table_mode = False
                    generic_indices = {}
                    generic_table_kind = ""
                    continue
                if _looks_like_heading_line(stripped_line):
                    current_table_title = _normalize_section_title(stripped_line)
                    section_is_excluded = _is_excluded_requirement_section(current_table_title)
                    has_target_section = (
                        has_target_section
                        or _is_target_requirement_section(current_table_title)
                    )
                    header_indices = {}
                    generic_table_mode = False
                    generic_indices = {}
                    generic_table_kind = ""
                continue
            if section_is_excluded:
                continue
            if "|" not in raw_line:
                continue
            raw_cells = _split_pipe_row(raw_line)
            cells = [_clean_cell_text(cell) for cell in raw_cells]
            description_cells = [_clean_description_cell_text(cell) for cell in raw_cells]
            if not cells or _is_table_divider_row(cells):
                continue
            if cells and _looks_like_note_line(cells[0]):
                continue

            normalized_cells = [_normalize_header_name(cell) for cell in cells]
            candidate_header = _find_header_indices(cells)
            if candidate_header:
                header_indices = candidate_header
                generic_table_mode = False
                generic_table_kind = ""
                continue

            # sample_0605 input often has construction-definition tables with
            # three columns: 기능구분 | 주요내용 | 상세. Treat every following row
            # as one or more atomic requirements.
            if {"기능구분", "주요내용", "상세"}.issubset(set(normalized_cells)):
                generic_table_mode = True
                generic_indices = {
                    "biz_requirement_name": normalized_cells.index("기능구분"),
                    "requirement_name": normalized_cells.index("주요내용"),
                    "description": normalized_cells.index("상세"),
                }
                header_indices = {}
                generic_table_kind = "generic"
                continue
            if _is_generic_table_header(cells):
                compact_header = _compact_generic_cells(raw_cells)
                if len(compact_header) == 3:
                    generic_table_mode = True
                    generic_indices = {
                        "biz_requirement_name": 0,
                        "requirement_name": 1,
                        "description": 2,
                    }
                    header_indices = {}
                    generic_table_kind = "generic"
                elif len(compact_header) == 2:
                    generic_table_mode = True
                    if "요구사항명" in normalized_cells and (
                        "기능/비기능요구사항" in normalized_cells
                        or "기능비기능요구사항" in normalized_cells
                    ):
                        generic_indices = {
                            "requirement_name": 0,
                            "description": 1,
                        }
                        generic_table_kind = "requirement_description"
                    else:
                        generic_indices = {
                            "biz_requirement_name": 0,
                            "requirement_name": 0,
                            "description": 1,
                        }
                        generic_table_kind = "generic"
                    header_indices = {}
                continue

            if generic_table_mode and generic_indices:
                compact_cells = _compact_generic_cells(raw_cells)
                if len(compact_cells) >= 3:
                    generic_cells = compact_cells[:3]
                    generic_indices = {
                        "biz_requirement_name": 0,
                        "requirement_name": 1,
                        "description": 2,
                    }
                elif len(compact_cells) == 2:
                    table_title = current_table_title or document.get("section_title") or "공통"
                    raw_values = [cell for cell in raw_cells if _clean_cell_text(cell)]
                    content_value = raw_values[1] if len(raw_values) > 1 else compact_cells[1]
                    top_bullet_items: list[tuple[str, str]] = []
                    if generic_table_kind == "requirement_description":
                        biz_name = compact_cells[0] or "공통"
                        split_items = _split_requirement_name_description_items(
                            compact_cells[0],
                            content_value,
                        )
                    else:
                        biz_name = compact_cells[0] or "공통"
                        top_bullet_items = _split_description_by_top_bullet(content_value)
                        split_items = (
                            top_bullet_items
                            or [(biz_name, content_value)]
                        )
                    for req_name, detail in split_items:
                        if not _looks_like_requirement_detail(f"{biz_name} {req_name} {detail}"):
                            continue
                        atom = _make_atom_from_table_row(
                            document=document,
                            chunk_id=chunk_id,
                            category="기능",
                            biz_requirement_id="",
                            biz_requirement_name=biz_name,
                            requirement_id="",
                            requirement_name=req_name,
                            description=detail,
                            metadata={
                                "source": "구축요건정의서",
                                "source_doc": metadata.get("source_file_name"),
                                "raw_table_category": biz_name,
                                "raw_table_title": req_name,
                                "section_title": _normalize_section_title(table_title),
                                "work": _normalize_section_title(table_title),
                                "section_category": _normalize_section_title(table_title),
                                "preserve_empty_description": (
                                    generic_table_kind == "requirement_description"
                                    or bool(top_bullet_items)
                                ),
                            },
                        )
                        if table_title:
                            atom.domain = _normalize_section_title(table_title)
                            atom.metadata["domain"] = atom.domain
                        atoms.append(atom)
                    continue
                else:
                    continue

                def g(field: str) -> str:
                    idx = generic_indices.get(field)
                    if idx is None or idx >= len(generic_cells):
                        return ""
                    return generic_cells[idx].strip()

                biz_name = g("biz_requirement_name") or "공통"
                req_name = g("requirement_name")
                detail = g("description")
                table_title = current_table_title or document.get("section_title") or "공통"
                split_items = _split_description_by_top_bullet(detail)
                if split_items:
                    for split_req_name, split_detail in split_items:
                        if not _looks_like_requirement_detail(f"{biz_name} {split_req_name} {split_detail}"):
                            continue
                        atom = _make_atom_from_table_row(
                            document=document,
                            chunk_id=chunk_id,
                            category="기능",
                            biz_requirement_id="",
                            biz_requirement_name=biz_name,
                            requirement_id="",
                            requirement_name=split_req_name,
                            description=split_detail,
                            metadata={
                                "source": "구축요건정의서",
                                "source_doc": metadata.get("source_file_name"),
                                "raw_table_category": biz_name,
                                "raw_table_title": req_name,
                                "section_title": _normalize_section_title(table_title),
                                "work": _normalize_section_title(table_title),
                                "section_category": _normalize_section_title(table_title),
                                "preserve_empty_description": True,
                            },
                        )
                        if table_title:
                            atom.domain = _normalize_section_title(table_title)
                            atom.metadata["domain"] = atom.domain
                        atoms.append(atom)
                    continue
                if not _looks_like_requirement_detail(f"{biz_name} {req_name} {detail}"):
                    continue
                atom = _make_atom_from_table_row(
                    document=document,
                    chunk_id=chunk_id,
                    category="기능",
                    biz_requirement_id="",
                    biz_requirement_name=biz_name,
                    requirement_id="",
                    requirement_name=req_name,
                    description=detail,
                    metadata={
                        "source": "구축요건정의서",
                        "source_doc": metadata.get("source_file_name"),
                        "raw_table_category": biz_name,
                        "raw_table_title": req_name,
                        "section_title": _normalize_section_title(table_title),
                        "work": _normalize_section_title(table_title),
                        "section_category": _normalize_section_title(table_title),
                    },
                )
                if table_title:
                    atom.domain = _normalize_section_title(table_title)
                    atom.metadata["domain"] = atom.domain
                atoms.append(atom)
                continue

            compact_cells = _compact_generic_cells(raw_cells)
            if not header_indices and len(compact_cells) in {2, 3} and (
                has_target_section or current_table_title
            ):
                generic_table_mode = True
                generic_table_kind = "generic"
                if len(compact_cells) == 3:
                    generic_indices = {
                        "biz_requirement_name": 0,
                        "requirement_name": 1,
                        "description": 2,
                    }
                else:
                    biz_name = compact_cells[0] or "공통"
                    table_title = current_table_title or document.get("section_title") or "공통"
                    raw_values = [cell for cell in raw_cells if _clean_cell_text(cell)]
                    content_value = raw_values[1] if len(raw_values) > 1 else compact_cells[1]
                    top_bullet_items = _split_description_by_top_bullet(content_value)
                    split_items = (
                        top_bullet_items
                        or [(biz_name, content_value)]
                    )
                    for req_name, detail in split_items:
                        if not _looks_like_requirement_detail(f"{biz_name} {req_name} {detail}"):
                            continue
                        atom = _make_atom_from_table_row(
                            document=document,
                            chunk_id=chunk_id,
                            category="기능",
                            biz_requirement_id="",
                            biz_requirement_name=biz_name,
                            requirement_id="",
                            requirement_name=req_name or detail,
                            description=detail,
                            metadata={
                                "source": "구축요건정의서",
                                "source_doc": metadata.get("source_file_name"),
                                "raw_table_category": biz_name,
                                "raw_table_title": req_name,
                                "section_title": _normalize_section_title(table_title),
                                "work": _normalize_section_title(table_title),
                                "section_category": _normalize_section_title(table_title),
                                "preserve_empty_description": bool(top_bullet_items),
                            },
                        )
                        if table_title:
                            atom.domain = _normalize_section_title(table_title)
                            atom.metadata["domain"] = atom.domain
                        atoms.append(atom)
                    continue
                # Re-process this row now that generic mode is established.
                biz_name = compact_cells[generic_indices["biz_requirement_name"]]
                req_name = compact_cells[generic_indices["requirement_name"]]
                detail = compact_cells[generic_indices["description"]]
                table_title = current_table_title or document.get("section_title") or "공통"
                split_items = _split_description_by_top_bullet(detail)
                if split_items:
                    for split_req_name, split_detail in split_items:
                        if not _looks_like_requirement_detail(f"{biz_name} {split_req_name} {split_detail}"):
                            continue
                        atom = _make_atom_from_table_row(
                            document=document,
                            chunk_id=chunk_id,
                            category="기능",
                            biz_requirement_id="",
                            biz_requirement_name=biz_name or "공통",
                            requirement_id="",
                            requirement_name=split_req_name,
                            description=split_detail,
                            metadata={
                                "source": "구축요건정의서",
                                "source_doc": metadata.get("source_file_name"),
                                "raw_table_category": biz_name,
                                "raw_table_title": req_name,
                                "section_title": _normalize_section_title(table_title),
                                "work": _normalize_section_title(table_title),
                                "section_category": _normalize_section_title(table_title),
                                "preserve_empty_description": True,
                            },
                        )
                        if table_title:
                            atom.domain = _normalize_section_title(table_title)
                            atom.metadata["domain"] = atom.domain
                        atoms.append(atom)
                    continue
                if not _looks_like_requirement_detail(f"{biz_name} {req_name} {detail}"):
                    continue
                atom = _make_atom_from_table_row(
                    document=document,
                    chunk_id=chunk_id,
                    category="기능",
                    biz_requirement_id="",
                    biz_requirement_name=biz_name or "공통",
                    requirement_id="",
                    requirement_name=req_name or detail,
                    description=detail,
                    metadata={
                        "source": "구축요건정의서",
                        "source_doc": metadata.get("source_file_name"),
                        "raw_table_category": biz_name,
                        "raw_table_title": req_name,
                        "section_title": _normalize_section_title(table_title),
                        "work": _normalize_section_title(table_title),
                        "section_category": _normalize_section_title(table_title),
                    },
                )
                if table_title:
                    atom.domain = _normalize_section_title(table_title)
                    atom.metadata["domain"] = atom.domain
                atoms.append(atom)
                continue

            if not header_indices:
                continue

            def get(field: str) -> str:
                idx = header_indices.get(field)
                if idx is None or idx >= len(cells):
                    return ""
                if field in {"description", "note"}:
                    return description_cells[idx].strip()
                return cells[idx].strip()

            requirement_name = get("requirement_name")
            description = get("description")
            requirement_id = get("requirement_id")
            biz_name = get("biz_requirement_name")
            if not any([requirement_name, description, requirement_id, biz_name]):
                continue
            category = get("category") or _classify_category(f"{biz_name} {requirement_name} {description}")
            split_items = _split_description_by_top_bullet(description)
            if split_items:
                detail_items = [detail for _, detail in split_items]
                requirement_names = [name for name, _ in split_items]
            else:
                detail_items = [description] if description else [requirement_name]
                requirement_names = [requirement_name for _ in detail_items]
            for detail_index, detail_item in enumerate(detail_items, start=1):
                # Preserve an existing BFE-* ID for the original row. When a
                # single row is split into multiple atomic requirements, suffix
                # subsequent derived IDs to keep them unique but traceable.
                derived_req_id = requirement_id
                if requirement_id and len(detail_items) > 1:
                    derived_req_id = requirement_id if detail_index == 1 else f"{requirement_id}-{detail_index:02d}"
                atomic_name = requirement_names[detail_index - 1]
                if len(detail_items) > 1:
                    atomic_name = truncate_text(atomic_name, 120)
                atoms.append(_make_atom_from_table_row(
                    document=document,
                    chunk_id=chunk_id,
                    category=category,
                    biz_requirement_id=get("biz_requirement_id"),
                    biz_requirement_name=biz_name or "공통",
                    requirement_id=derived_req_id,
                    requirement_name=atomic_name or detail_item,
                    description=detail_item if split_items else (detail_item or description or requirement_name),
                    metadata={
                        "biz_requirement_id": get("biz_requirement_id"),
                        "biz_requirement_name": biz_name,
                        "creation_stage": get("creation_stage"),
                        "status": get("status"),
                        "source": get("source") or "구축요건정의서",
                        "user_auth_requirement": get("user_auth_requirement"),
                        "request_dept": get("request_dept"),
                        "owner_team": get("owner_team"),
                        "review_status": get("review_status"),
                        "note": get("note"),
                        "change_requirement_id": get("change_requirement_id"),
                        "change_date": get("change_date"),
                        "source_doc": get("source_doc") or metadata.get("source_file_name"),
                        "ace": get("ace"),
                        "raw_table_title": requirement_name,
                        "preserve_empty_description": bool(split_items),
                    },
                ))

        # Meeting notes are often flattened into plain sentences during DOCX
        # parsing. If the table-oriented paths above produced nothing, treat the
        # remaining plain text chunk as a single atomic requirement candidate.
        if len(atoms) == document_start_count and _is_meeting_note_document(document):
            fallback_atom = _make_meeting_note_atom(document=document, chunk_id=chunk_id)
            if fallback_atom is not None:
                atoms.append(fallback_atom)
    return atoms


def _is_meeting_note_document(document: dict[str, Any]) -> bool:
    metadata = document.get("metadata") or {}
    document_type = str(
        metadata.get("document_type")
        or metadata.get("source_document_type")
        or metadata.get("documentType")
        or metadata.get("sourceDocumentType")
        or "",
    ).upper()
    if document_type in {"MEETING_NOTES", "MEETING_NOTE", "MEETING_MINUTES"}:
        return True

    haystack = " ".join(
        str(value or "")
        for value in (
            document.get("section_title"),
            metadata.get("source_file_name"),
            metadata.get("document_file_name"),
            metadata.get("file_name"),
        )
    ).lower()
    return any(keyword in haystack for keyword in ("회의록", "회의 내용", "회의내용", "미팅 내용", "미팅내용", "minutes", "meeting note", "meeting notes"))


def _make_meeting_note_atom(
    *,
    document: dict[str, Any],
    chunk_id: Any,
) -> RequirementAtom | None:
    metadata = document.get("metadata") or {}
    text = _clean_description_cell_text(document.get("text") or "")
    text = _normalize_meeting_note_text(text)
    if not _looks_like_requirement_detail(text):
        return None

    section_title = _normalize_section_title(document.get("section_title") or "")
    biz_name = section_title or "회의록"
    category = _classify_category(text)
    requirement_name = truncate_text(text, 120)
    description = truncate_text(text, 700)
    requirement_id = ""
    return _make_atom_from_table_row(
        document=document,
        chunk_id=chunk_id,
        category=category,
        biz_requirement_id="",
        biz_requirement_name=biz_name,
        requirement_id=requirement_id,
        requirement_name=requirement_name,
        description=description,
        metadata={
            "source": metadata.get("source") or "회의록",
            "source_doc": metadata.get("source_file_name"),
            "section_title": section_title or "회의록",
            "work": section_title or "회의록",
            "section_category": section_title or "회의록",
            "preserve_empty_description": False,
        },
    )


def _normalize_meeting_note_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"^#+\s*", "", value).strip()
    value = re.sub(r"^\d+(?:[-.]\d+)*\.\s*", "", value)
    value = re.sub(r"^\d+[\).]\s*", "", value)
    value = value.strip(" -•ㅇ○·")
    return re.sub(r"\s+", " ", value).strip()

def deduplicate_requirement_atoms(atoms: Iterable[RequirementAtom]) -> list[RequirementAtom]:
    """Deduplicate requirement atoms using the same grouping idea as sample_0605."""
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[RequirementAtom] = []
    for atom in atoms or []:
        key = _requirement_dedupe_key(atom)
        if key in seen:
            continue
        seen.add(key)
        result.append(atom)
    return result


def assign_requirement_ids(atoms: Iterable[RequirementAtom]) -> list[RequirementAtom]:
    """Assign Biz/REQ IDs in reference-compatible Biz-0001 / REQ-00001 format."""
    biz_seq: dict[str, int] = {}
    used_requirement_ids: set[str] = set()
    result: list[RequirementAtom] = []

    for idx, atom in enumerate(list(atoms or []), start=1):
        metadata = dict(atom.metadata or {})
        biz_name = (
            atom.biz_requirement_name
            or atom.domain
            or atom.category
            or "공통"
        ).strip() or "공통"
        if biz_name not in biz_seq:
            biz_seq[biz_name] = len(biz_seq) + 1
        atom.biz_requirement_name = biz_name
        if not atom.domain:
            atom.domain = biz_name
        if not atom.biz_requirement_id:
            atom.biz_requirement_id = f"Biz-{biz_seq[biz_name]:04d}"

        raw_id = str(atom.requirement_id or "").strip()
        current_id = raw_id
        if current_id and not looks_like_requirement_identifier(current_id):
            metadata["source_requirement_id_raw"] = current_id
            current_id = ""

        should_generate_id = (
            not current_id
            or current_id.startswith(("RQ-", "Requirement"))
            or re.fullmatch(r"REQ-?\d+", current_id or "", flags=re.IGNORECASE)
        )
        if should_generate_id:
            prefix = (
                "BSR"
                if metadata.get("source") == "구축요건정의서"
                and metadata.get("raw_table_category")
                else "REQ"
            )
            current_id = f"{prefix}-{idx:05d}"

        base_id = current_id
        suffix = 2
        while current_id in used_requirement_ids:
            current_id = f"{base_id}-{suffix:02d}"
            suffix += 1
        atom.requirement_id = current_id
        used_requirement_ids.add(current_id)

        if not atom.requirement_name:
            atom.requirement_name = atom.title or atom.feature or atom.description[:80]
        atom.requirement_name = _clean_requirement_name_text(atom.requirement_name)
        if not atom.title:
            atom.title = atom.requirement_name
        else:
            atom.title = _clean_requirement_name_text(atom.title)
        atom.acceptance_criteria = _build_requirement_acceptance_criteria(atom)
        atom.metadata = {
            **metadata,
            "category": atom.category,
            "biz_requirement_id": atom.biz_requirement_id,
            "biz_requirement_name": atom.biz_requirement_name,
            "requirement_name": atom.requirement_name,
            "requirement_type": atom.requirement_type,
            "domain": atom.domain,
            "feature": atom.feature,
            "work": metadata.get("work") or atom.domain,
            "section_category": metadata.get("section_category") or atom.domain,
            "creation_stage": metadata.get("creation_stage") or "요구사항정의",
            "status": metadata.get("status") or "신규",
            "source": metadata.get("source") or "구축요건정의서",
            "note": metadata.get("note") if metadata.get("note") not in (None, "") else "",
        }
        result.append(atom)
    return result
