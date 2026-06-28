# EN: Core agent adapter for generating screen design artifacts.
# KO: 화면설계서 산출물 생성을 위한 Core Agent adapter입니다.

import json
import re
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.request import normalize_author_value
from util.agent_generation_utils import (
    RequirementAtom,
    normalize_requirement_atoms,
    parse_json_array,
    parse_json_object,
    truncate_text,
)

logger = get_logger(__name__)

SCREEN_LLM_SYSTEM_PROMPT = """
너는 PM Agent의 화면설계서 생성기다.
요구사항명세서와 구축요건정의서 맥락을 바탕으로 화면설계서 화면 목록을 JSON으로 생성하라.
반드시 JSON 객체만 반환한다.

스키마:
{
  "artifact_type": "SCREEN_DESIGN",
  "screens": [
    {
      "screen_id": "SCR-001",
      "name": "화면명",
      "description": "화면 목적과 사용 흐름\n사용자 확인 포인트",
      "source_requirement_ids": ["REQ-00001"],
      "metadata": {
        "display_items": [
          {"item_name": "항목명", "description": "화면에서 보여줄 내용"}
        ]
      }
    }
  ],
  "metadata": {}
}

규칙:
- 화면은 요구사항별로 1개 이상 생성하되, 너무 쪼개지 말고 사용자가 실제로 보게 될 화면 단위로 묶는다.
- description은 화면 설명 항목을 최소 2개 이상 생성한다.
- description 항목에는 화면 구성, 조회/등록/처리 흐름, 사용자 확인 포인트를 포함한다.
- description 항목은 번호나 bullet 없이 일반 문장으로 작성한다.
- 다른 화면이나 요구사항의 순번을 이어받지 말고, 모든 화면 description은 독립적으로 작성한다.
- display_items에는 화면에 실제 노출될 만한 항목을 3~8개 정도 작성한다.
- source_requirement_ids는 실제 근거가 되는 요구사항 ID를 1~3개 넣는다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


class ScreenDesignAgent:
    """Generates screen-design artifacts from UI-related requirements."""

    AGENT_NAME = "ScreenDesignAgent"

    def __init__(self, *, model_invoker=None) -> None:
        self.model_invoker = model_invoker

    def with_model_invoker(self, model_invoker) -> "ScreenDesignAgent":
        return ScreenDesignAgent(model_invoker=model_invoker)

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}"
        )

        try:
            atoms = normalize_requirement_atoms(
                self._context_requirement_artifact(request),
                documents=request.documents,
            )
            screen_atoms = self._deduplicate_by_requirement_id(atoms)

            used_default_draft = False
            if not screen_atoms:
                screen_atoms = self._fallback_atoms_from_request(request)
                used_default_draft = True

            screens = await self._generate_in_batches(request, screen_atoms)
            if not screens:
                screens = self._deterministic_screens(screen_atoms)
            else:
                screens = self._resequence_screens(screens)

            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={
                    "artifact_type": "SCREEN_DESIGN",
                    "screens": screens,
                    "metadata": {
                        "project_id": request.project_id,
                        "project_name": str((request.context or {}).get("project_name") or (request.context or {}).get("project_nm") or "프로젝트명"),
                        "author": self._author(request.context or {}),
                        "generated_by": self.AGENT_NAME,
                        "source_requirement_count": len(atoms),
                        "screen_requirement_count": len(screen_atoms),
                        "process_rule": "Create one screen-design page per requirement ID and use the full requirement context when describing the screen",
                        **(self._default_draft_metadata() if used_default_draft else {}),
                    },
                },
            )
        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    def _fallback_atoms_from_request(self, request: AgentRequest) -> list[RequirementAtom]:
        context = request.context or {}
        query = str(context.get("query") or "").strip()
        project_name = str(
            context.get("project_name")
            or context.get("project_nm")
            or request.project_id
            or "프로젝트"
        ).strip()
        subject = truncate_text(query or f"{project_name} 화면설계서 생성", 100)
        common_metadata = {
            "generation_source": "default_draft",
            "assumptions": [
                "참고 문서가 없어 일반적인 업무 화면 구조를 기준으로 초안을 작성했습니다.",
            ],
            "additional_check_required": [
                "실제 메뉴 구조, 권한, 입력/출력 항목, 화면 흐름은 확인이 필요합니다.",
            ],
        }
        return [
            RequirementAtom(
                requirement_id="REQ-00001",
                title=subject,
                requirement_name=subject,
                description=f"{project_name} 요청을 기준으로 대표 업무 화면을 구성한다.",
                biz_requirement_name="공통",
                domain="공통",
                feature="대표 화면",
                metadata=common_metadata,
            ),
            RequirementAtom(
                requirement_id="REQ-00002",
                title="목록 및 검색 화면",
                requirement_name="목록 및 검색 화면",
                description="주요 데이터 목록 조회, 검색 조건 입력, 결과 확인 흐름을 제공한다.",
                biz_requirement_name="조회",
                domain="조회",
                feature="목록/검색",
                metadata=common_metadata,
            ),
            RequirementAtom(
                requirement_id="REQ-00003",
                title="등록 및 상세 화면",
                requirement_name="등록 및 상세 화면",
                description="데이터 등록, 상세 조회, 수정, 저장 결과 확인 흐름을 제공한다.",
                biz_requirement_name="처리",
                domain="처리",
                feature="등록/상세",
                metadata=common_metadata,
            ),
        ]

    def _default_draft_metadata(self) -> dict[str, object]:
        return {
            "generation_source": "default_draft",
            "가정사항": [
                "참고 문서가 없어 일반적인 업무 화면 구조를 기준으로 초안을 작성했습니다.",
            ],
            "추가 확인 필요 항목": [
                "실제 메뉴 구조, 권한, 입력/출력 항목, 화면 흐름은 확인이 필요합니다.",
            ],
        }

    async def _generate_with_llm(
        self,
        request: AgentRequest,
        atoms: list[Any],
        *,
        call_index: int = 1,
        call_total: int = 1,
        call_label: str = "screen-plan",
    ) -> list[dict[str, Any]]:
        model_invoker = self.model_invoker
        if model_invoker is None or not hasattr(model_invoker, "invoke_agent_llm"):
            return []

        prompt = f"""
Project ID: {request.project_id}
Project name: {self._project_name(request.context or {})}
Requirement summary:
{json.dumps(self._build_requirement_digest(atoms), ensure_ascii=False, default=str)}
""".strip()

        llm_result = await model_invoker.invoke_agent_llm(
            system_prompt=SCREEN_LLM_SYSTEM_PROMPT,
            user_prompt=prompt,
            call_index=call_index,
            call_total=call_total,
            call_label=call_label,
        )
        parsed = parse_json_object(llm_result)
        if not parsed:
            parsed_array = parse_json_array(llm_result)
            if not parsed_array:
                return []
            parsed = {"screens": parsed_array}

        screens = parsed.get("screens") or parsed.get("items") or []
        if not isinstance(screens, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, screen in enumerate(screens, start=1):
            if not isinstance(screen, dict):
                continue
            name = self._screen_name_from_payload(screen, index)
            description = self._screen_description_from_payload(screen, index, name)
            source_requirement_ids = screen.get("source_requirement_ids") or []
            if isinstance(source_requirement_ids, str):
                source_requirement_ids = [source_requirement_ids]
            if not source_requirement_ids:
                source_requirement_ids = self._guess_source_requirement_ids(atoms, name, description)
            screen_id = str(screen.get("screen_id") or f"SCR-{index:03d}").strip()
            display_items = self._normalize_display_items(screen.get("metadata") or {}, name, description)
            normalized.append(
                {
                    "screen_id": screen_id,
                    "name": name,
                    "description": description,
                    "source_requirement_ids": [str(value) for value in source_requirement_ids if value],
                    "metadata": {
                        "screen_no": screen_id,
                        "requirement_id": ", ".join([str(value) for value in source_requirement_ids if value]),
                        "requirement_name": name,
                        "description": description,
                        "original_requirement_description": description,
                        "biz_requirement_name": self._guess_biz_name(atoms, name, description),
                        "domain": self._guess_biz_name(atoms, name, description),
                        "feature": name,
                        "display_items": display_items,
                        "generation_source": "llm",
                    },
                }
            )
        return normalized

    async def _generate_in_batches(
        self,
        request: AgentRequest,
        atoms: list[Any],
    ) -> list[dict[str, Any]]:
        screens = await self._generate_with_llm(
            request,
            atoms,
            call_index=1,
            call_total=1,
            call_label="screen-plan",
        )
        return screens

    def _deterministic_screens(self, atoms: list[Any]) -> list[dict[str, Any]]:
        screens = []
        for index, atom in enumerate(atoms, start=1):
            screen_id = f"SCR-{index:03d}"
            screen_name = self._screen_name(atom, index)
            work_description = self._ensure_screen_description(
                self._work_description(atom),
                screen_name,
            )
            display_items = self._display_items(atom)
            screens.append(
                {
                    "screen_id": screen_id,
                    "name": screen_name,
                    "description": work_description,
                    "source_requirement_ids": [atom.requirement_id],
                    "metadata": {
                        "screen_no": screen_id,
                        "requirement_id": atom.requirement_id,
                        "requirement_name": atom.requirement_name or atom.title,
                        "description": work_description,
                        "original_requirement_description": atom.description or atom.title,
                        "biz_requirement_name": atom.biz_requirement_name,
                        "domain": atom.domain,
                        "feature": atom.feature,
                        "display_items": display_items,
                    },
                }
            )
        return screens

    def _resequence_screens(self, screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, screen in enumerate(screens, start=1):
            if not isinstance(screen, dict):
                continue
            source_requirement_ids = screen.get("source_requirement_ids") or []
            if isinstance(source_requirement_ids, str):
                source_requirement_ids = [source_requirement_ids]
            screen_id = f"SCR-{index:03d}"
            metadata = dict(screen.get("metadata") or {})
            name = str(screen.get("name") or metadata.get("screen_name") or f"화면 {index}")
            description = self._ensure_screen_description(
                str(screen.get("description") or metadata.get("description") or ""),
                name,
            )
            metadata["screen_no"] = screen_id
            metadata.setdefault("requirement_id", ", ".join([str(value) for value in source_requirement_ids if value]))
            metadata.setdefault("requirement_name", name)
            metadata["description"] = description
            metadata.setdefault("display_items", metadata.get("display_items") or [])
            normalized.append(
                {
                    **screen,
                    "screen_id": screen_id,
                    "description": description,
                    "source_requirement_ids": [str(value) for value in source_requirement_ids if value],
                    "metadata": metadata,
                }
            )
        return normalized

    def _context_requirement_artifact(self, request: AgentRequest):
        context = request.context or {}
        for key in ("requirement_artifact", "source_artifact", "previous_artifact", "artifact"):
            value = context.get(key)
            if isinstance(value, dict) and isinstance(value.get("requirements"), list):
                return value
        return None

    def _deduplicate_by_requirement_id(self, atoms):
        candidates = []
        seen_keys = set()
        for atom in atoms:
            key = (
                atom.requirement_id
                or atom.requirement_name
                or atom.title
                or atom.description
                or ""
            ).strip()
            if not key:
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append(atom)
        return candidates

    def _screen_name(self, atom, index: int) -> str:
        base = atom.feature or atom.requirement_name or atom.title or atom.biz_requirement_name or f"화면 {index}"
        if "화면" not in base and "페이지" not in base:
            base = f"{base} 화면"
        return truncate_text(base, 80)

    def _author(self, context: dict) -> str:
        return normalize_author_value(context.get("author")) or normalize_author_value(
            context.get("writer")
        )

    def _work_description(self, atom) -> str:
        requirement_name = atom.requirement_name or atom.title or atom.feature or "요구사항"
        return truncate_text(atom.description or requirement_name, 700)

    def _display_items(self, atom):
        return [
            {
                "item_name": "Description",
                "description": truncate_text(self._work_description(atom), 300),
            }
        ]

    def _build_requirement_digest(self, atoms: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "requirement_id": atom.requirement_id,
                "requirement_name": atom.requirement_name or atom.title,
                "biz_requirement_name": atom.biz_requirement_name,
                "domain": atom.domain,
                "feature": atom.feature,
                "category": atom.category,
                "requirement_type": atom.requirement_type,
                "description": truncate_text(atom.description, 220),
            }
            for atom in atoms
        ]

    def _project_name(self, context: dict[str, Any]) -> str:
        return str(context.get("project_name") or context.get("project_nm") or "프로젝트명")

    def _screen_name_from_payload(self, payload: dict[str, Any], index: int) -> str:
        base = payload.get("name") or payload.get("screen_name") or payload.get("title") or f"화면 {index}"
        return truncate_text(base, 80)

    def _screen_description_from_payload(self, payload: dict[str, Any], index: int, name: str | None = None) -> str:
        base = payload.get("description") or payload.get("screen_description") or payload.get("summary") or ""
        if not str(base).strip():
            base = f"{name or self._screen_name_from_payload(payload, index)}의 조회, 등록, 수정, 상세 확인 흐름을 포함하는 화면"
        return self._ensure_screen_description(base, name or self._screen_name_from_payload(payload, index))

    def _ensure_screen_description(self, base: str, name: str) -> str:
        title = name or "화면"
        items = [
            self._strip_number_prefix(line)
            for line in str(base or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if self._strip_number_prefix(line)
        ]
        if not items:
            items = [
                f"{title}에서 주요 조회와 입력 흐름을 제공한다."
            ]

        description_items = list(items)
        target_count = self._screen_description_target_count(base=" ".join(description_items), name=title)
        for line in self._screen_description_support_lines(
            base=" ".join(description_items),
            name=title,
        ):
            if line not in description_items:
                description_items.append(line)
            if len(description_items) >= target_count:
                break

        return truncate_text(self._line_description(description_items), 700)

    def _strip_number_prefix(self, value: Any) -> str:
        return re.sub(
            r"^\s*(?:[-*•ㆍ]+|\d+[.)])\s*",
            "",
            str(value or "").strip(),
        ).strip()

    def _line_description(self, items: list[str]) -> str:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = self._strip_number_prefix(item)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
            if len(normalized) >= 10:
                break

        if len(normalized) < 2:
            title = normalized[0] if normalized else "화면"
            normalized.append(f"{title}의 처리 결과와 사용자 확인 흐름을 제공한다.")

        return "\n".join(normalized)

    def _screen_description_support_lines(self, *, base: str, name: str) -> list[str]:
        corpus = f"{name} {base}".lower()
        candidates: list[str] = []
        if any(keyword in corpus for keyword in ("조회", "검색", "목록", "상세")):
            candidates.append(f"{name}에서 조회 조건, 목록 결과, 상세 확인 흐름을 제공한다.")
        if any(keyword in corpus for keyword in ("등록", "저장", "추가", "입력")):
            candidates.append(f"{name}에서 입력 항목 검증과 저장 결과 반영을 처리한다.")
        if any(keyword in corpus for keyword in ("수정", "변경")):
            candidates.append(f"{name}에서 기존 값 확인, 변경 입력, 수정 결과 반영을 처리한다.")
        if any(keyword in corpus for keyword in ("삭제", "제거")):
            candidates.append(f"{name}에서 삭제 전 확인, 삭제 처리, 삭제 후 목록 반영을 제공한다.")
        if any(keyword in corpus for keyword in ("권한", "인증", "보안")):
            candidates.append(f"{name}에서 권한별 접근 제어와 버튼 노출 상태를 확인할 수 있다.")
        if any(keyword in corpus for keyword in ("팝업", "경고", "오류", "예외", "메시지")):
            candidates.append(f"{name}에서 팝업, 경고 메시지, 오류 안내 흐름을 제공한다.")
        if any(keyword in corpus for keyword in ("탭", "정렬", "필터", "조건", "검색조건")):
            candidates.append(f"{name}에서 탭 전환, 정렬, 필터 조건 변경을 지원한다.")
        if any(keyword in corpus for keyword in ("페이징", "페이지", "다음", "이전")):
            candidates.append(f"{name}에서 페이지 이동과 건별 목록 확인을 지원한다.")
        if any(keyword in corpus for keyword in ("파일", "첨부", "다운로드", "업로드")):
            candidates.append(f"{name}에서 파일 첨부와 다운로드 흐름을 처리한다.")
        if any(keyword in corpus for keyword in ("승인", "결재", "반려")):
            candidates.append(f"{name}에서 승인, 반려, 처리 결과 반영 흐름을 확인한다.")
        if any(keyword in corpus for keyword in ("연동", "전송", "호출", "api", "인터페이스")):
            candidates.append(f"{name}에서 외부 연동 결과와 응답 상태를 확인한다.")
        if any(keyword in corpus for keyword in ("차트", "통계", "집계", "요약")):
            candidates.append(f"{name}에서 요약 정보와 집계 결과를 시각적으로 확인한다.")

        if not candidates:
            candidates = [
                f"{name}에서 주요 정보 표시와 사용자 입력 흐름을 제공한다.",
                f"{name}의 필수 항목 검증과 처리 결과 반영을 확인할 수 있다.",
                f"{name}에서 화면 진입 후 초기 상태와 조회 결과를 확인한다.",
            ]
        elif len(candidates) == 1:
            candidates.append(f"{name}의 사용자는 처리 결과, 안내 메시지, 화면 반영 상태를 확인한다.")
        elif len(candidates) == 2:
            candidates.append(f"{name}에서 사용자의 입력 후 반영 상태를 확인한다.")

        return candidates[:10]

    def _screen_description_target_count(self, *, base: str, name: str) -> int:
        corpus = f"{name} {base}".lower()
        score = 2
        keyword_buckets = (
            ("조회", "검색", "목록", "상세"),
            ("등록", "저장", "추가", "입력"),
            ("수정", "변경"),
            ("삭제", "제거"),
            ("권한", "인증", "보안"),
            ("팝업", "경고", "오류", "예외", "메시지"),
            ("탭", "정렬", "필터", "조건", "검색조건"),
            ("페이징", "페이지", "다음", "이전"),
            ("파일", "첨부", "다운로드", "업로드"),
            ("승인", "결재", "반려"),
            ("연동", "전송", "호출", "api", "인터페이스"),
            ("차트", "통계", "집계", "요약"),
        )
        for keywords in keyword_buckets:
            if any(keyword in corpus for keyword in keywords):
                score += 1

        sentence_count = sum(1 for line in str(base or "").splitlines() if self._strip_number_prefix(line))
        if sentence_count >= 3:
            score += 1
        if sentence_count >= 5:
            score += 1
        if sentence_count >= 7:
            score += 1

        if len(corpus) > 80:
            score += 1
        if len(corpus) > 140:
            score += 1

        return max(2, min(score, 10))

    def _normalize_display_items(self, metadata: dict[str, Any], name: str, description: str) -> list[dict[str, str]]:
        display_items = metadata.get("display_items") or []
        normalized: list[dict[str, str]] = []
        if isinstance(display_items, list):
            for item in display_items:
                if isinstance(item, dict):
                    item_name = truncate_text(item.get("item_name") or item.get("name") or "", 80)
                    item_desc = truncate_text(item.get("description") or item.get("value") or "", 260)
                    if item_name:
                        normalized.append({"item_name": item_name, "description": item_desc})
                elif isinstance(item, str) and item.strip():
                    normalized.append({"item_name": item.strip(), "description": truncate_text(description, 260)})
        if normalized:
            while len(normalized) < 3:
                if len(normalized) == 1:
                    normalized.append({"item_name": "주요 항목", "description": truncate_text(name, 300)})
                else:
                    normalized.append(
                        {"item_name": "검증 포인트", "description": "입력값 검증, 조회 결과 반영, 저장 후 상태 변화를 확인한다."}
                    )
            return normalized
        return [
            {"item_name": "Description", "description": truncate_text(description or name, 300)},
            {"item_name": "주요 항목", "description": truncate_text(name, 300)},
            {"item_name": "검증 포인트", "description": "입력값 검증, 조회 결과 반영, 저장 후 상태 변화를 확인한다."},
        ]

    def _guess_source_requirement_ids(self, atoms: list[Any], name: str, description: str) -> list[str]:
        corpus = f"{name} {description}".lower()
        matches: list[str] = []
        for atom in atoms:
            candidate_text = " ".join(
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
            if any(token in candidate_text for token in corpus.split() if token):
                matches.append(atom.requirement_id)
            elif not matches and any(keyword in candidate_text for keyword in ("화면", "등록", "수정", "조회", "상세", "검색", "버튼", "팝업")):
                matches.append(atom.requirement_id)
        return matches

    def _guess_biz_name(self, atoms: list[Any], name: str, description: str) -> str:
        for atom in atoms:
            candidate_text = " ".join(
                str(value or "").lower()
                for value in (
                    atom.biz_requirement_name,
                    atom.domain,
                    atom.feature,
                    atom.requirement_name,
                    atom.title,
                )
            )
            if any(token in candidate_text for token in f"{name} {description}".lower().split() if token):
                return atom.biz_requirement_name or atom.domain or "공통"
        return atoms[0].biz_requirement_name if atoms else "공통"


screen_design_agent = ScreenDesignAgent()
