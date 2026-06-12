# EN: Core agent adapter for generating unit test case artifacts.
# KO: 단위테스트케이스 산출물 생성을 위한 Core Agent adapter입니다.

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    parse_json_array,
    parse_json_object,
    truncate_text,
)

logger = get_logger(__name__)

UNIT_TEST_LLM_SYSTEM_PROMPT = """
너는 PM Agent의 단위테스트케이스 생성기다.
요구사항명세서와 화면설계서 맥락을 바탕으로 단위테스트케이스를 JSON으로 생성하라.
반드시 JSON 객체만 반환한다.

스키마:
{
  "artifact_type": "UNITTEST_SPEC",
  "test_cases": [
    {
      "test_case_id": "TEST-001",
      "test_case_name": "테스트명",
      "requirement_id": "REQ-00001",
      "requirement_name": "요구사항명",
      "scenario_id": "SCN-001",
      "test_content": "검증해야 할 내용",
      "metadata": {}
    }
  ],
  "metadata": {}
}

규칙:
- 요구사항을 그대로 옮기지 말고 실제 테스트에서 필요한 정상/예외/경계/권한/데이터 검증 항목을 포함한다.
- 요구사항 하나당 1~3개 정도의 테스트케이스를 제안한다.
- test_content는 실행 가능한 수준으로 구체적으로 작성한다.
- 화면설계서가 있으면 입력/조회/저장/삭제/검색/팝업/권한 검증을 함께 고려한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


class UnitTestAgent:
    """Generates deterministic unit test cases from requirement-spec rows."""

    AGENT_NAME = "UnitTestAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}"
        )

        try:
            requirements = self._requirement_items(request)
            if not requirements:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No requirement context available for unit test generation",
                )

            screens = self._screen_items(request)
            test_cases = await self._generate_with_llm(request, requirements)
            if not test_cases:
                test_cases = self._build_test_cases(requirements, request=request, screens=screens)
            if not test_cases:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="Unit test case generation produced no test cases",
                )

            context = request.context or {}
            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result={
                    "artifact_type": "UNITTEST_SPEC",
                    "test_cases": test_cases,
                    "metadata": {
                        "project_id": request.project_id,
                        "project_name": str(
                            context.get("project_name")
                            or context.get("project_nm")
                            or "프로젝트명"
                        ),
                        "author": self._author(context),
                        "generated_by": self.AGENT_NAME,
                        "source_requirement_count": len(requirements),
                        "process_rule": "Create one unit test case per requirement row",
                    },
                },
            )
        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    async def _generate_with_llm(
        self,
        request: AgentRequest,
        requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        orchestrator = (request.context or {}).get("generation_orchestrator")
        if orchestrator is None or not hasattr(orchestrator, "invoke_agent_llm"):
            return []

        prompt = f"""
Project ID: {request.project_id}
Project name: {self._project_name(request.context or {})}
Requirement summary:
{json.dumps(self._build_requirement_digest(requirements), ensure_ascii=False, default=str)}
""".strip()

        llm_result = await orchestrator.invoke_agent_llm(
            system_prompt=UNIT_TEST_LLM_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=5000,
        )
        parsed = parse_json_object(llm_result)
        if not parsed:
            parsed_array = parse_json_array(llm_result)
            if not parsed_array:
                return []
            parsed = {"test_cases": parsed_array}

        test_cases = parsed.get("test_cases") or parsed.get("items") or []
        if not isinstance(test_cases, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, test_case in enumerate(test_cases, start=1):
            if not isinstance(test_case, dict):
                continue
            requirement_id = str(test_case.get("requirement_id") or f"REQ-{index:04d}").strip()
            requirement_name = str(
                test_case.get("requirement_name")
                or test_case.get("title")
                or requirement_id
            ).strip()
            scenario_id = str(test_case.get("scenario_id") or f"SCN-{index:03d}").strip()
            test_case_id = str(test_case.get("test_case_id") or f"TEST-{index:03d}").strip()
            test_case_name = str(test_case.get("test_case_name") or requirement_name).strip()
            screen_hint = self._match_screen_hint(
                self._screen_items(request),
                requirement_id,
                requirement_name,
            )
            test_content = self._build_test_content(
                requirement_name=requirement_name,
                requirement_description=test_case.get("test_content")
                or test_case.get("description")
                or requirement_name,
                screen_hint=screen_hint,
            )
            normalized.append(
                {
                    "test_case_id": test_case_id,
                    "test_case_name": test_case_name,
                    "requirement_id": requirement_id,
                    "requirement_name": requirement_name,
                    "scenario_id": scenario_id,
                    "test_content": test_content,
                    "metadata": {
                        "row_number": index,
                        "author": self._author(request.context or {}),
                        "requirement_id": requirement_id,
                        "requirement_name": requirement_name,
                        "scenario_id": scenario_id,
                        "test_case_id": test_case_id,
                        "test_case_name": test_case_name,
                        "test_content": test_content,
                        "generation_source": "llm",
                    },
                }
            )
        return normalized

    def _requirement_items(self, request: AgentRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        for key in ("requirement_artifact", "source_artifact", "previous_artifact", "artifact"):
            value = context.get(key)
            if isinstance(value, dict) and isinstance(value.get("requirements"), list):
                return [
                    self._flatten_requirement(item)
                    for item in value["requirements"]
                    if isinstance(item, dict)
                ]

        items: list[dict[str, Any]] = []
        for document in request.documents or []:
            metadata = document.get("metadata") or {}
            requirement = metadata.get("requirement")
            if isinstance(requirement, dict):
                items.append(self._flatten_requirement(requirement))
                continue
            parsed = parse_json_object(str(document.get("text", "")))
            if parsed and isinstance(parsed.get("requirements"), list):
                items.extend(
                    self._flatten_requirement(item)
                    for item in parsed["requirements"]
                    if isinstance(item, dict)
                )
        return items

    def _screen_items(self, request: AgentRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        for key in ("screen_artifact", "screen_design_artifact", "source_screen_artifact", "artifact"):
            value = context.get(key)
            if isinstance(value, dict) and isinstance(value.get("screens"), list):
                return [
                    self._flatten_screen(item)
                    for item in value["screens"]
                    if isinstance(item, dict)
                ]
        return []

    def _build_requirement_digest(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        digest: list[dict[str, Any]] = []
        for item in requirements:
            digest.append(
                {
                    "requirement_id": str(item.get("requirement_id") or ""),
                    "requirement_name": str(item.get("requirement_name") or item.get("title") or ""),
                    "description": truncate_text(item.get("description") or "", 220),
                    "biz_requirement_id": str(item.get("biz_requirement_id") or ""),
                    "biz_requirement_name": str(item.get("biz_requirement_name") or ""),
                    "domain": str(item.get("domain") or ""),
                    "feature": str(item.get("feature") or ""),
                }
            )
        return digest

    def _project_name(self, context: dict[str, Any]) -> str:
        return str(context.get("project_name") or context.get("project_nm") or "프로젝트명")

    def _flatten_requirement(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") or {}
        return {
            **metadata,
            **item,
            "requirement_id": item.get("requirement_id") or metadata.get("requirement_id") or item.get("id") or "",
            "requirement_name": (
                metadata.get("requirement_name")
                or item.get("requirement_name")
                or item.get("title")
                or ""
            ),
            "description": metadata.get("description") or item.get("description") or "",
            "biz_requirement_id": metadata.get("biz_requirement_id") or item.get("biz_requirement_id") or "",
        }

    def _flatten_screen(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") or {}
        return {
            **metadata,
            **item,
            "screen_id": item.get("screen_id") or metadata.get("screen_no") or "",
            "screen_name": item.get("name") or item.get("screen_name") or metadata.get("screen_name") or "",
            "description": item.get("description") or metadata.get("description") or "",
            "source_requirement_ids": item.get("source_requirement_ids") or metadata.get("source_requirement_ids") or [],
        }

    def _match_screen_hint(
        self,
        screens: list[dict[str, Any]],
        requirement_id: str,
        requirement_name: str,
    ) -> dict[str, Any] | None:
        if not screens:
            return None
        req_lower = f"{requirement_id} {requirement_name}".lower()
        for screen in screens:
            screen_ids = screen.get("source_requirement_ids") or []
            if any(str(value).strip() == requirement_id for value in screen_ids):
                return screen
            screen_text = f"{screen.get('screen_name') or ''} {screen.get('description') or ''}".lower()
            if any(token and token in screen_text for token in req_lower.split()):
                return screen
        return screens[0]

    def _build_test_cases(
        self,
        requirements: list[dict[str, Any]],
        *,
        request: AgentRequest,
        screens: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        counters: dict[str, int] = {}
        test_cases: list[dict[str, Any]] = []
        author = self._author(request.context or {})
        for index, requirement in enumerate(requirements, start=1):
            requirement_id = str(requirement.get("requirement_id") or f"REQ-{index:04d}").strip()
            requirement_name = str(requirement.get("requirement_name") or requirement.get("title") or requirement_id).strip()
            biz_requirement_id = str(requirement.get("biz_requirement_id") or f"Biz-{index:04d}").strip()
            biz_number = self._biz_number(biz_requirement_id, fallback=index)
            counters[biz_number] = counters.get(biz_number, 0) + 1
            test_case_id = f"TEST-{biz_number}-{counters[biz_number]:03d}"
            screen_hint = self._match_screen_hint(screens or [], requirement_id, requirement_name)
            test_content = self._build_test_content(
                requirement_name=requirement_name,
                requirement_description=requirement.get("description"),
                screen_hint=screen_hint,
            )
            test_cases.append(
                {
                    "test_case_id": test_case_id,
                    "test_case_name": f"{requirement_name} 화면",
                    "requirement_id": requirement_id,
                    "requirement_name": requirement_name,
                    "scenario_id": biz_requirement_id,
                    "test_content": test_content,
                    "metadata": {
                        "row_number": index,
                        "author": author,
                        "biz_requirement_id": biz_requirement_id,
                        "biz_requirement_name": requirement.get("biz_requirement_name") or "",
                        "requirement_id": requirement_id,
                        "requirement_name": requirement_name,
                        "scenario_id": biz_requirement_id,
                        "test_case_id": test_case_id,
                        "test_case_name": f"{requirement_name} 화면",
                        "test_content": test_content,
                    },
                }
        )
        return test_cases

    def _build_test_content(
        self,
        *,
        requirement_name: str,
        requirement_description: Any,
        screen_hint: dict[str, Any] | None = None,
    ) -> str:
        requirement_text = str(requirement_description or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
        if screen_hint:
            screen_name = str(screen_hint.get("screen_name") or requirement_name or "화면").strip()
            screen_description = str(screen_hint.get("description") or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
            lines = [
                f"{screen_name} 화면에서 조회/입력/저장 흐름을 검증한다.",
                f"{screen_name}의 필수 항목 검증, 권한 확인, 결과 반영을 점검한다.",
            ]
            if screen_description:
                lines.append(truncate_text(screen_description, 260))
            elif requirement_text:
                lines.append(truncate_text(requirement_text, 260))
            return "\n".join(line for line in lines if line).strip()

        if requirement_text:
            lines = [
                f"{requirement_name}의 정상 처리 결과를 검증한다.",
                f"{requirement_name}의 예외/경계 조건 및 입력값 검증을 확인한다.",
                truncate_text(requirement_text, 260),
            ]
            return "\n".join(line for line in lines if line).strip()

        return f"{requirement_name}의 동작을 검증한다."

    def _biz_number(self, biz_requirement_id: str, *, fallback: int) -> str:
        match = re.search(r"(\d+)", biz_requirement_id or "")
        if match:
            return match.group(1)
        return f"{fallback:04d}"

    def _author(self, context: dict[str, Any]) -> str:
        return str(
            context.get("author")
            or context.get("writer")
            or context.get("created_by")
            or context.get("user_id")
            or "작성자"
        )


unit_test_agent = UnitTestAgent()
