# EN: Core agent adapter for generating screen design artifacts.
# KO: 화면설계서 산출물 생성을 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
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
            screen_atoms = self._deduplicate_by_requirement_id(atoms)

            if not screen_atoms:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No requirement context available for screen design generation",
                )

            screens = []
            for index, atom in enumerate(screen_atoms, start=1):
                screen_id = f"SCR-{index:03d}"
                work_description = self._work_description(atom)
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

            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={
                    "artifact_type": "SCREEN_DESIGN",
                    "screens": screens,
                    "metadata": {
                        "project_id": request.project_id,
                        "project_name": str((request.context or {}).get("project_name") or request.project_id or "프로젝트명"),
                        "author": self._author(request.context or {}),
                        "generated_by": self.AGENT_NAME,
                        "source_requirement_count": len(atoms),
                        "screen_requirement_count": len(screen_atoms),
                        "process_rule": "Create one screen-design page per requirement ID and write only the requirement description into the template Description area",
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


screen_design_agent = ScreenDesignAgent()
