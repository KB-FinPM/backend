# EN: Core agent adapter for generating screen design artifacts.
# KO: 화면설계서 산출물 생성을 위한 Core Agent adapter입니다.

import json
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
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
      "description": "화면 목적과 사용 흐름이 드러나는 설명",
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
- description은 단순 요구사항 문구가 아니라 화면 구성, 조회/등록/처리 흐름, 사용자 확인 포인트를 포함해 구체적으로 작성한다.
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

            if not screen_atoms:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No requirement context available for screen design generation",
                )

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
                    },
                },
            )
        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

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
            work_description = self._work_description(atom)
            work_description = self._ensure_screen_description(work_description, self._screen_name(atom, index))
            display_items = self._display_items(atom)
            screens.append(
                {
                    "screen_id": screen_id,
                    "name": self._screen_name(atom, index),
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
            metadata["screen_no"] = screen_id
            metadata.setdefault("requirement_id", ", ".join([str(value) for value in source_requirement_ids if value]))
            metadata.setdefault("requirement_name", str(screen.get("name") or ""))
            metadata.setdefault("description", str(screen.get("description") or ""))
            metadata.setdefault("display_items", metadata.get("display_items") or [])
            normalized.append(
                {
                    **screen,
                    "screen_id": screen_id,
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
        return str(
            context.get("author")
            or context.get("writer")
            or context.get("created_by")
            or context.get("user_id")
            or "작성자"
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
        lines = [
            line.strip()
            for line in str(base or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if line.strip()
        ]
        if len(lines) >= 2:
            return truncate_text("\n".join(lines), 700)

        title = name or "화면"
        fallback_lines = [
            f"{title}에서 주요 조회와 입력 흐름을 제공한다.",
            f"{title}의 필수 항목 검증과 저장 결과 반영을 처리한다.",
            f"{title}의 사용자는 목록, 상세, 팝업 또는 경고 메시지를 확인한다.",
        ]
        return truncate_text("\n".join(fallback_lines), 700)

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
