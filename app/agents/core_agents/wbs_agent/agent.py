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
    load_wbs_common_rows,
    load_deliverable_mapper_local,
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

    def __init__(self, *, model_invoker=None) -> None:
        self.model_invoker = model_invoker

    def with_model_invoker(self, model_invoker) -> "WbsAgent":
        return WbsAgent(model_invoker=model_invoker)

    DEVELOPMENT_PHASE_ORDER = ("요구사항정의", "분석", "설계", "구현", "테스트", "이행", "안정화")
    DEVELOPMENT_PHASE_BASE_RATIOS = {
        "요구사항정의": 0.15,
        "분석": 0.09,
        "설계": 0.09,
        "테스트": 0.15,
        "이행": 0.03,
        "안정화": 0.07,
    }
    SCHEDULE_ANCHOR_DETAIL_ROWS = (
        {"level": "3", "wbs_id": "3.3.5", "wbs_name": "테스트계획설계"},
        {"level": "3", "wbs_id": "3.4.3", "wbs_name": "단위테스트"},
        {"level": "3", "wbs_id": "3.5.1", "wbs_name": "통합테스트"},
        {"level": "4", "wbs_id": "3.6.2.3", "wbs_name": "가동(오픈)"},
    )

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
            metadata["planned_start_date"] = start_value.isoformat() if start_value else start_text
            task["start_date"] = start_text
            task["planned_start_date"] = metadata["planned_start_date"]
        if end_text:
            metadata["end_date"] = end_text
            metadata["planned_end_date"] = end_value.isoformat() if end_value else end_text
            task["end_date"] = end_text
            task["planned_end_date"] = metadata["planned_end_date"]

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

    def _parse_start_date(self, value: object) -> date | None:
        return self._normalize_date(value)

    def _format_date(self, value: date | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y.%m.%d")

    def _parse_period_value(self, value: object) -> dict[str, object] | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        match = re.search(
            r"(\d+)\s*(개월간|개월|달간|달|months?|mos?|년간|년|years?|주간|주|weeks?|일간|일|days?)",
            normalized,
        )
        if not match:
            return None
        unit = match.group(2)
        if unit in {"개월간", "개월", "달간", "달", "month", "months", "mo", "mos"}:
            normalized_unit = "개월"
        elif unit in {"년간", "년", "year", "years"}:
            normalized_unit = "년"
        elif unit in {"주간", "주", "week", "weeks"}:
            normalized_unit = "주"
        else:
            normalized_unit = "일"
        return {"value": int(match.group(1)), "unit": normalized_unit}

    def _parse_project_period(self, value: object, start_date: date) -> date | None:
        period = self._parse_period_value(value)
        if period is None:
            return None
        return self._add_duration(start_date, int(period["value"]), str(period["unit"]))

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
            parsed_candidate = self._parse_period_value(candidate)
            if parsed_candidate is not None:
                return parsed_candidate
            joined_text = "\n".join(line.strip() for line in candidate.splitlines() if line.strip())
            if any(keyword in joined_text for keyword in ["추진 일정", "일정", "기간", "계약기간", "프로젝트 기간"]):
                parsed_period = self._parse_period_value(joined_text)
                if parsed_period is not None:
                    return parsed_period
            for line in candidate.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not any(keyword in line for keyword in ["추진 일정", "일정", "기간", "계약기간", "프로젝트 기간"]):
                    continue
                parsed_period = self._parse_period_value(line)
                if parsed_period is not None:
                    return parsed_period

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
        normalized_unit = str(unit or "").lower()
        if normalized_unit in {"개월", "개월간", "달", "달간", "month", "months", "mo", "mos"}:
            year = start_date.year + (start_date.month - 1 + value) // 12
            month = (start_date.month - 1 + value) % 12 + 1
            day = min(start_date.day, monthrange(year, month)[1])
            return date(year, month, day)
        if normalized_unit in {"년", "년간", "year", "years"}:
            year = start_date.year + value
            day = min(start_date.day, monthrange(year, start_date.month)[1])
            return date(year, start_date.month, day)
        if normalized_unit in {"주", "주간", "week", "weeks"}:
            return start_date + timedelta(weeks=value)
        if normalized_unit in {"일", "일간", "day", "days"}:
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

            start_text = self._format_date(start_value) or metadata.get("start_date") or ""
            end_text = self._format_date(end_value) or metadata.get("end_date") or ""
            metadata["start_date"] = start_text
            metadata["end_date"] = end_text
            metadata["planned_start_date"] = start_value.isoformat() if start_value else start_text
            metadata["planned_end_date"] = end_value.isoformat() if end_value else end_text
            task["start_date"] = metadata["start_date"]
            task["end_date"] = metadata["end_date"]
            task["planned_start_date"] = metadata["planned_start_date"]
            task["planned_end_date"] = metadata["planned_end_date"]

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

    def _has_explicit_schedule_context(self, context: dict | None) -> bool:
        context = context or {}
        schedule_keys = (
            "start_date",
            "project_start_date",
            "contract_date",
            "contract_start_date",
            "project_period",
            "project_duration",
            "duration",
            "period",
            "contract_period",
        )
        return any(context.get(key) not in (None, "") for key in schedule_keys)

    def _has_invalid_explicit_schedule_context(
        self,
        context: dict | None,
    ) -> bool:
        context = context or {}
        date_keys = (
            "start_date",
            "project_start_date",
            "contract_date",
            "contract_start_date",
        )
        period_keys = (
            "project_period",
            "project_duration",
            "duration",
            "period",
            "contract_period",
        )
        start_value = next(
            (context.get(key) for key in date_keys if context.get(key) not in (None, "")),
            None,
        )
        period_value = next(
            (context.get(key) for key in period_keys if context.get(key) not in (None, "")),
            None,
        )
        if start_value is not None and self._normalize_date(start_value) is None:
            return True
        if period_value is not None and self._parse_period_value(period_value) is None:
            return True
        return False

    def _strip_schedule_fields(self, tasks: list[dict[str, object]]) -> None:
        for task in tasks:
            for key in (
                "start_date",
                "end_date",
                "planned_start_date",
                "planned_end_date",
            ):
                task.pop(key, None)
            metadata = task.get("metadata")
            if not isinstance(metadata, dict):
                continue
            for key in (
                "start_date",
                "end_date",
                "planned_start_date",
                "planned_end_date",
            ):
                metadata.pop(key, None)

    def _parent_wbs_id(self, wbs_id: str) -> str:
        if "." not in wbs_id:
            return ""
        return wbs_id.rsplit(".", 1)[0]

    def _build_schedule_anchor_tasks(
        self,
        *,
        start_date_text: str,
        end_date_text: str,
    ) -> list[dict[str, object]]:
        tasks: list[dict[str, object]] = []
        for row in self.SCHEDULE_ANCHOR_DETAIL_ROWS:
            wbs_id = str(row["wbs_id"])
            name = str(row["wbs_name"])
            phase_name = self._development_phase_from_wbs_id(wbs_id)
            metadata = {
                "level": str(row["level"]),
                "phase": phase_name,
                "deliverable": self._resolve_deliverable_local(name, phase_name),
                "template_source": "wbs_schedule_anchors",
                "wbs_id": wbs_id,
                "id": wbs_id,
                "parent_task_id": self._parent_wbs_id(wbs_id),
                "worker": "작업자",
                "start_date": start_date_text,
                "end_date": end_date_text,
            }
            tasks.append(
                {
                    "task_id": f"WBS-{wbs_id}",
                    "name": name,
                    "description": self._detail_description_for_phase(phase_name, name),
                    "source_requirement_ids": [],
                    "metadata": metadata,
                }
            )
        return tasks

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
                deliverable = self._resolve_deliverable_local(name, phase_name)

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

        if self._has_explicit_schedule_context(request_context):
            tasks.extend(
                self._build_schedule_anchor_tasks(
                    start_date_text=start_date_text,
                    end_date_text=end_date_text,
                )
            )

        self._apply_development_phase_schedule(tasks, project_start=start_date, project_end=end_date)
        return tasks

    def _development_phase_from_wbs_id(self, wbs_id: str) -> str:
        if wbs_id.startswith("3.1"):
            return "요구사항정의"
        if wbs_id.startswith("3.2"):
            return "분석"
        if wbs_id.startswith("3.3"):
            return "설계"
        if wbs_id.startswith("3.4"):
            return "구현"
        if wbs_id.startswith("3.5"):
            return "테스트"
        if wbs_id.startswith("3.6.3"):
            return "안정화"
        if wbs_id.startswith("3.6"):
            return "이행"
        return "구현"

    def _detail_description_for_phase(self, phase: str, name: str) -> str:
        phase_descriptions = {
            "요구사항정의": "요구사항 범위와 업무 규칙을 정리하고 세부 요구를 확정한다.",
            "분석": "업무 흐름, 데이터, 인터페이스, 제약 조건을 분석한다.",
            "설계": "기능, 화면, 데이터, 인터페이스, 테스트 관점을 설계한다.",
            "구현": "설계 내용을 기반으로 기능을 개발하고 연동을 구현한다.",
            "테스트": "단위, 통합, 인수 테스트를 설계하고 실행해 품질을 검증한다.",
            "이행": "배포, 교육, 오픈 준비와 이행 점검을 수행한다.",
            "안정화": "오픈 이후 이슈를 점검하고 안정화한다.",
        }
        base = phase_descriptions.get(phase, "관련 작업을 수행한다.")
        if name and name not in base:
            return f"{name} 작업을 통해 {base}"
        return base

    def _phase_detail_targets(self) -> dict[str, int]:
        return {
            "요구사항정의": 2,
            "분석": 2,
            "설계": 3,
            "구현": 3,
            "테스트": 2,
            "이행": 2,
            "안정화": 0,
        }

    def _atom_display_name(self, atom, fallback: str = "프로젝트") -> str:
        return str(
            atom.requirement_name
            or atom.title
            or atom.feature
            or atom.domain
            or fallback
        ).strip()

    def _score_atom_for_phase(self, atom, phase: str) -> int:
        phase_keywords = {
            "요구사항정의": ("요구사항", "정의", "기능", "비기능", "정책"),
            "분석": ("분석", "업무", "도메인", "데이터", "정책", "흐름"),
            "설계": ("설계", "화면", "UI", "UX", "인터페이스", "아키텍처", "DB", "데이터"),
            "구현": ("구현", "개발", "연동", "처리", "백엔드", "프론트", "API"),
            "테스트": ("테스트", "검증", "통합", "시나리오", "단위", "결과"),
            "이행": ("이행", "운영", "교육", "안정화", "전환", "오픈"),
            "안정화": ("안정화", "운영", "장애", "개선", "오픈"),
        }
        haystack = " ".join(
            str(value or "").lower()
            for value in (
                atom.requirement_name,
                atom.title,
                atom.feature,
                atom.domain,
                atom.description,
                atom.biz_requirement_name,
            )
        )
        score = 0
        for keyword in phase_keywords.get(phase, ()):
            if keyword.lower() in haystack:
                score += 1
        return score

    def _select_atoms_for_phase(self, atoms, phase: str, limit: int) -> list[object]:
        ordered_atoms = list(atoms or [])
        if not ordered_atoms:
            return []
        scored = [
            (self._score_atom_for_phase(atom, phase), index, atom)
            for index, atom in enumerate(ordered_atoms)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [atom for _, _, atom in scored[:limit]]
        return selected

    def _build_phase_detail_tasks(
        self,
        atoms,
        *,
        project_name: str,
        project_type: str,
        existing_phase_counts: dict[str, int] | None = None,
    ) -> list[dict[str, object]]:
        tasks: list[dict[str, object]] = []
        phase_targets = self._phase_detail_targets()
        phase_suffixes = {
            "요구사항정의": ["기능요구사항 정의", "요구사항 정의"],
            "분석": ["업무 분석", "데이터/정책 분석"],
            "설계": ["아키텍처 설계", "화면 설계", "데이터베이스 설계"],
            "구현": ["기능 개발", "연동 구현", "데이터 처리 개발"],
            "테스트": ["통합테스트", "기능 테스트"],
            "이행": ["운영이관", "사용자 교육 및 안정화"],
            "안정화": ["안정화 점검"],
        }
        phase_role_labels = {
            "요구사항정의": "기능요구사항",
            "분석": "업무 분석",
            "설계": "설계",
            "구현": "개발",
            "테스트": "테스트",
            "이행": "이행",
            "안정화": "안정화",
        }
        existing_phase_counts = existing_phase_counts or {}
        for phase in self.DEVELOPMENT_PHASE_ORDER:
            target_count = phase_targets.get(phase, 1)
            current_count = existing_phase_counts.get(phase, 0)
            needed = max(target_count - current_count, 0)
            if needed == 0:
                continue

            selected_atoms = self._select_atoms_for_phase(atoms, phase, limit=needed)
            if not selected_atoms:
                selected_atoms = [None] * needed

            suffixes = phase_suffixes.get(phase, ["작업"])
            for index in range(needed):
                atom = selected_atoms[index] if index < len(selected_atoms) else None
                suffix = suffixes[index % len(suffixes)]
                if atom is not None:
                    atom_name = self._atom_display_name(atom, fallback=project_name)
                    source_requirement_ids = [str(getattr(atom, "requirement_id", "")).strip()]
                    name = f"{atom_name} {suffix}".strip()
                    description = f"{atom_name} 관련 {phase_role_labels.get(phase, phase)} 작업을 수행한다."
                    if atom.description:
                        description = f"{description} {truncate_text(atom.description, 180)}"
                else:
                    source_requirement_ids = []
                    if phase == "요구사항정의":
                        name = f"{project_name} {suffix}".strip()
                    elif phase == "이행":
                        name = suffix
                    else:
                        name = f"{project_name} {suffix}".strip()
                    description = self._detail_description_for_phase(phase, name)

                deliverable = str(self._resolve_deliverable_local(name, phase) or "").strip()
                if project_type and project_type != "auto":
                    description = f"{description} 프로젝트 유형은 {project_type}로 분류되었다."
                tasks.append(
                    {
                        "phase": phase,
                        "level": "3",
                        "name": name,
                        "description": truncate_text(description, 700),
                        "source_requirement_ids": [value for value in source_requirement_ids if value],
                        "metadata": {
                            "phase": phase,
                            "deliverable": deliverable,
                            "generation_source": "fallback",
                            "level": "3",
                            "worker": "작업자",
                        },
                    }
                )
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
                    "description": atom.description,
                }
            )
        return digest

    def _build_deliverable_digest(self) -> list[dict[str, str]]:
        mapper = load_deliverable_mapper_local()
        digest: list[dict[str, str]] = []
        for phase, deliverable in (mapper.get("default_by_phase") or {}).items():
            digest.append({"phase": str(phase), "deliverable": str(deliverable)})
        for rule in mapper.get("keyword_rules") or []:
            if not isinstance(rule, dict):
                continue
            digest.append(
                {
                    "keywords": ", ".join(str(item) for item in rule.get("keywords") or [] if item),
                    "deliverables": ", ".join(str(item) for item in rule.get("deliverables") or [] if item),
                }
            )
        return digest

    def _resolve_deliverable_local(self, name: str, phase: str) -> str:
        mapper = load_deliverable_mapper_local()
        text = f"{name} {phase}"
        for rule in mapper.get("keyword_rules") or []:
            if not isinstance(rule, dict):
                continue
            keywords = rule.get("keywords") or []
            if any(str(keyword).lower() in text.lower() for keyword in keywords if keyword):
                deliverables = rule.get("deliverables") or []
                return ", ".join(str(item) for item in deliverables[:2] if item)
        for key, value in (mapper.get("default_by_phase") or {}).items():
            if str(key) and str(key) in str(phase):
                return str(value)
        return ""

    def _collect_llm_task_candidates(self, value) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        if isinstance(value, list):
            for item in value:
                candidates.extend(self._collect_llm_task_candidates(item))
            return candidates
        if not isinstance(value, dict):
            return candidates

        nested_task_keys = ("development_tasks", "tasks", "items", "subtasks", "children", "rows", "data")
        is_task_like = any(
            key in value
            for key in ("level", "name", "wbs_name", "task_name", "description", "deliverable")
        )
        has_nested_tasks = any(isinstance(value.get(key), (list, dict)) for key in nested_task_keys)

        if is_task_like and not has_nested_tasks:
            candidates.append(value)
            return candidates

        for key in nested_task_keys:
            nested = value.get(key)
            if isinstance(nested, (list, dict)):
                candidates.extend(self._collect_llm_task_candidates(nested))

        if is_task_like and not candidates:
            candidates.append(value)

        return candidates

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
        model_invoker = self.model_invoker
        if model_invoker is None or not hasattr(model_invoker, "invoke_agent_llm"):
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

        llm_result = await model_invoker.invoke_agent_llm(
            system_prompt=WBS_LLM_SYSTEM_PROMPT,
            user_prompt=prompt,
            call_index=1,
            call_total=1,
            call_label="wbs-dev-tasks",
        )
        parsed = parse_json_object(llm_result)
        if not parsed:
            parsed_array = parse_json_array(llm_result)
            if not parsed_array:
                return []
            parsed = {"development_tasks": parsed_array}

        groups = (
            parsed.get("development_tasks")
            or parsed.get("tasks")
            or parsed.get("items")
            or parsed.get("data")
            or []
        )
        insert_after_phase = bool(parsed.get("tasks")) and not bool(parsed.get("development_tasks"))
        if not isinstance(groups, list):
            groups = [groups]

        task_candidates = self._collect_llm_task_candidates(groups)
        if not task_candidates:
            task_candidates = self._collect_llm_task_candidates(parsed)
        if not task_candidates:
            logger.warning(
                f"[{self.AGENT_NAME}] LLM response parsed but no task candidates were found | "
                f"response_preview={str(llm_result)[:500]}"
            )
            return []

        normalized: list[dict[str, object]] = []
        for group in task_candidates:
            if not isinstance(group, dict):
                continue
            phase = str(
                group.get("phase")
                or (group.get("metadata") or {}).get("phase")
                or "구현"
            ).strip()
            if not phase:
                phase = "구현"
            name = truncate_text(group.get("name") or group.get("wbs_name") or group.get("task_name") or "", 120)
            if not name:
                continue
            try:
                level = int(str(group.get("level") or group.get("depth") or "3").strip() or "3")
            except ValueError:
                level = 3
            level = 3 if level < 3 else min(level, 4)
            description = truncate_text(group.get("description") or name, 700)
            source_requirement_ids = group.get("source_requirement_ids") or []
            if isinstance(source_requirement_ids, str):
                source_requirement_ids = [source_requirement_ids]
            if not source_requirement_ids:
                source_requirement_ids = self._guess_source_requirement_ids(atoms, phase, name)
            deliverable = str(group.get("deliverable") or self._resolve_deliverable_local(name, phase) or "").strip()
            normalized.append(
                {
                    "phase": phase,
                    "level": str(level),
                    "name": name,
                    "description": description,
                    "source_requirement_ids": [str(value) for value in source_requirement_ids if value],
                    "_insert_after_phase": insert_after_phase,
                    "metadata": {
                        "phase": phase,
                        "deliverable": deliverable,
                        "generation_source": "llm",
                    },
                }
            )
        if not normalized:
            logger.warning(
                f"[{self.AGENT_NAME}] LLM response parsed but no WBS tasks were normalized | "
                f"parsed_keys={list(parsed.keys())}"
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
        return candidates

    def _merge_llm_development_tasks(
        self,
        base_tasks: list[dict[str, object]],
        llm_tasks: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        phase_buckets: dict[str, list[dict[str, object]]] = {phase: [] for phase in self.DEVELOPMENT_PHASE_ORDER}
        overflow_tasks: list[dict[str, object]] = []
        append_tasks: list[dict[str, object]] = []

        for index, extra in enumerate(llm_tasks, start=1):
            phase = str(extra.get("phase") or "").strip()
            if phase == "개발":
                phase = "구현"
            materialized = self._materialize_llm_task(extra, phase=phase, index=index)
            metadata = materialized.get("metadata") or {}
            insert_after_phase = False
            if isinstance(metadata, dict):
                insert_after_phase = bool(metadata.pop("_insert_after_phase", False))
            if phase not in phase_buckets:
                overflow_tasks.append(materialized)
                continue
            if insert_after_phase:
                phase_buckets[phase].append(materialized)
            else:
                append_tasks.append(materialized)

        merged: list[dict[str, object]] = []
        for task in base_tasks:
            merged.append(task)
            task_phase = str((task.get("metadata") or {}).get("phase") or "").strip()
            if task_phase in phase_buckets and phase_buckets[task_phase]:
                merged.extend(phase_buckets[task_phase])
                phase_buckets[task_phase] = []

        for phase in self.DEVELOPMENT_PHASE_ORDER:
            if phase_buckets[phase]:
                merged.extend(phase_buckets[phase])

        merged.extend(append_tasks)
        merged.extend(overflow_tasks)
        return merged

    def _phase_counts(self, tasks: list[dict[str, object]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in tasks or []:
            phase = str((task.get("phase") or (task.get("metadata") or {}).get("phase") or "")).strip()
            if phase:
                counts[phase] = counts.get(phase, 0) + 1
        return counts

    def _materialize_llm_task(
        self,
        extra: dict[str, object],
        *,
        phase: str,
        index: int,
    ) -> dict[str, object]:
        extra_metadata = dict(extra.get("metadata") or {})
        extra_metadata.setdefault("phase", phase)
        extra_metadata.setdefault(
            "deliverable",
            self._resolve_deliverable_local(str(extra.get("name") or ""), phase),
        )
        extra_metadata.setdefault("generation_source", "llm")
        if extra.get("_insert_after_phase"):
            extra_metadata["_insert_after_phase"] = True
        level_text = str(extra.get("level") or extra_metadata.get("level") or "3").strip() or "3"
        extra_metadata["level"] = level_text
        if not extra_metadata.get("wbs_id"):
            try:
                extra_metadata["wbs_id"] = str(int(level_text) + 1)
            except ValueError:
                extra_metadata["wbs_id"] = "4"
        extra_metadata.setdefault("id", extra_metadata.get("wbs_id"))
        extra_metadata.setdefault("worker", "작업자")
        return {
            "task_id": f"WBS-LLM-{phase[:1] or 'X'}-{index:02d}",
            "name": str(extra.get("name") or "").strip(),
            "description": str(extra.get("description") or "").strip(),
            "source_requirement_ids": extra.get("source_requirement_ids") or [],
            "metadata": extra_metadata,
        }

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
            generation_source = str(metadata.get("generation_source") or "").strip()
            if generation_source not in {"llm", "fallback"}:
                continue
            if phase in windows:
                current_phase = phase
            elif current_phase not in windows:
                continue
            start_value, end_value = windows[current_phase]
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
            detail_tasks = self._build_phase_detail_tasks(
                atoms,
                project_name=str((request.context or {}).get("project_name") or (request.context or {}).get("project_nm") or "프로젝트명"),
                project_type=project_type,
                existing_phase_counts=self._phase_counts(llm_tasks),
            )
            if llm_tasks:
                generated_tasks = list(llm_tasks)
            else:
                logger.warning(
                    f"[{self.AGENT_NAME}] LLM generation produced no tasks; "
                    "falling back to deterministic development detail rows"
                )
                generated_tasks = detail_tasks

            tasks = self._merge_llm_development_tasks(base_tasks, generated_tasks)

            self._apply_llm_development_schedule(
                tasks,
                project_start=start_date,
                project_end=end_date,
            )
            if self.model_invoker is None and self._has_invalid_explicit_schedule_context(
                request.context
            ):
                self._strip_schedule_fields(tasks)

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
                        "process_rule": "Common WBS template rows plus LLM-generated development tasks",
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
