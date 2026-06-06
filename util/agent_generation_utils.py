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
        title = str(
            item.get("requirement_name")
            or item.get("title")
            or item.get("feature")
            or item.get("description")
            or f"Requirement {requirement_id}"
        ).strip()
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
                requirement_name=truncate_text(str(item.get("requirement_name") or title), 120),
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


def atoms_to_requirement_artifact(atoms: list[RequirementAtom], project_id: str, generated_by: str) -> dict[str, Any]:
    return {
        "artifact_type": "REQUIREMENT_SPEC",
        "requirements": [
            {
                "requirement_id": atom.requirement_id,
                "title": atom.title,
                "description": atom.description,
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



def _normalize_header_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").replace("\n", "").strip()).lower()



COMPOUND_SPLIT_PATTERN = re.compile(
    r"(?=(?:^|\n|\s)(?:[-*•ㅇ○·]|\d+[.)]|[①②③④⑤⑥⑦⑧⑨⑩]|[ㄱ-ㅎ]\.))"
)


def _clean_cell_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\\n", "\n")).strip()


def _looks_like_requirement_detail(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    keywords = [
        "구축", "설계", "개발", "구현", "제공", "적용", "연계", "개선", "관리", "처리", "지원", "확대",
        "모니터링", "로그", "백업", "보안", "API", "화면", "조회", "등록", "수정", "삭제", "검색",
    ]
    return any(keyword.lower() in value.lower() for keyword in keywords)


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
    value = re.sub(r"\s*[/|]\s*(?=[-•ㅇ○·]|\d+[.)]|[①②③④⑤⑥⑦⑧⑨⑩])", "\n", value)
    value = re.sub(r"\s+(?=[-•ㅇ○·]\s*[^\s])", "\n", value)
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
    title = truncate_text(requirement_name or description or biz_requirement_name or requirement_id, 120)
    return RequirementAtom(
        requirement_id=requirement_id,
        title=title,
        requirement_name=title,
        description=description or title,
        priority="SHOULD",
        category=category,
        requirement_type=req_type,
        biz_requirement_id=biz_requirement_id,
        biz_requirement_name=biz_requirement_name or category or "공통",
        domain=biz_requirement_name or category or "공통",
        feature=requirement_name or biz_requirement_name or title,
        source_document_id=document.get("document_id"),
        source_chunk_ids=[str(chunk_id)] if chunk_id else [],
        acceptance_criteria=[f"{requirement_id or title} 요구사항이 충족된다."],
        rationale=metadata.get("note") or "Extracted from source requirement table.",
        metadata={
            **metadata,
            "category": category,
            "biz_requirement_id": biz_requirement_id,
            "biz_requirement_name": biz_requirement_name,
            "requirement_id": requirement_id,
            "requirement_name": title,
            "requirement_type": req_type,
            "description": description or title,
            "source_file_name": (document.get("metadata") or {}).get("source_file_name"),
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

    for document in documents or []:
        metadata = document.get("metadata") or {}
        chunk_id = document.get("chunk_id")
        for raw_line in str(document.get("text") or "").splitlines():
            if "|" not in raw_line:
                continue
            cells = [_clean_cell_text(cell) for cell in _split_pipe_row(raw_line)]
            if not cells:
                continue

            normalized_cells = [_normalize_header_name(cell) for cell in cells]
            candidate_header = _find_header_indices(cells)
            if candidate_header:
                header_indices = candidate_header
                generic_table_mode = False
                continue

            # sample_0605 input often has construction-definition tables with
            # three columns: 기능구분 | 주요내용 | 상세. Treat every following row
            # as one or more atomic requirements.
            if {"기능구분", "주요내용", "상세"}.issubset(set(normalized_cells)):
                generic_table_mode = True
                generic_indices = {
                    "category": normalized_cells.index("기능구분"),
                    "requirement_name": normalized_cells.index("주요내용"),
                    "description": normalized_cells.index("상세"),
                }
                header_indices = {}
                continue

            if generic_table_mode and generic_indices:
                def g(field: str) -> str:
                    idx = generic_indices.get(field)
                    if idx is None or idx >= len(cells):
                        return ""
                    return cells[idx].strip()
                biz_name = g("category") or "공통"
                req_name = g("requirement_name")
                detail = g("description")
                if not _looks_like_requirement_detail(f"{biz_name} {req_name} {detail}"):
                    continue
                detail_items = split_requirement_detail_items(detail)
                for detail_index, detail_item in enumerate(detail_items, start=1):
                    atomic_name = req_name
                    if len(detail_items) > 1:
                        atomic_name = truncate_text(f"{req_name} - {detail_item}", 120)
                    atoms.append(_make_atom_from_table_row(
                        document=document,
                        chunk_id=chunk_id,
                        category=_classify_category(f"{biz_name} {req_name} {detail_item}"),
                        biz_requirement_id="",
                        biz_requirement_name=biz_name,
                        requirement_id="",
                        requirement_name=atomic_name,
                        description=detail_item,
                        metadata={
                            "source": "구축요건정의서",
                            "source_doc": metadata.get("source_file_name"),
                            "raw_table_category": biz_name,
                            "raw_table_title": req_name,
                        },
                    ))
                continue

            if not header_indices:
                continue

            def get(field: str) -> str:
                idx = header_indices.get(field)
                if idx is None or idx >= len(cells):
                    return ""
                return cells[idx].strip()

            requirement_name = get("requirement_name")
            description = get("description")
            requirement_id = get("requirement_id")
            biz_name = get("biz_requirement_name")
            if not any([requirement_name, description, requirement_id, biz_name]):
                continue
            category = get("category") or _classify_category(f"{biz_name} {requirement_name} {description}")
            detail_items = split_requirement_detail_items(description) if description else [requirement_name]
            for detail_index, detail_item in enumerate(detail_items, start=1):
                # Preserve an existing BFE-* ID for the original row. When a
                # single row is split into multiple atomic requirements, suffix
                # subsequent derived IDs to keep them unique but traceable.
                derived_req_id = requirement_id
                if requirement_id and len(detail_items) > 1:
                    derived_req_id = requirement_id if detail_index == 1 else f"{requirement_id}-{detail_index:02d}"
                atomic_name = requirement_name
                if len(detail_items) > 1:
                    atomic_name = truncate_text(f"{requirement_name} - {detail_item}", 120)
                atoms.append(_make_atom_from_table_row(
                    document=document,
                    chunk_id=chunk_id,
                    category=category,
                    biz_requirement_id=get("biz_requirement_id"),
                    biz_requirement_name=biz_name or "공통",
                    requirement_id=derived_req_id,
                    requirement_name=atomic_name or detail_item,
                    description=detail_item or description or requirement_name,
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
                    },
                ))
    return atoms

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
    """Assign Biz/REQ IDs in sample-compatible BIZ-001 / REQ-0001 format."""
    biz_seq: dict[str, int] = {}
    result: list[RequirementAtom] = []
    for idx, atom in enumerate(list(atoms or []), start=1):
        biz_name = (atom.biz_requirement_name or atom.domain or atom.category or '공통').strip() or '공통'
        if biz_name not in biz_seq:
            biz_seq[biz_name] = len(biz_seq) + 1
        atom.biz_requirement_name = biz_name
        if not atom.domain:
            atom.domain = biz_name
        if not atom.biz_requirement_id:
            atom.biz_requirement_id = f"BIZ-{biz_seq[biz_name]:03d}"
        # Preserve source requirement IDs such as BFE-21000 from existing
        # requirement tables. Only assign REQ-0001 style IDs when the source did
        # not provide one or when it is a generated placeholder.
        current_id = (atom.requirement_id or '').strip()
        if (
            not current_id
            or current_id.startswith(('RQ-', 'Requirement'))
            or re.fullmatch(r'REQ-?\d+', current_id or '', flags=re.IGNORECASE)
        ):
            atom.requirement_id = f"REQ-{idx:04d}"
        else:
            atom.requirement_id = current_id
        if not atom.requirement_name:
            atom.requirement_name = atom.title or atom.feature or atom.description[:80]
        if not atom.title:
            atom.title = atom.requirement_name
        atom.acceptance_criteria = [f"{atom.requirement_id} 요구사항이 충족된다."]
        atom.metadata = {
            **(atom.metadata or {}),
            'category': atom.category,
            'biz_requirement_id': atom.biz_requirement_id,
            'biz_requirement_name': atom.biz_requirement_name,
            'requirement_name': atom.requirement_name,
            'requirement_type': atom.requirement_type,
            'domain': atom.domain,
            'feature': atom.feature,
            'note': atom.metadata.get('note') if atom.metadata.get('note') not in (None, '') else '',
        }
        result.append(atom)
    return result
