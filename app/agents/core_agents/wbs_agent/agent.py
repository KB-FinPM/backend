# EN: Core agent adapter for generating WBS artifacts.
# KO: WBS 산출물 생성을 위한 Core Agent adapter입니다.

import json
import re
from collections import defaultdict
from calendar import monthrange
from math import floor
from datetime import date, datetime, timedelta

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    classify_project_type,
    normalize_requirement_atoms,
    parse_json_array,
    parse_json_object,
    truncate_text,
)
from util.agent_template_utils import (
    find_deliverable,
    load_wbs_common_rows,
    load_wbs_deliverable_catalog,
)

logger = get_logger(__name__)

WBS_LLM_SYSTEM_PROMPT = """
너는 PM Agent의 WBS 생성기다.
입력으로 주어지는 구축요건정의서 요구사항과 고정 WBS 뼈대를 바탕으로,
개발영역의 상세 WBS만 JSON으로 생성하라.

반드시 JSON 객체만 반환하고, 스키마는 아래를 따른다.
{
  "artifact_type": "WBS",
  "development_tasks": [
    {
      "phase": "요구사항정의 | 분석 | 설계 | 구현 | 테스트 | 이행 | 안정화",
      "tasks": [
        {
          "level": 3,
          "name": "WBS명",
          "description": "작업 목적과 범위를 드러내는 설명",
          "source_requirement_ids": ["REQ-00001"],
          "deliverable": "산출물명"
        }
      ]
    }
  ],
  "metadata": {
    "summary": "짧은 요약"
  }
}

규칙:
- 개발영역의 level 2 단계는 고정이며, 그 아래 상세만 생성한다.
- 각 phase 별로 1~4개의 상세 WBS를 제안한다.
- WBS명은 구축요건정의서의 실제 기능/정책/데이터/화면/인터페이스/테스트 요구를 반영해야 한다.
- description은 "무엇을 어떤 목적으로 하는지"가 드러나게 1~2문장으로 작성한다.
- deliverable은 제공된 산출물 목록을 참고해 가장 적합한 명칭으로 작성한다.
- source_requirement_ids는 실제로 근거가 되는 요구사항 ID를 1~3개 넣는다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


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

    def _find_task_id_by_name(self, tasks: list[dict[str, object]], name: str) -> str | None:
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
        task: dict[str, object],
        *,
        start_value: date | None,
        end_value: date | None,
    ) -> None:
        metadata = task.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            return
        start_text = self._format_date(start_value)
        end_text = self._format_date(end_value)
        if start_text:
            metadata["start_date"] = start_text
            task["start_date"] = start_text
        if end_text:
            metadata["end_date"] = end_text
            task["end_date"] = end_text

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

        project_period = self._extract_project_period(request.documents, {})
        if project_period is None:
            project_period = {"value": 6, "unit": "개월"}
        end_date = None
        if project_period is not None and start_date is not None:
            end_date = self._add_duration(start_date, project_period["value"], project_period["unit"])

        return start_date, end_date, self._format_period(project_period)

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

    def _format_date(self, value: date | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y.%m.%d")

    def _extract_project_period(self, documents: list[dict] | None, context: dict | None) -> dict[str, object] | None:
        candidates: list[str] = []
        for key in ("project_period", "project_duration", "duration", "period", "contract_period"):
            value = (context or {}).get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

        for document in documents or []:
            if not isinstance(document, dict):
                continue
            for key in ("text", "content", "page_content"):
                value = document.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
                    break

        for candidate in candidates:
            if not candidate:
                continue
            joined_text = "\n".join(line.strip() for line in candidate.splitlines() if line.strip())
            if any(keyword in joined_text for keyword in ["추진 일정", "일정", "기간", "계약기간", "프로젝트 기간"]):
                match = re.search(r"(\d+)\s*(개월|개월간|달|달간|주|일|년)", joined_text)
                if match:
                    return {"value": int(match.group(1)), "unit": match.group(2)}
            for line in candidate.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not any(keyword in line for keyword in ["추진 일정", "일정", "기간", "계약기간", "프로젝트 기간"]):
                    continue
                match = re.search(r"(\d+)\s*(개월|개월간|달|달간|주|일|년)", line)
                if match:
                    return {"value": int(match.group(1)), "unit": match.group(2)}

        return None

    def _format_period(self, project_period: dict[str, object] | None) -> str | None:
        if not project_period:
            return None
        value = project_period.get("value")
        unit = project_period.get("unit")
        if value is None or unit is None:
            return None
        return f"{value}{unit}"

    def _add_duration(self, start_date: date, value: int, unit: str) -> date:
        if unit in {"개월", "개월간", "달", "달간"}:
            year = start_date.year + (start_date.month - 1 + value) // 12
            month = (start_date.month - 1 + value) % 12 + 1
            day = min(start_date.day, monthrange(year, month)[1])
            return date(year, month, day)
        if unit in {"년", "년간"}:
            year = start_date.year + value
            day = min(start_date.day, monthrange(year, start_date.month)[1])
            return date(year, start_date.month, day)
        if unit in {"주", "주간"}:
            return start_date + timedelta(weeks=value)
        if unit in {"일", "일간"}:
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
        tasks: list[dict[str, object]],
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

            metadata["start_date"] = self._format_date(start_value) or metadata.get("start_date") or ""
            metadata["end_date"] = self._format_date(end_value) or metadata.get("end_date") or ""
            task["start_date"] = metadata["start_date"]
            task["end_date"] = metadata["end_date"]

        self._apply_development_area_schedule(tasks, windows)
        self._apply_special_wbs_schedule(tasks, windows)

    def _apply_development_area_schedule(
        self,
        tasks: list[dict[str, object]],
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
        implementation_start, implementation_end = windows["구현"]
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

    def _apply_special_wbs_schedule(
        self,
        tasks: list[dict[str, object]],
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

        # Apply from the most specific anchor down to descendants based on ID prefix.
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

    def _is_development_detail_row(self, row: dict[str, str]) -> bool:
        wbs_id = str(row.get("wbs_id") or "")
        try:
            level = int(str(row.get("level") or "0").strip() or "0")
        except ValueError:
            level = 0
        return wbs_id.startswith("3.") and level >= 3

    def _build_base_tasks(
        self,
        request: AgentRequest,
        *,
        start_date: date | None,
        end_date: date | None,
        project_period: str | None,
    ) -> list[dict[str, object]]:
        tasks: list[dict[str, object]] = []
        today_text = date.today().strftime("%Y.%m.%d")
        start_date_text = self._format_date(start_date) or today_text
        end_date_text = self._format_date(end_date) or today_text
        template_rows = load_wbs_common_rows()
        request_context = request.context or {}
        project_name = str(
            request_context.get("project_name")
            or request_context.get("project_nm")
            or "프로젝트명"
        )

        for raw in template_rows:
            if self._is_development_detail_row(raw):
                continue
            level = str(raw.get("level", "")).strip()
            name = str(raw.get("wbs_name", "")).replace("{project_name}", project_name)
            deliverable = str(raw.get("deliverable", "")).replace("{project_name}", project_name)
            if not name:
                continue

            try:
                numeric_level = int(level)
            except ValueError:
                numeric_level = 0

            phase_name = name if numeric_level >= 2 else ""
            if not deliverable and phase_name:
                deliverable = find_deliverable(name, phase_name)

            task_metadata = {
                "level": level,
                "phase": phase_name or "공통",
                "deliverable": deliverable,
                "template_source": "wbs_template.json",
            }
            sample_wbs_id = str(raw.get("wbs_id", "")).strip()
            if sample_wbs_id:
                task_metadata["wbs_id"] = sample_wbs_id
                task_metadata["id"] = sample_wbs_id
            if start_date_text:
                task_metadata["start_date"] = start_date_text
            if end_date_text:
                task_metadata["end_date"] = end_date_text
            if numeric_level > 1 and not task_metadata.get("worker"):
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

        self._apply_development_phase_schedule(tasks, project_start=start_date, project_end=end_date)
        return tasks

    def _fixed_development_phases(self, tasks: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        return {
            str(task.get("name") or ""): task
            for task in tasks
            if str((task.get("metadata") or {}).get("phase") or "") in self.DEVELOPMENT_PHASE_ORDER
            or str(task.get("name") or "") in self.DEVELOPMENT_PHASE_ORDER
        }

    def _build_requirement_digest(self, atoms) -> list[dict[str, object]]:
        digest = []
        for atom in atoms or []:
            digest.append(
                {
                    "requirement_id": atom.requirement_id,
                    "requirement_name": atom.requirement_name or atom.title,
                    "biz_requirement_name": atom.biz_requirement_name,
                    "domain": atom.domain,
                    "feature": atom.feature,
                    "category": atom.category,
                    "requirement_type": atom.requirement_type,
                    "description": truncate_text(atom.description, 240),
                }
            )
        return digest

    def _build_deliverable_digest(self) -> list[dict[str, str]]:
        catalog = load_wbs_deliverable_catalog()
        selected: list[dict[str, str]] = []
        for item in catalog:
            if item.get("stage") not in self.DEVELOPMENT_PHASE_ORDER and item.get("stage") not in {"요구사항정의", "분석", "설계", "구현", "테스트", "이행", "안정화"}:
                continue
            selected.append(item)
        return selected[:60]

    async def _generate_llm_development_tasks(
        self,
        request: AgentRequest,
        atoms,
        *,
        project_type: str,
        start_date: date | None,
        end_date: date | None,
        project_period: str | None,
    ) -> list[dict[str, object]]:
        orchestrator = (request.context or {}).get("generation_orchestrator")
        if orchestrator is None or not hasattr(orchestrator, "invoke_agent_llm"):
            return []

        context = request.context or {}
        fixed_rows = [
            row
            for row in load_wbs_common_rows()
            if self._is_development_detail_row(row) is False and str(row.get("wbs_id") or "").startswith("3")
        ]
        prompt = f"""
Project ID: {request.project_id}
Project type: {project_type}
Project name: {context.get("project_name") or context.get("project_nm") or "프로젝트명"}
Project start date: {self._format_date(start_date) or ""}
Project end date: {self._format_date(end_date) or ""}
Project period: {project_period or ""}

고정 개발영역 뼈대:
{json.dumps(fixed_rows, ensure_ascii=False, default=str)}

구축요건정의서 요구사항 요약:
{json.dumps(self._build_requirement_digest(atoms), ensure_ascii=False, default=str)}

산출물 목록(참고용):
{json.dumps(self._build_deliverable_digest(), ensure_ascii=False, default=str)}
""".strip()

        llm_result = await orchestrator.invoke_agent_llm(
            system_prompt=WBS_LLM_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=7000,
        )
        parsed = parse_json_object(llm_result)
        if not parsed:
            parsed_array = parse_json_array(llm_result)
            if not parsed_array:
                return []
            parsed = {"development_tasks": parsed_array}

        groups = parsed.get("development_tasks") or parsed.get("tasks") or []
        if not isinstance(groups, list):
            return []

        normalized: list[dict[str, object]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            phase = str(group.get("phase") or group.get("name") or "").strip()
            if not phase:
                continue
            phase_tasks = group.get("tasks") or group.get("items") or []
            if not isinstance(phase_tasks, list):
                continue
            for item in phase_tasks:
                if not isinstance(item, dict):
                    continue
                name = truncate_text(item.get("name") or item.get("wbs_name") or "", 120)
                if not name:
                    continue
                try:
                    level = int(str(item.get("level") or "3").strip() or "3")
                except ValueError:
                    level = 3
                level = 3 if level < 3 else min(level, 4)
                description = truncate_text(item.get("description") or name, 700)
                source_requirement_ids = item.get("source_requirement_ids") or []
                if isinstance(source_requirement_ids, str):
                    source_requirement_ids = [source_requirement_ids]
                if not source_requirement_ids:
                    source_requirement_ids = self._guess_source_requirement_ids(atoms, phase, name)
                deliverable = str(item.get("deliverable") or find_deliverable(name, phase) or "").strip()
                normalized.append(
                    {
                        "phase": phase,
                        "level": str(level),
                        "name": name,
                        "description": description,
                        "source_requirement_ids": [str(value) for value in source_requirement_ids if value],
                        "metadata": {
                            "phase": phase,
                            "deliverable": deliverable,
                            "generation_source": "llm",
                        },
                    }
                )
        return normalized

    def _guess_source_requirement_ids(self, atoms, phase: str, name: str) -> list[str]:
        candidates: list[str] = []
        phase_text = f"{phase} {name}".lower()
        for atom in atoms or []:
            corpus = " ".join(
                str(value or "").lower()
                for value in (
                    atom.biz_requirement_name,
                    atom.domain,
                    atom.feature,
                    atom.title,
                    atom.description,
                    atom.requirement_name,
                )
            )
            if any(token in corpus for token in phase_text.split() if token):
                candidates.append(atom.requirement_id)
            elif not candidates and any(token in corpus for token in ("화면", "테스트", "데이터", "인터페이스", "배치", "권한", "보안")):
                candidates.append(atom.requirement_id)
        return candidates[:3]

    def _merge_llm_development_tasks(
        self,
        base_tasks: list[dict[str, object]],
        llm_tasks: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for task in llm_tasks:
            phase = str(task.get("phase") or "").strip()
            if phase:
                grouped[phase].append(task)

        merged: list[dict[str, object]] = []
        inserted_phases: set[str] = set()
        for task in base_tasks:
            merged.append(task)
            metadata = task.get("metadata") or {}
            phase = str(metadata.get("phase") or task.get("name") or "").strip()
            if phase not in self.DEVELOPMENT_PHASE_ORDER:
                continue
            if phase in inserted_phases:
                continue
            extra_rows = grouped.get(phase) or []
            if not extra_rows:
                inserted_phases.add(phase)
                continue
            for index, extra in enumerate(extra_rows, start=1):
                extra_metadata = dict(extra.get("metadata") or {})
                extra_metadata.setdefault("phase", phase)
                extra_metadata.setdefault("deliverable", find_deliverable(str(extra.get("name") or ""), phase))
                extra_metadata.setdefault("generation_source", "llm")
                extra_metadata.setdefault("level", str(extra.get("level") or "3"))
                extra_metadata.setdefault("worker", "작업자")
                merged.append(
                    {
                        "task_id": f"WBS-LLM-{phase[:1]}-{index:02d}",
                        "name": str(extra.get("name") or "").strip(),
                        "description": str(extra.get("description") or "").strip(),
                        "source_requirement_ids": extra.get("source_requirement_ids") or [],
                        "metadata": extra_metadata,
                    }
                )
            inserted_phases.add(phase)
        return merged

    def _apply_llm_development_schedule(
        self,
        tasks: list[dict[str, object]],
        *,
        project_start: date | None,
        project_end: date | None,
    ) -> None:
        if project_start is None:
            return
        windows = self._build_development_phase_windows(project_start, project_end or project_start)
        if not windows:
            return

        current_phase: str | None = None
        for task in tasks:
            metadata = task.get("metadata") or {}
            phase = str(metadata.get("phase") or task.get("name") or "").strip()
            if phase in windows:
                current_phase = phase
            elif current_phase not in windows:
                continue
            start_value, end_value = windows[current_phase]
            if str(metadata.get("generation_source") or "") == "llm" or phase in windows:
                self._set_task_schedule(task, start_value=start_value, end_value=end_value)

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
            start_date, end_date, project_period = self._resolve_project_schedule(request)
            base_tasks = self._build_base_tasks(
                request,
                start_date=start_date,
                end_date=end_date,
                project_period=project_period,
            )
            llm_tasks = await self._generate_llm_development_tasks(
                request,
                atoms,
                project_type=project_type,
                start_date=start_date,
                end_date=end_date,
                project_period=project_period,
            )
            tasks = (
                self._merge_llm_development_tasks(base_tasks, llm_tasks)
                if llm_tasks
                else self._build_tasks(
                    atoms,
                    request=request,
                    start_date=start_date,
                    end_date=end_date,
                    project_period=project_period,
                )
            )
            if llm_tasks:
                self._apply_llm_development_schedule(
                    tasks,
                    project_start=start_date,
                    project_end=end_date,
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
                        "project_name": str((request.context or {}).get("project_name") or (request.context or {}).get("project_nm") or "프로젝트명"),
                        "generated_by": self.AGENT_NAME,
                        "project_type": project_type,
                        "source_requirement_count": len(atoms),
                        "project_start_date": self._format_date(start_date) or date.today().strftime("%Y.%m.%d"),
                        "project_end_date": self._format_date(end_date) or date.today().strftime("%Y.%m.%d"),
                        "project_period": project_period,
                        "process_rule": "Common WBS template rows from JSON template",
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

    def _build_tasks(self, atoms, request, start_date: date | None, end_date: date | None, project_period: str | None):
        tasks = []
        today_text = date.today().strftime("%Y.%m.%d")
        start_date_text = self._format_date(start_date) or today_text
        end_date_text = self._format_date(end_date) or today_text

        # The workbook template is the source of truth for the common prefix rows.
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
            task_metadata = {
                "level": level,
                "phase": "공통",
                "deliverable": deliverable,
                "template_source": "wbs_template.xlsx",
            }
            if sample_wbs_id:
                task_metadata["wbs_id"] = sample_wbs_id
                task_metadata["id"] = sample_wbs_id
            if start_date_text:
                task_metadata["start_date"] = start_date_text
            if end_date_text:
                task_metadata["end_date"] = end_date_text
            try:
                numeric_level = int(level)
            except ValueError:
                numeric_level = 0
            if numeric_level > 1:
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
        self._apply_development_phase_schedule(tasks, project_start=start_date, project_end=end_date)
        return tasks


wbs_agent = WbsAgent()
