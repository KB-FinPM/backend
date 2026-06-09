# EN: Core agent adapter for generating WBS artifacts.
# KO: WBS 산출물 생성을 위한 Core Agent adapter입니다.

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    classify_project_type,
    group_atoms_by_biz,
    normalize_requirement_atoms,
    phase_names,
    truncate_text,
)
from util.agent_template_utils import find_deliverable, load_deliverable_mapper, load_wbs_template

logger = get_logger(__name__)


class WbsAgent:
    """Generates WBS artifacts from requirement-style structured context."""

    AGENT_NAME = "WbsAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}"
        )

        try:
            atoms = normalize_requirement_atoms(
                self._context_requirement_artifact(request),
                documents=request.documents,
            )
            if not atoms:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No requirement context available for WBS generation",
                )

            configured_type = str((request.context or {}).get("project_type") or "auto")
            project_type = classify_project_type(
                text="\n".join(document.get("text", "") for document in request.documents),
                atoms=atoms,
                configured=configured_type,
            )
            phases = phase_names(project_type)
            tasks = self._build_tasks(atoms, phases, request=request)

            if not tasks:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="WBS task generation produced no tasks",
                )

            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={
                    "artifact_type": "WBS",
                    "tasks": tasks,
                    "metadata": {
                        "project_id": request.project_id,
                        "project_name": str((request.context or {}).get("project_name") or (request.context or {}).get("project_nm") or "프로젝트명"),
                        "generated_by": self.AGENT_NAME,
                        "project_type": project_type,
                        "source_requirement_count": len(atoms),
                        "process_rule": "Common PM phases + Biz requirement based decomposition",
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

    def _build_tasks(self, atoms, phases, request):
        tasks = []
        sequence = 1

        # sample_0605의 template/wbs_template.json에 있던 공통 WBS 1~36 항목을 먼저 반영한다.
        template = load_wbs_template()
        request_context = request.context or {}
        project_name = str(
            request_context.get("project_name")
            or request_context.get("project_nm")
            or "프로젝트명"
        )
        for raw in template.get("common_items", []):
            level = str(raw.get("level", "")).strip()
            name = str(raw.get("wbs_name", "")).replace("{project_name}", project_name)
            deliverable = str(raw.get("deliverable", "")).replace("{project_name}", project_name)
            if not name:
                continue
            task_id = f"WBS-{sequence:03d}"
            tasks.append({
                "task_id": task_id,
                "name": name,
                "description": f"공통 WBS 템플릿 항목: {name}",
                "source_requirement_ids": [],
                "metadata": {
                    "level": level,
                    "phase": "공통",
                    "deliverable": deliverable,
                    "template_source": "wbs_template.json",
                },
            })
            sequence += 1

        grouped = group_atoms_by_biz(atoms)
        deliverable_mapper = load_deliverable_mapper()
        top_index = 1
        for biz_name, biz_atoms in grouped.items():
            top_task_id = f"WBS-{sequence:03d}"
            sequence += 1
            requirement_ids = [atom.requirement_id for atom in biz_atoms if atom.requirement_id]
            tasks.append(
                {
                    "task_id": top_task_id,
                    "name": biz_name,
                    "description": f"{biz_name} 영역의 요구사항을 분석, 설계, 구현/구축, 검증, 이행 작업으로 분해한다.",
                    "source_requirement_ids": requirement_ids,
                    "metadata": {
                        "level": "1",
                        "biz_requirement_name": biz_name,
                        "phase": "영역",
                        "deliverable": "",
                        "template_source": "generated_from_requirement_spec",
                    },
                }
            )
            for phase_index, phase in enumerate(phases, start=1):
                phase_task_id = f"{top_task_id}-{phase_index:02d}"
                phase_requirements = requirement_ids[:]
                deliverable = find_deliverable(biz_name, phase, deliverable_mapper)
                tasks.append(
                    {
                        "task_id": phase_task_id,
                        "name": f"{biz_name} {phase}",
                        "description": f"{biz_name} 영역의 {phase} 작업을 수행한다.",
                        "source_requirement_ids": phase_requirements,
                        "metadata": {
                            "level": "2",
                            "parent_task_id": top_task_id,
                            "biz_requirement_name": biz_name,
                            "phase": phase,
                            "deliverable": deliverable,
                        },
                    }
                )
                for req_index, atom in enumerate(biz_atoms[:3], start=1):
                    leaf_task_id = f"{phase_task_id}-{req_index:02d}"
                    req_name = atom.requirement_name or atom.feature or atom.title or atom.description
                    tasks.append(
                        {
                            "task_id": leaf_task_id,
                            "name": truncate_text(f"{req_name} {phase}", 120),
                            "description": truncate_text(atom.description, 300),
                            "source_requirement_ids": [atom.requirement_id],
                            "metadata": {
                                "level": "3",
                                "parent_task_id": phase_task_id,
                                "biz_requirement_name": biz_name,
                                "phase": phase,
                                "category": atom.category,
                                "requirement_type": atom.requirement_type,
                                "deliverable": deliverable,
                            },
                        }
                    )
            top_index += 1
        self._assign_hierarchical_wbs_ids(tasks)
        return tasks

    def _assign_hierarchical_wbs_ids(self, tasks):
        counters: list[int] = []
        for task in tasks:
            metadata = task.setdefault("metadata", {})
            try:
                level = int(str(metadata.get("level", task.get("level", "0"))).strip() or "0")
            except ValueError:
                level = 0
            if level <= 0:
                counters = [0]
                display_id = "0"
            else:
                while len(counters) <= level:
                    counters.append(0)
                counters = counters[: level + 1]
                counters[level] += 1
                for idx in range(level + 1, len(counters)):
                    counters[idx] = 0
                # If a malformed sequence jumps levels, seed missing parents with 1.
                for idx in range(1, level):
                    if counters[idx] == 0:
                        counters[idx] = 1
                display_id = ".".join(str(counters[idx]) for idx in range(1, level + 1))
            task["wbs_id"] = display_id
            metadata["wbs_id"] = display_id


wbs_agent = WbsAgent()
