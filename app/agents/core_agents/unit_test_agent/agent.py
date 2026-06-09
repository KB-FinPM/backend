# EN: Core agent adapter for generating unit test case artifacts.
# KO: 단위테스트케이스 산출물 생성을 위한 Core Agent adapter입니다.

from __future__ import annotations

import re
from typing import Any

from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import parse_json_object, truncate_text

logger = get_logger(__name__)


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

            test_cases = self._build_test_cases(requirements, request=request)
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

    def _build_test_cases(
        self,
        requirements: list[dict[str, Any]],
        *,
        request: AgentRequest,
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
            test_content = self._test_content(requirement.get("description"))
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

    def _test_content(self, value: Any) -> str:
        text = (
            str(value or "")
            .replace("\\n", "\n")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        if not text:
            return " "
        return truncate_text(text, 1000)

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
