# EN: Core agent adapter for generating screen design artifacts.
# KO: 화면설계서 산출물 생성을 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    is_screen_related,
    normalize_requirement_atoms,
    truncate_text,
)

logger = get_logger(__name__)


class ScreenDesignAgent:
    """Generates screen-design artifacts from UI-related requirements."""

    AGENT_NAME = "ScreenDesignAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}"
        )

        try:
            atoms = normalize_requirement_atoms(
                self._context_requirement_artifact(request),
                documents=request.documents,
            )
            screen_atoms = [atom for atom in atoms if is_screen_related(atom)]
            used_fallback = False
            if not screen_atoms:
                # Some requirement specifications, especially infrastructure or
                # platform projects, do not contain explicit UI keywords.
                # In that case we still create a draft screen-design artifact
                # from representative requirements instead of failing the API.
                # The generated PPTX can then be refined by the user.
                screen_atoms = self._fallback_screen_atoms(atoms)
                used_fallback = True

            if not screen_atoms:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No requirement context available for screen design generation",
                )

            screens = []
            for index, atom in enumerate(screen_atoms, start=1):
                screen_id = f"SCR-{index:03d}"
                display_items = self._display_items(atom)
                screens.append(
                    {
                        "screen_id": screen_id,
                        "name": self._screen_name(atom, index),
                        "description": truncate_text(atom.description or atom.title, 500),
                        "source_requirement_ids": [atom.requirement_id],
                        "metadata": {
                            "screen_no": screen_id,
                            "requirement_id": atom.requirement_id,
                            "requirement_name": atom.requirement_name or atom.title,
                            "description": atom.description or atom.title,
                            "biz_requirement_name": atom.biz_requirement_name,
                            "domain": atom.domain,
                            "feature": atom.feature,
                            "display_items": display_items,
                        },
                    }
                )

            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={
                    "artifact_type": "SCREEN_DESIGN",
                    "screens": screens,
                    "metadata": {
                        "project_id": request.project_id,
                        "project_name": str((request.context or {}).get("project_name") or request.project_id or "프로젝트명"),
                        "author": str((request.context or {}).get("author") or ""),
                        "generated_by": self.AGENT_NAME,
                        "source_requirement_count": len(atoms),
                        "screen_requirement_count": len(screen_atoms),
                        "used_fallback": used_fallback,
                        "process_rule": "UI related requirements are preferred; when none are found, representative requirements are converted into draft management/monitoring screens",
                    },
                },
            )
        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    def _context_requirement_artifact(self, request: AgentRequest):
        context = request.context or {}
        for key in ("requirement_artifact", "source_artifact", "previous_artifact", "artifact"):
            value = context.get(key)
            if isinstance(value, dict) and isinstance(value.get("requirements"), list):
                return value
        return None

    def _fallback_screen_atoms(self, atoms):
        candidates = []
        seen_groups = set()
        for atom in atoms:
            group_key = (atom.biz_requirement_name or atom.domain or atom.category or atom.requirement_id or "공통").strip()
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            candidates.append(atom)
            if len(candidates) >= 12:
                break
        if candidates:
            return candidates
        return list(atoms)[:12]

    def _screen_name(self, atom, index: int) -> str:
        base = atom.feature or atom.requirement_name or atom.title or atom.biz_requirement_name or f"화면 {index}"
        if "화면" not in base and "페이지" not in base:
            base = f"{base} 화면"
        return truncate_text(base, 80)

    def _display_items(self, atom):
        requirement_name = atom.requirement_name or atom.title or atom.feature or "요구사항"
        requirement_desc = atom.description or requirement_name
        base_items = [
            ("요구사항ID", atom.requirement_id),
            ("요구사항명", requirement_name),
            ("Description", requirement_desc),
            ("검색 조건", f"{requirement_name} 관련 데이터를 조회하기 위한 검색 조건을 제공한다."),
            ("목록/상세 정보", f"{requirement_name} 처리에 필요한 목록 및 상세 정보를 표시한다."),
            ("입력/수정 항목", f"{requirement_name} 처리에 필요한 입력 및 수정 항목을 제공한다."),
            ("처리 버튼", "조회, 저장, 수정, 삭제, 승인 등 화면 처리 버튼을 제공한다."),
            ("검증 메시지", "필수값, 형식, 권한, 처리 결과 메시지를 표시한다."),
        ]
        items = []
        seen = set()
        for item_name, description in base_items:
            name = str(item_name or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            items.append({
                "item_name": truncate_text(name, 40),
                "description": truncate_text(description, 300),
            })
            if len(items) >= 8:
                break
        return items


screen_design_agent = ScreenDesignAgent()
