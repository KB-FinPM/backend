# EN: Core agent adapter for generating WBS artifacts.
# KO: WBS 산출물 생성을 위한 Core Agent adapter입니다.

import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from math import floor
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    classify_project_type,
    group_atoms_by_biz,
    normalize_requirement_atoms,
    phase_names,
    truncate_text,
)
from util.agent_template_utils import (
    find_deliverable,
    load_deliverable_mapper,
    load_wbs_common_rows,
)

logger = get_logger(__name__)


class WbsAgent:
    """Generates WBS artifacts from requirement-style structured context."""

    AGENT_NAME = "WbsAgent"
    DEVELOPMENT_PHASE_ORDER = ("요구사항정의", "분석", "설계", "구현", "테스트", "이행", "안정화")
    DEVELOPMENT_PHASE_BASE_RATIOS = {
        "요구사항정의": 0.15,
        "분석": 0.09,
        "설계": 0.09,
        "테스트": 0.15,
        "이행": 0.03,
        "안정화": 0.07,
    }

    @classmethod
    def _development_phase_ratios(cls) -> list[tuple[str, float]]:
        implementation_ratio = max(
            1.0 - sum(cls.DEVELOPMENT_PHASE_BASE_RATIOS.values()),
            0.0,
        )
        return [
            ("요구사항정의", cls.DEVELOPMENT_PHASE_BASE_RATIOS["요구사항정의"]),
            ("분석", cls.DEVELOPMENT_PHASE_BASE_RATIOS["분석"]),
            ("설계", cls.DEVELOPMENT_PHASE_BASE_RATIOS["설계"]),
            ("구현", implementation_ratio),
            ("테스트", cls.DEVELOPMENT_PHASE_BASE_RATIOS["테스트"]),
            ("이행", cls.DEVELOPMENT_PHASE_BASE_RATIOS["이행"]),
            ("안정화", cls.DEVELOPMENT_PHASE_BASE_RATIOS["안정화"]),
        ]

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
            start_date, end_date, project_period = self._resolve_project_schedule(request)
            tasks = self._build_tasks(
                atoms,
                phases,
                request=request,
                start_date=start_date,
                end_date=end_date,
            )

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
                        "project_name": str(
                            (request.context or {}).get("project_name")
                            or (request.context or {}).get("project_nm")
                            or "프로젝트명"
                        ),
                        "generated_by": self.AGENT_NAME,
                        "project_type": project_type,
                        "source_requirement_count": len(atoms),
                        "project_start_date": self._format_date(start_date) or date.today().strftime("%Y.%m.%d"),
                        "project_end_date": self._format_date(end_date) or date.today().strftime("%Y.%m.%d"),
                        "project_period": project_period,
                        "process_rule": "Common WBS template rows + Biz requirement based decomposition",
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

    def _build_tasks(
        self,
        atoms: list[Any],
        phases: list[str],
        *,
        request: AgentRequest,
        start_date: date | None,
        end_date: date | None,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        template_rows = load_wbs_common_rows()
        request_context = request.context or {}
        project_name = str(
            request_context.get("project_name")
            or request_context.get("project_nm")
            or "프로젝트명"
        )

        for raw in template_rows:
            level = str(raw.get("level", "")).strip()
            name = str(raw.get("wbs_name", "")).replace("{project_name}", project_name)
            deliverable = str(raw.get("deliverable", "")).replace("{project_name}", project_name)
            sample_wbs_id = str(raw.get("wbs_id", "")).strip()
            if not name:
                continue

            task_metadata: dict[str, Any] = {
                "level": level,
                "phase": "공통",
                "deliverable": deliverable,
                "template_source": "wbs_template.json",
            }
            if sample_wbs_id:
                task_metadata["wbs_id"] = sample_wbs_id
                task_metadata["id"] = sample_wbs_id
            if self._numeric_level(level) > 1:
                task_metadata["worker"] = "작업자"

            tasks.append(
                {
                    "task_id": f"WBS-{len(tasks) + 1:03d}",
                    "name": name,
                    "description": f"공통 WBS 템플릿 항목: {name}",
                    "source_requirement_ids": [],
                    "metadata": task_metadata,
                }
            )

        common_task_count = len(tasks)
        generated_tasks = self._build_generated_requirement_tasks(
            atoms,
            phases,
            start_sequence=len(tasks) + 1,
            start_top_index=self._next_top_level_wbs_id(tasks),
        )
        tasks.extend(generated_tasks)

        if start_date is not None and end_date is not None:
            self._apply_development_phase_schedule(
                tasks[:common_task_count],
                project_start=start_date,
                project_end=end_date,
            )
            self._apply_generated_task_schedule(
                generated_tasks,
                project_start=start_date,
                project_end=end_date,
            )
        return tasks

    def _build_generated_requirement_tasks(
        self,
        atoms: list[Any],
        phases: list[str],
        *,
        start_sequence: int,
        start_top_index: int,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        sequence = start_sequence
        top_index = start_top_index
        grouped = group_atoms_by_biz(atoms)
        deliverable_mapper = load_deliverable_mapper()

        for biz_name, biz_atoms in grouped.items():
            top_task_id = f"WBS-{sequence:03d}"
            top_wbs_id = str(top_index)
            sequence += 1
            requirement_ids = [atom.requirement_id for atom in biz_atoms if atom.requirement_id]
            tasks.append(
                {
                    "task_id": top_task_id,
                    "wbs_id": top_wbs_id,
                    "name": biz_name,
                    "description": f"{biz_name} 영역의 요구사항을 분석, 설계, 구현/구축, 검증, 이행 작업으로 분해한다.",
                    "source_requirement_ids": requirement_ids,
                    "metadata": {
                        "level": "1",
                        "wbs_id": top_wbs_id,
                        "id": top_wbs_id,
                        "biz_requirement_name": biz_name,
                        "phase": "영역",
                        "deliverable": "",
                        "template_source": "generated_from_requirement_spec",
                    },
                }
            )

            for phase_index, phase in enumerate(phases, start=1):
                phase_task_id = f"WBS-{sequence:03d}"
                phase_wbs_id = f"{top_wbs_id}.{phase_index}"
                sequence += 1
                deliverable = find_deliverable(biz_name, phase, deliverable_mapper)
                tasks.append(
                    {
                        "task_id": phase_task_id,
                        "wbs_id": phase_wbs_id,
                        "name": f"{biz_name} {phase}",
                        "description": f"{biz_name} 영역의 {phase} 작업을 수행한다.",
                        "source_requirement_ids": requirement_ids[:],
                        "metadata": {
                            "level": "2",
                            "wbs_id": phase_wbs_id,
                            "id": phase_wbs_id,
                            "parent_task_id": top_task_id,
                            "biz_requirement_name": biz_name,
                            "phase": phase,
                            "deliverable": deliverable,
                            "worker": "작업자",
                        },
                    }
                )

                for req_index, atom in enumerate(biz_atoms[:3], start=1):
                    leaf_task_id = f"WBS-{sequence:03d}"
                    leaf_wbs_id = f"{phase_wbs_id}.{req_index}"
                    sequence += 1
                    req_name = atom.requirement_name or atom.feature or atom.title or atom.description
                    tasks.append(
                        {
                            "task_id": leaf_task_id,
                            "wbs_id": leaf_wbs_id,
                            "name": truncate_text(f"{req_name} {phase}", 120),
                            "description": truncate_text(atom.description, 300),
                            "source_requirement_ids": [atom.requirement_id] if atom.requirement_id else [],
                            "metadata": {
                                "level": "3",
                                "wbs_id": leaf_wbs_id,
                                "id": leaf_wbs_id,
                                "parent_task_id": phase_task_id,
                                "biz_requirement_name": biz_name,
                                "phase": phase,
                                "category": atom.category,
                                "requirement_type": atom.requirement_type,
                                "deliverable": deliverable,
                                "worker": "작업자",
                            },
                        }
                    )
            top_index += 1
        return tasks

    def _resolve_project_schedule(self, request: AgentRequest) -> tuple[date | None, date | None, str | None]:
        context = request.context or {}
        start_date_value = (
            context.get("start_date")
            or context.get("project_start_date")
            or context.get("contract_date")
            or context.get("contract_start_date")
        )
        start_date = self._normalize_date(start_date_value)
        if start_date is None:
            start_date = date.today()

        project_period = self._extract_project_period(request.documents, context)
        if project_period is None:
            project_period = {"value": 6, "unit": "개월"}

        end_date = self._add_duration(
            start_date,
            int(project_period["value"]),
            str(project_period["unit"]),
        )
        return start_date, end_date, self._format_period(project_period)

    def _extract_project_period(self, documents: list[dict] | None, context: dict | None) -> dict[str, object] | None:
        for key in ("project_period", "project_duration", "duration", "period", "contract_period"):
            value = (context or {}).get(key)
            period = self._parse_period_text(value, require_schedule_keyword=False)
            if period is not None:
                return period

        for document in documents or []:
            if not isinstance(document, dict):
                continue
            for key in ("text", "content", "page_content"):
                value = document.get(key)
                if not isinstance(value, str) or not value.strip():
                    continue
                period = self._parse_period_text(value, require_schedule_keyword=True)
                if period is not None:
                    return period
                break
        return None

    def _parse_period_text(
        self,
        value: object,
        *,
        require_schedule_keyword: bool,
    ) -> dict[str, object] | None:
        if not isinstance(value, str) or not value.strip():
            return None

        for line in value.splitlines() or [value]:
            line = line.strip()
            if not line:
                continue
            if require_schedule_keyword and not any(
                keyword in line for keyword in ["추진 일정", "일정", "기간", "계약기간", "프로젝트 기간"]
            ):
                continue
            match = re.search(
                r"(\d+)\s*(개월|개월간|달|달간|주|주간|일|일간|년|년간|months?|mons?|weeks?|days?|years?|[mwd])",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                return {"value": int(match.group(1)), "unit": match.group(2)}
        return None

    def _normalize_date(self, value: object) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None

        raw_value = value.strip()
        if not raw_value:
            return None

        match = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", raw_value)
        if not match:
            return None

        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    def _parse_start_date(self, value: Any) -> date | None:
        return self._normalize_date(value)

    def _parse_project_period(self, value: Any, start: date) -> date | None:
        project_period = self._parse_period_text(value, require_schedule_keyword=False)
        if project_period is None:
            return None
        return self._add_duration(
            start,
            int(project_period["value"]),
            str(project_period["unit"]),
        )

    def _format_date(self, value: date | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y.%m.%d")

    def _format_period(self, project_period: dict[str, object] | None) -> str | None:
        if not project_period:
            return None
        value = project_period.get("value")
        unit = project_period.get("unit")
        if value is None or unit is None:
            return None
        return f"{value}{unit}"

    def _add_duration(self, start_date: date, value: int, unit: str) -> date:
        normalized_unit = str(unit).strip().lower()
        if normalized_unit in {"개월", "개월간", "달", "달간", "month", "months", "mon", "mons", "m"}:
            year = start_date.year + (start_date.month - 1 + value) // 12
            month = (start_date.month - 1 + value) % 12 + 1
            day = min(start_date.day, monthrange(year, month)[1])
            return date(year, month, day)
        if normalized_unit in {"년", "년간", "year", "years", "y"}:
            year = start_date.year + value
            day = min(start_date.day, monthrange(year, start_date.month)[1])
            return date(year, start_date.month, day)
        if normalized_unit in {"주", "주간", "week", "weeks", "w"}:
            return start_date + timedelta(weeks=value)
        if normalized_unit in {"일", "일간", "day", "days", "d"}:
            return start_date + timedelta(days=value)
        return start_date

    def _build_development_phase_windows(
        self,
        start_date: date,
        end_date: date | None,
    ) -> dict[str, tuple[date, date]]:
        if end_date is None:
            return {}

        total_days = max((end_date - start_date).days + 1, 1)
        cumulative_ratios: list[tuple[str, float]] = []
        cumulative = 0.0
        phase_ratios = self._development_phase_ratios()
        for phase_name, ratio in phase_ratios:
            cumulative += ratio
            cumulative_ratios.append((phase_name, cumulative))

        raw_windows: dict[str, tuple[date, date]] = {}
        current_start = start_date
        previous_cut = 0
        for index, (phase_name, cumulative_ratio) in enumerate(cumulative_ratios):
            if index == len(cumulative_ratios) - 1:
                cut_day_count = total_days
            else:
                cut_day_count = floor(total_days * cumulative_ratio)
                cut_day_count = max(cut_day_count, previous_cut + 1)
                remaining_phases = len(cumulative_ratios) - index - 1
                cut_day_count = min(cut_day_count, total_days - remaining_phases)

            phase_end = start_date + timedelta(days=cut_day_count - 1)
            raw_windows[phase_name] = (current_start, phase_end)
            current_start = phase_end + timedelta(days=1)
            previous_cut = cut_day_count

        windows: dict[str, tuple[date, date]] = {}
        for phase_name, (raw_start, raw_end) in raw_windows.items():
            start_value = self._shift_weekend_to_friday(raw_start)
            end_value = self._shift_weekend_to_friday(raw_end)
            if start_value > end_value:
                start_value, end_value = raw_start, raw_end
            windows[phase_name] = (start_value, end_value)

        return windows

    def _apply_development_phase_schedule(
        self,
        tasks: list[dict[str, Any]],
        *,
        project_start: date,
        project_end: date | None,
    ) -> None:
        windows = self._build_development_phase_windows(project_start, project_end)
        if not windows:
            return

        current_phase: str | None = None
        development_phase_names = set(self.DEVELOPMENT_PHASE_ORDER)

        for task in tasks:
            metadata = task.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                continue
            name = str(task.get("name") or "").strip()
            if name == "개발영역":
                start_value = windows["요구사항정의"][0]
                end_value = windows["안정화"][1]
                current_phase = None
            elif name in development_phase_names:
                start_value, end_value = windows[name]
                current_phase = name
            elif current_phase in windows:
                start_value, end_value = windows[current_phase]
            else:
                start_value = project_start
                end_value = project_end or project_start

            self._set_task_schedule(task, start_value=start_value, end_value=end_value)
            if self._numeric_level(metadata.get("level")) > 1:
                metadata["worker"] = str(metadata.get("worker") or task.get("worker") or "작업자").strip() or "작업자"
                task["worker"] = metadata["worker"]

        self._apply_development_area_schedule(tasks, windows)
        self._apply_special_wbs_schedule(tasks, windows)

    def _apply_generated_task_schedule(
        self,
        tasks: list[dict[str, Any]],
        *,
        project_start: date,
        project_end: date | None,
    ) -> None:
        windows = self._build_development_phase_windows(project_start, project_end)
        if not windows:
            return

        for task in tasks:
            metadata = task.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                continue
            phase = str(metadata.get("phase") or "").strip()
            if phase == "영역":
                start_value = project_start
                end_value = project_end or project_start
            else:
                mapped_phase = self._map_generated_phase(phase)
                start_value, end_value = windows.get(
                    mapped_phase,
                    (project_start, project_end or project_start),
                )

            self._set_task_schedule(task, start_value=start_value, end_value=end_value)
            if self._numeric_level(metadata.get("level")) > 1:
                metadata["worker"] = str(metadata.get("worker") or task.get("worker") or "작업자").strip() or "작업자"
                task["worker"] = metadata["worker"]

    def _map_generated_phase(self, phase: str) -> str:
        normalized = re.sub(r"\s+", "", str(phase or ""))
        if "요구사항" in normalized or "요건" in normalized:
            return "요구사항정의"
        if "분석" in normalized:
            return "분석"
        if "설계" in normalized:
            return "설계"
        if "테스트" in normalized or "검증" in normalized:
            return "테스트"
        if "이행" in normalized or "오픈" in normalized or "안정화" in normalized:
            return "이행"
        if "개발" in normalized or "구현" in normalized or "구축" in normalized:
            return "구현"
        return "구현"

    def _apply_development_area_schedule(
        self,
        tasks: list[dict[str, Any]],
        windows: dict[str, tuple[date, date]],
    ) -> None:
        if not windows:
            return

        def anchor(name: str) -> str | None:
            return self._find_task_id_by_name(tasks, name)

        def add_rule(
            rule_specs: list[tuple[str | None, date | None, date | None]],
            name: str,
            start_value: date,
            end_value: date,
        ) -> None:
            aligned_start, aligned_end = self._align_to_week_boundaries(start_value, end_value)
            rule_specs.append((anchor(name), aligned_start, aligned_end))

        design_end = windows["설계"][1]
        _implementation_start, implementation_end = windows["구현"]
        test_start, test_end = windows["테스트"]
        transition_end = windows["이행"][1]

        rule_specs: list[tuple[str | None, date | None, date | None]] = []
        add_rule(rule_specs, "테스트계획설계", design_end - timedelta(weeks=1), design_end)
        add_rule(rule_specs, "단위테스트", implementation_end - timedelta(weeks=2), implementation_end)
        add_rule(rule_specs, "통합테스트", test_start, test_end - timedelta(weeks=1))
        add_rule(rule_specs, "사용자인수테스트", test_end - timedelta(weeks=1), test_end)
        add_rule(rule_specs, "시스템이행", transition_end - timedelta(days=3), transition_end)
        add_rule(rule_specs, "이행일정계획및점검", transition_end - timedelta(days=3), transition_end - timedelta(days=1))
        add_rule(rule_specs, "가동(오픈)", transition_end, transition_end)

        self._apply_anchor_schedule_rules(tasks, rule_specs)

    def _apply_special_wbs_schedule(
        self,
        tasks: list[dict[str, Any]],
        windows: dict[str, tuple[date, date]],
    ) -> None:
        if not windows:
            return

        def anchor(name: str) -> str | None:
            return self._find_task_id_by_name(tasks, name)

        def add_rule(
            rule_specs: list[tuple[str | None, date | None, date | None]],
            name: str,
            start_value: date,
            end_value: date,
        ) -> None:
            aligned_start, aligned_end = self._align_to_week_boundaries(start_value, end_value)
            rule_specs.append((anchor(name), aligned_start, aligned_end))

        rule_specs: list[tuple[str | None, date | None, date | None]] = []
        analysis_end = windows["분석"][1]
        requirement_start = windows["요구사항정의"][0]
        implementation_start, implementation_end = windows["구현"]
        test_start, test_end = windows["테스트"]
        requirement_end = windows["요구사항정의"][1]
        transition_end = windows["이행"][1]
        stabilization_start, stabilization_end = windows["안정화"]

        add_rule(rule_specs, "요구사항정의/분석/설계단계말산출물검토", analysis_end - timedelta(weeks=1), analysis_end)
        add_rule(rule_specs, "구현/테스트단계말산출물검토", implementation_end - timedelta(weeks=1), implementation_end)
        add_rule(rule_specs, "아키텍처정의", requirement_start, requirement_end)
        add_rule(rule_specs, "개발 환경 구축", requirement_start, requirement_end)
        add_rule(rule_specs, "테스트 환경 구축", implementation_start, implementation_start + timedelta(weeks=3))
        add_rule(rule_specs, "운영시스템 환경 구축", implementation_start, implementation_start + timedelta(weeks=3))
        add_rule(rule_specs, "인프라테스트", test_start - timedelta(weeks=1), test_end)
        add_rule(rule_specs, "프로젝트계획수립", requirement_end - timedelta(weeks=1), requirement_end)
        add_rule(rule_specs, "프로젝트계획서작성", requirement_end - timedelta(weeks=1), requirement_end)
        add_rule(rule_specs, "프로젝트계획서승인(부장)", requirement_end - timedelta(weeks=1), requirement_end)
        add_rule(rule_specs, "프로젝트착수보고", requirement_end, requirement_end)
        add_rule(rule_specs, "Cut-Over 계획수립", transition_end - timedelta(weeks=2), transition_end - timedelta(weeks=1))
        add_rule(rule_specs, "프로젝트종료", stabilization_start, stabilization_end)

        self._apply_anchor_schedule_rules(tasks, rule_specs)

    def _apply_anchor_schedule_rules(
        self,
        tasks: list[dict[str, Any]],
        rule_specs: list[tuple[str | None, date | None, date | None]],
    ) -> None:
        for anchor_id, start_value, end_value in rule_specs:
            if not anchor_id:
                continue
            for task in tasks:
                metadata = task.get("metadata") or {}
                if not isinstance(metadata, dict):
                    continue
                task_id = str(metadata.get("wbs_id") or metadata.get("id") or "").strip()
                if not task_id or not self._is_same_or_descendant(task_id, anchor_id):
                    continue
                self._set_task_schedule(task, start_value=start_value, end_value=end_value)

    def _find_task_id_by_name(self, tasks: list[dict[str, Any]], name: str) -> str | None:
        for task in tasks:
            task_name = str(task.get("name") or "").strip()
            if task_name != name:
                continue
            metadata = task.get("metadata") or {}
            if isinstance(metadata, dict):
                task_id = str(metadata.get("wbs_id") or metadata.get("id") or "").strip()
                if task_id:
                    return task_id
        return None

    def _is_same_or_descendant(self, task_id: str, anchor_id: str) -> bool:
        return task_id == anchor_id or task_id.startswith(f"{anchor_id}.")

    def _shift_weekend_to_friday(self, value: date) -> date:
        if value.weekday() == 5:
            return value - timedelta(days=1)
        if value.weekday() == 6:
            return value - timedelta(days=2)
        return value

    def _align_to_week_boundaries(self, start_value: date, end_value: date) -> tuple[date, date]:
        return self._shift_weekend_to_friday(start_value), self._shift_weekend_to_friday(end_value)

    def _set_task_schedule(
        self,
        task: dict[str, Any],
        *,
        start_value: date | None,
        end_value: date | None,
    ) -> None:
        metadata = task.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            return
        if start_value is not None and end_value is not None and end_value < start_value:
            end_value = start_value

        start_text = self._format_date(start_value)
        end_text = self._format_date(end_value)
        if start_text:
            metadata["start_date"] = start_text
            task["start_date"] = start_text
        if end_text:
            metadata["end_date"] = end_text
            task["end_date"] = end_text
        if start_value is not None:
            metadata["planned_start_date"] = start_value.isoformat()
            task["planned_start_date"] = start_value.isoformat()
        if end_value is not None:
            metadata["planned_end_date"] = end_value.isoformat()
            task["planned_end_date"] = end_value.isoformat()

    def _numeric_level(self, value: object) -> int:
        try:
            return max(int(str(value or "0").strip() or "0"), 0)
        except (TypeError, ValueError):
            return 0

    def _next_top_level_wbs_id(self, tasks: list[dict[str, Any]]) -> int:
        max_top_id = 0
        for task in tasks:
            metadata = task.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            wbs_id = str(metadata.get("wbs_id") or task.get("wbs_id") or "").strip()
            if not wbs_id:
                continue
            top_segment = wbs_id.split(".", 1)[0]
            if top_segment.isdigit():
                max_top_id = max(max_top_id, int(top_segment))
        return max_top_id + 1


wbs_agent = WbsAgent()
