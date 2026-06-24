# EN: Core agent adapter for generating unit test case artifacts.
# KO: 단위테스트케이스 산출물 생성을 위한 Core Agent adapter입니다.

from __future__ import annotations

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
화면설계서의 화면 목록과 description을 바탕으로 단위테스트케이스를 JSON으로 생성하라.
반드시 JSON 객체만 반환한다.

스키마:
{
  "artifact_type": "UNITTEST_SPEC",
  "test_cases": [
    {
      "test_case_id": "TEST-001",
      "test_case_name": "테스트명",
      "screen_id": "SCR-001",
      "screen_name": "화면명",
      "scenario_id": "SCN-001",
      "test_content": "검증해야 할 내용",
      "metadata": {}
    }
  ],
  "metadata": {}
}

규칙:
- 화면 하나당 테스트케이스 하나를 생성한다.
- 화면설계서의 screen_name과 source_requirement_ids를 그대로 반영한다.
- test_case_name은 화면명과 검증 성격(기본/처리/조회/수정/삭제/권한/팝업 등)을 자연스럽게 포함한다.
- test_content는 화면설계서 description을 활용해 복수의 점검 항목으로 작성한다.
- 화면설계서가 있으면 화면 설명, 입력/조회/저장/삭제/검색/팝업/권한 검증을 함께 고려한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


class UnitTestAgent:
    """Generates deterministic unit test cases from screen-design rows."""

    AGENT_NAME = "UnitTestAgent"

    def __init__(self, *, model_invoker=None) -> None:
        self.model_invoker = model_invoker

    def with_model_invoker(self, model_invoker) -> "UnitTestAgent":
        return UnitTestAgent(model_invoker=model_invoker)

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(
            f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}"
        )

        try:
            screens = self._screen_items(request)
            screens = self._screen_pages_from_third(screens)
            used_default_draft = False
            if not screens:
                screens = self._fallback_screens_from_request(request)
                used_default_draft = True

            test_cases = self._build_test_cases(screens, request=request)
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
                        "source_screen_count": len(screens),
                        "process_rule": "Create one unit test case per screen description",
                        **(self._default_draft_metadata() if used_default_draft else {}),
                    },
                },
            )
        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    def _fallback_screens_from_request(self, request: AgentRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        query = str(context.get("query") or "").strip()
        project_name = str(
            context.get("project_name")
            or context.get("project_nm")
            or request.project_id
            or "프로젝트"
        ).strip()
        subject = truncate_text(query or f"{project_name} 단위테스트케이스 생성", 100)
        common_metadata = {
            "generation_source": "default_draft",
            "assumptions": [
                "참고 화면설계서가 없어 일반적인 화면 검증 관점으로 초안을 작성했습니다.",
            ],
            "additional_check_required": [
                "실제 화면 목록, 화면 흐름, 데이터 조건, 예외 정책은 확인이 필요합니다.",
            ],
        }
        return [
            {
                "screen_id": "SCR-001",
                "screen_name": subject,
                "description": f"{project_name} 요청의 주요 화면 흐름과 검증 포인트를 확인한다.",
                "source_requirement_ids": [],
                **common_metadata,
            },
            {
                "screen_id": "SCR-002",
                "screen_name": "입력값 및 예외 검증",
                "description": "필수 입력값, 경계값, 권한, 오류 메시지 처리를 확인한다.",
                "source_requirement_ids": [],
                **common_metadata,
            },
        ]

    def _default_draft_metadata(self) -> dict[str, object]:
        return {
            "generation_source": "default_draft",
            "가정사항": [
                "참고 화면설계서가 없어 일반적인 화면 검증 관점으로 초안을 작성했습니다.",
            ],
            "추가 확인 필요 항목": [
                "실제 화면 목록, 화면 흐름, 데이터 조건, 예외 정책은 확인이 필요합니다.",
            ],
        }

    async def _generate_with_llm(
        self,
        request: AgentRequest,
        screens: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Keep the method as a stable async fallback, but generate from the
        # screen-design source deterministically so screen names and source IDs
        # stay aligned with the selected pages.
        return self._build_test_cases(screens, request=request)

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
        for key in (
            "screen_artifact",
            "screen_design_artifact",
            "source_screen_artifact",
            "artifact",
        ):
            value = context.get(key)
            screens = self._extract_screens_from_value(value)
            if screens:
                return self._deduplicate_screens(screens)

        items: list[dict[str, Any]] = []
        for document in request.documents or []:
            metadata = document.get("metadata") or {}
            for key in ("screen_artifact", "screen_design_artifact", "screen"):
                screens = self._extract_screens_from_value(metadata.get(key))
                if screens:
                    items.extend(screens)
            text = str(document.get("text", ""))
            parsed = parse_json_object(text)
            if parsed:
                screens = self._extract_screens_from_value(parsed)
                if screens:
                    items.extend(screens)
            text_screens = self._extract_screens_from_text(text)
            if text_screens:
                items.extend(text_screens)
        deduped = self._deduplicate_screens(items)
        if deduped:
            return deduped
        return self._screens_from_document_chunks(request.documents or [])

    def _deduplicate_screens(
        self,
        screens: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for screen in screens:
            screen_id = str(screen.get("screen_id") or "").strip()
            screen_name = str(screen.get("screen_name") or screen.get("name") or "").strip()
            description = str(screen.get("description") or "").strip()
            if self._is_preliminary_screen(screen_name, description):
                continue
            key = (screen_id, screen_name, description)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(screen)
        return deduped

    def _extract_screens_from_value(
        self,
        value: Any,
    ) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [
                self._flatten_screen(item)
                for item in value
                if isinstance(item, dict)
            ]
        if not isinstance(value, dict):
            return []
        if (
            value.get("screen_id")
            and (value.get("name") or value.get("screen_name") or value.get("description"))
        ):
            return [self._flatten_screen(value)]
        if isinstance(value.get("screens"), list):
            return [
                self._flatten_screen(item)
                for item in value["screens"]
                if isinstance(item, dict)
            ]
        if value.get("artifact_type") == "SCREEN_DESIGN" and isinstance(
            value.get("items"), list
        ):
            return [
                self._flatten_screen(item)
                for item in value["items"]
                if isinstance(item, dict)
            ]
        return []

    def _extract_screens_from_text(self, text: str) -> list[dict[str, Any]]:
        normalized_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if "[Slide " in normalized_text:
            slide_screens = self._extract_screens_from_slide_text(normalized_text)
            if slide_screens:
                return slide_screens
        if "# SCREEN_DESIGN" not in normalized_text and "|" not in normalized_text:
            return []

        screens: list[dict[str, Any]] = []
        for raw_line in normalized_text.splitlines():
            line = str(raw_line or "").strip()
            if not line or line.startswith("# "):
                continue
            if line.lower().startswith("screen_id"):
                continue
            if "|" not in line:
                continue
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 5:
                continue
            screen_id = cells[0]
            screen_name = cells[1]
            description = cells[2]
            if self._is_preliminary_screen(screen_name, description):
                continue
            source_requirement_ids = [
                value.strip()
                for value in cells[4].split(",")
                if value.strip()
            ]
            if not screen_id or not screen_name:
                continue
            screens.append(
                self._flatten_screen(
                    {
                        "screen_id": screen_id,
                        "screen_name": screen_name,
                        "description": description,
                        "source_requirement_ids": source_requirement_ids,
                    }
                )
            )
        return screens

    def _extract_screens_from_slide_text(self, text: str) -> list[dict[str, Any]]:
        slides = re.split(r"(?m)^\[Slide\s+(\d+)\]\s*", text)
        if len(slides) < 3:
            return []

        screens: list[dict[str, Any]] = []
        for index in range(1, len(slides), 2):
            slide_no_text = slides[index]
            slide_body = slides[index + 1] if index + 1 < len(slides) else ""
            try:
                slide_no = int(slide_no_text)
            except ValueError:
                continue
            if slide_no < 3:
                continue

            lines = [
                line.strip()
                for line in slide_body.splitlines()
                if line.strip() and not line.strip().startswith("# ")
            ]
            if not lines:
                continue

            pipe_rows = [line for line in lines if "|" in line]
            screen_name = self._slide_screen_name(lines, pipe_rows)
            if not screen_name:
                continue

            description = self._slide_screen_description(lines, pipe_rows)
            source_requirement_ids = self._slide_source_requirement_ids(lines, pipe_rows)
            screens.append(
                self._flatten_screen(
                    {
                        "screen_id": f"SCR-{slide_no:03d}",
                        "screen_name": screen_name,
                        "description": description,
                        "source_requirement_ids": source_requirement_ids,
                        "metadata": {"page_number": slide_no},
                    }
                )
            )
        return screens

    def _slide_screen_name(self, lines: list[str], pipe_rows: list[str]) -> str:
        for line in lines:
            if "|" in line:
                continue
            if self._is_preliminary_screen(line, "") or self._is_document_header(line):
                continue
            return line
        if pipe_rows:
            first_row = [cell.strip() for cell in pipe_rows[0].split("|") if cell.strip()]
            if len(first_row) >= 2:
                return first_row[1]
        return ""

    def _slide_screen_description(self, lines: list[str], pipe_rows: list[str]) -> str:
        description_parts: list[str] = []
        for line in lines:
            if self._is_preliminary_screen(line, "") or self._is_document_header(line):
                continue
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|")]
                if len(cells) >= 3:
                    description_parts.append(cells[2])
                continue
            if line == self._slide_screen_name(lines, pipe_rows):
                continue
            description_parts.append(line)
        return " ".join(part for part in description_parts if part).strip()

    def _slide_source_requirement_ids(self, lines: list[str], pipe_rows: list[str]) -> list[str]:
        ids: list[str] = []
        for line in lines:
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|")]
                if len(cells) >= 5:
                    ids.extend(
                        value.strip()
                        for value in cells[4].split(",")
                        if value.strip()
                    )
            ids.extend(
                match.group(0)
                for match in re.finditer(r"\b[A-Z]{2,5}-?\d[\d.]*\b", line)
            )
        deduped: list[str] = []
        seen: set[str] = set()
        for value in ids:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _is_preliminary_screen(self, screen_name: str, description: str) -> bool:
        text = f"{screen_name} {description}".lower()
        preliminary_keywords = (
            "표지",
            "목차",
            "개요",
            "문서정보",
            "문서 정보",
            "버전이력",
            "버전 이력",
            "이력",
        )
        return any(keyword.lower() in text for keyword in preliminary_keywords)

    def _is_document_header(self, text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        if value.startswith("# "):
            return True
        return any(
            keyword in value
            for keyword in (
                "screen_design",
                "screen design",
                "part-",
                "slide ",
                "page ",
            )
        )

    def _screens_from_document_chunks(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        screens: list[dict[str, Any]] = []
        for document in documents:
            chunk_index = self._chunk_index(document)
            if chunk_index is not None and chunk_index < 2:
                continue
            text = str(document.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            if not text:
                continue
            screen_name = self._guess_screen_name_from_text(
                text,
                fallback=str(document.get("section_title") or "").strip(),
            )
            if not screen_name:
                continue
            description = self._guess_screen_description_from_text(text, screen_name)
            source_requirement_ids = self._guess_requirement_ids_from_text(text)
            screen_id = str(document.get("screen_id") or "").strip() or self._screen_id_from_chunk(document)
            screens.append(
                self._flatten_screen(
                    {
                        "screen_id": screen_id,
                        "screen_name": screen_name,
                        "description": description,
                        "source_requirement_ids": source_requirement_ids,
                        "metadata": {
                            "page_number": self._page_number_from_chunk(document),
                            "chunk_index": chunk_index,
                        },
                    }
                )
            )
        return self._deduplicate_screens(screens)

    def _chunk_index(self, document: dict[str, Any]) -> int | None:
        for key in ("chunk_index", "page_index", "page_number", "slide_index", "slide_number"):
            value = document.get(key)
            if value in (None, ""):
                metadata = document.get("metadata") or {}
                value = metadata.get(key)
            if value in (None, ""):
                continue
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                continue
        return None

    def _page_number_from_chunk(self, document: dict[str, Any]) -> int | None:
        chunk_index = self._chunk_index(document)
        if chunk_index is None:
            return None
        return chunk_index + 1

    def _screen_id_from_chunk(self, document: dict[str, Any]) -> str:
        chunk_index = self._chunk_index(document)
        if chunk_index is None:
            return str(document.get("document_id") or "SCR-UNK").strip()
        return f"SCR-{chunk_index + 1:03d}"

    def _guess_screen_name_from_text(self, text: str, *, fallback: str = "") -> str:
        fallback = str(fallback or "").strip()
        if fallback and not self._is_preliminary_screen(fallback, "") and not self._is_document_header(fallback):
            return fallback
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("# ")
        ]
        for line in lines:
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|")]
                if len(cells) >= 2 and cells[1]:
                    if self._is_document_header(cells[1]):
                        continue
                    return cells[1]
            if not self._is_preliminary_screen(line, "") and not self._is_document_header(line):
                cleaned = re.sub(r"^\s*(?:[•·ㆍ-]+|\d+[.)])\s*", "", line).strip()
                if cleaned:
                    return cleaned
        return fallback

    def _guess_screen_description_from_text(self, text: str, screen_name: str) -> str:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("# ")
        ]
        description_parts: list[str] = []
        for line in lines:
            if screen_name and screen_name in line:
                continue
            if self._is_document_header(line):
                continue
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|")]
                if len(cells) >= 3 and cells[2]:
                    description_parts.append(cells[2])
                elif len(cells) >= 4:
                    description_parts.append(cells[3])
            else:
                cleaned = re.sub(r"^\s*(?:[•·ㆍ-]+|\d+[.)])\s*", "", line).strip()
                if cleaned and cleaned != screen_name:
                    description_parts.append(cleaned)
        description = " ".join(description_parts).strip()
        return description or screen_name

    def _guess_requirement_ids_from_text(self, text: str) -> list[str]:
        ids: list[str] = []
        for match in re.finditer(r"\b[A-Z]{2,5}-?\d[\d.]*\b", text):
            value = match.group(0).strip()
            if value and value not in ids:
                ids.append(value)
        return ids

    def _build_screen_digest(self, screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        digest: list[dict[str, Any]] = []
        for item in screens:
            digest.append(
                {
                    "screen_id": str(item.get("screen_id") or ""),
                    "screen_name": str(item.get("screen_name") or item.get("name") or ""),
                    "description": truncate_text(item.get("description") or "", 220),
                    "source_requirement_ids": [
                        str(value)
                        for value in (item.get("source_requirement_ids") or [])
                        if str(value).strip()
                    ],
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
        screens: list[dict[str, Any]],
        *,
        request: AgentRequest,
    ) -> list[dict[str, Any]]:
        test_cases: list[dict[str, Any]] = []
        author = self._author(request.context or {})
        for index, screen in enumerate(screens, start=1):
            screen_id = str(screen.get("screen_id") or f"SCR-{index:03d}").strip()
            screen_name = str(
                screen.get("screen_name")
                or screen.get("name")
                or screen_id
            ).strip()
            description = str(screen.get("description") or "").strip()
            source_requirement_ids = [
                str(value).strip()
                for value in (screen.get("source_requirement_ids") or [])
                if str(value).strip()
            ]
            requirement_id = source_requirement_ids[0] if source_requirement_ids else screen_id
            test_case_id = f"TEST-{index:04d}"
            scenario_id = f"SCN-{index:03d}"
            test_case_name = self._test_case_name(screen_name, description)
            test_content = self._build_test_content(
                requirement_name=screen_name,
                requirement_description=description or screen_name,
                screen_hint=screen,
            )
            test_cases.append(
                {
                    "test_case_id": test_case_id,
                    "test_case_name": test_case_name,
                    "requirement_id": requirement_id,
                    "requirement_name": screen_name,
                    "scenario_id": scenario_id,
                    "test_content": test_content,
                    "metadata": {
                        "row_number": index,
                        "author": author,
                        "screen_id": screen_id,
                        "screen_name": screen_name,
                        "screen_description": description,
                        "source_requirement_ids": source_requirement_ids,
                        "requirement_id": requirement_id,
                        "requirement_name": screen_name,
                        "scenario_id": scenario_id,
                        "test_case_id": test_case_id,
                        "test_case_name": test_case_name,
                        "test_content": test_content,
                    },
                }
            )
        return test_cases

    def _test_case_name(self, screen_name: str, screen_description: str) -> str:
        corpus = f"{screen_name} {screen_description}".lower()
        template = self._screen_template_kind(corpus)
        if template == "query":
            return f"{screen_name} 기본 검증"
        if template == "save":
            return f"{screen_name} 처리 검증"
        if template == "edit":
            return f"{screen_name} 처리 검증"
        if template == "delete":
            return f"{screen_name} 처리 검증"
        if template == "authority":
            return f"{screen_name} 권한 검증"
        if template == "popup":
            return f"{screen_name} 팝업 검증"
        return f"{screen_name} 기본 검증"

    def _build_test_content(
        self,
        *,
        requirement_name: str,
        requirement_description: Any,
        screen_hint: dict[str, Any] | None = None,
        scenario_label: str | None = None,
        scenario_focus: str | None = None,
    ) -> str:
        requirement_text = str(requirement_description or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
        label_text = f"{scenario_label} " if scenario_label else ""
        if screen_hint:
            screen_name = str(screen_hint.get("screen_name") or requirement_name or "화면").strip()
            screen_description = str(screen_hint.get("description") or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
            lines = self._screen_test_content_lines(
                screen_name=screen_name,
                screen_description=screen_description,
                scenario_label=label_text,
                scenario_focus=scenario_focus,
            )
            if (
                requirement_text
                and requirement_text != screen_name
                and requirement_text != screen_description
            ):
                lines.append(truncate_text(requirement_text, 260))
            return self._number_test_content_lines(
                "\n".join(line for line in lines if line).strip()
            )

        if not requirement_text:
            return " "

        if requirement_text:
            lines = [
                f"{label_text}{requirement_name}의 {scenario_focus or '정상 처리'} 결과를 검증한다.",
                f"{requirement_name}의 예외/경계 조건 및 입력값 검증을 확인한다.",
                truncate_text(requirement_text, 260),
            ]
            return self._number_test_content_lines("\n".join(line for line in lines if line).strip())

        return self._number_test_content_lines(f"{label_text}{requirement_name}의 동작을 검증한다.")

    def _screen_test_content_lines(
        self,
        *,
        screen_name: str,
        screen_description: str,
        scenario_label: str | None,
        scenario_focus: str | None,
    ) -> list[str]:
        corpus = f"{screen_name} {screen_description}".lower()
        description_points = self._screen_description_points(screen_name, screen_description)
        lines = self._screen_template_lines(
            screen_name=screen_name,
            screen_description=screen_description,
            corpus=corpus,
            description_points=description_points,
        )

        if scenario_label:
            lines[0] = f"{scenario_label}{lines[0]}"
        if scenario_focus:
            lines[0] = f"{lines[0]} ({scenario_focus})"

        if description_points:
            ordered_lines: list[str] = []
            for point in description_points:
                if point and point not in ordered_lines:
                    ordered_lines.append(point)
            for candidate in lines:
                if candidate and candidate not in ordered_lines:
                    ordered_lines.append(candidate)
            lines = ordered_lines
        elif screen_description and truncate_text(screen_description, 260) not in lines:
            lines.insert(0, truncate_text(screen_description, 260))

        if len(lines) < 2:
            lines.append(f"{screen_name}의 기본 화면 요소를 확인한다.")

        return lines[:6]

    def _screen_template_lines(
        self,
        *,
        screen_name: str,
        screen_description: str,
        corpus: str,
        description_points: list[str],
    ) -> list[str]:
        template = self._screen_template_kind(corpus)
        if not description_points:
            description_points = [f"{screen_name} 화면의 설명과 동작을 검증한다."]

        templates: dict[str, list[str]] = {
            "query": [
                f"{screen_name} 화면 진입 시 기본 조회 조건과 표시 항목이 정상 노출되는지 확인한다.",
                f"{screen_name}의 조회 조건 입력 후 결과 목록이 설명과 일치하게 반영되는지 확인한다.",
                f"{screen_name}의 검색어, 필터, 정렬, 페이징이 정상 동작하는지 확인한다.",
                f"{screen_name}의 조회 초기화 또는 재조회 동작이 정상 반영되는지 확인한다.",
            ],
            "save": [
                f"{screen_name} 화면의 필수 입력 항목과 저장 버튼 상태가 정상인지 확인한다.",
                f"{screen_name}의 정상 저장 후 결과 메시지와 데이터 반영이 설명과 일치하는지 확인한다.",
                f"{screen_name}의 필수값 누락, 형식 오류, 중복 입력에 대한 검증을 확인한다.",
                f"{screen_name} 저장 후 목록 또는 상세 화면에 결과가 반영되는지 확인한다.",
            ],
            "edit": [
                f"{screen_name} 화면 진입 시 현재 값이 정상 조회되는지 확인한다.",
                f"{screen_name}의 수정 저장 후 변경 내용이 정상 반영되는지 확인한다.",
                f"{screen_name}의 수정 전후 값 비교와 수정 이력 반영 여부를 확인한다.",
                f"{screen_name}의 수정 실패 시 오류 메시지와 롤백 여부를 확인한다.",
            ],
            "delete": [
                f"{screen_name}의 삭제 전 확인 절차와 삭제 버튼 노출 상태를 확인한다.",
                f"{screen_name}의 정상 삭제 후 목록 반영 및 삭제 완료 메시지를 확인한다.",
                f"{screen_name}의 삭제 권한, 미존재 대상, 중복 삭제 예외를 확인한다.",
                f"{screen_name}의 삭제 후 재조회 시 대상이 제외되는지 확인한다.",
            ],
            "authority": [
                f"{screen_name}의 권한별 접근 가능 여부를 확인한다.",
                f"{screen_name}의 비권한 사용자 접근 차단과 안내 메시지를 확인한다.",
                f"{screen_name}의 조회, 저장, 수정, 삭제 버튼 노출이 권한별로 다른지 확인한다.",
            ],
            "popup": [
                f"{screen_name}의 팝업 노출 조건과 닫기 동작을 확인한다.",
                f"{screen_name}의 팝업 내 확인 및 취소 처리 결과를 확인한다.",
                f"{screen_name}의 팝업에서 입력한 값이 부모 화면에 정상 반영되는지 확인한다.",
            ],
            "common": [
                f"{screen_name} 화면 진입 시 기본 표시 항목과 초기 상태를 확인한다.",
                f"{screen_name}의 필수값, 경계값, 빈값 검증을 확인한다.",
            ],
        }

        selected = list(description_points[:3])
        for candidate in templates.get(template, templates["common"]):
            if candidate not in selected:
                selected.append(candidate)
        if template == "common":
            selected.append(f"{screen_name}의 결과 조회 또는 저장 후 화면 갱신을 확인한다.")

        return selected[:6]

    def _screen_description_points(
        self,
        screen_name: str,
        screen_description: str,
    ) -> list[str]:
        text = str(screen_description or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return []

        raw_parts = re.split(
            r"[.\n;•·ㆍ]+|(?:\s+그리고\s+)|(?:\s+및\s+)|(?:\s+후\s+)|(?:\s+와\s+)|(?:\s+과\s+)",
            text,
        )
        points: list[str] = []
        seen: set[str] = set()
        for part in raw_parts:
            cleaned = re.sub(r"^\s*(?:[-*•ㆍ]+|\d+[.)])\s*", "", part).strip()
            cleaned = cleaned.strip(" -")
            if len(cleaned) < 4:
                continue

            primary = f"화면 설명 원문: {cleaned}"
            primary_key = primary.lower()
            if primary_key not in seen:
                seen.add(primary_key)
                points.append(primary)

            for derived in self._derive_description_points(screen_name, cleaned, text):
                derived_key = derived.lower()
                if derived_key in seen:
                    continue
                seen.add(derived_key)
                points.append(derived)
                if len(points) >= 4:
                    break

            if len(points) >= 4:
                break

        if len(points) < 2:
            fallback_points = self._derive_description_points(screen_name, text, text)
            for derived in fallback_points:
                derived_key = derived.lower()
                if derived_key in seen:
                    continue
                seen.add(derived_key)
                points.append(derived)
                if len(points) >= 2:
                    break

        return points[:4]

    def _derive_description_points(
        self,
        screen_name: str,
        clause: str,
        corpus: str,
    ) -> list[str]:
        lower_clause = clause.lower()
        lower_corpus = corpus.lower()
        subject = screen_name.strip() or clause.strip() or "화면"

        mapping: list[tuple[list[str], str]] = [
            (
                ["조회", "검색", "list", "find", "목록"],
                f"{subject}의 조회 조건 입력과 조회 결과 반영을 확인한다.",
            ),
            (
                ["상세", "detail"],
                f"{subject}의 상세 화면 진입과 상세 정보 표시를 확인한다.",
            ),
            (
                ["등록", "저장", "추가", "create", "insert", "신규"],
                f"{subject}의 저장 후 결과 메시지와 데이터 반영을 확인한다.",
            ),
            (
                ["수정", "변경", "update", "edit", "편집"],
                f"{subject}의 수정 전후 값 비교와 반영 결과를 확인한다.",
            ),
            (
                ["삭제", "remove", "delete", "제거"],
                f"{subject}의 삭제 후 대상 제외와 삭제 완료 메시지를 확인한다.",
            ),
            (
                ["권한", "인증", "보안", "접근제어"],
                f"{subject}의 권한별 접근 가능 여부와 차단 메시지를 확인한다.",
            ),
            (
                ["팝업", "modal", "dialog", "layer"],
                f"{subject}의 팝업 노출 조건과 확인/취소 동작을 확인한다.",
            ),
            (
                ["입력", "필수", "빈값", "경계", "한도", "최대", "최소", "유효성"],
                f"{subject}의 입력값 유효성과 경계값 검증을 확인한다.",
            ),
            (
                ["오류", "예외", "실패", "invalid", "에러"],
                f"{subject}의 오류 메시지와 예외 처리 결과를 확인한다.",
            ),
        ]

        derived: list[str] = []
        seen: set[str] = {lower_clause}
        for keywords, sentence in mapping:
            if any(keyword in lower_clause or keyword in lower_corpus for keyword in keywords):
                key = sentence.lower()
                if key not in seen:
                    seen.add(key)
                    derived.append(sentence)
            if len(derived) >= 2:
                break

        if not derived:
            derived = [
                f"{subject}의 기본 화면 표시 항목을 확인한다.",
                f"{subject}의 입력값, 결과 반영, 오류 처리 흐름을 확인한다.",
            ]
        elif len(derived) == 1:
            derived.append(f"{subject}의 결과 반영과 사용자 확인 흐름을 확인한다.")

        return derived[:2]

    def _screen_template_kind(self, corpus: str) -> str:
        if any(keyword in corpus for keyword in ("조회", "검색", "list", "find", "목록", "조회조건")):
            return "query"
        if any(keyword in corpus for keyword in ("등록", "저장", "추가", "create", "insert", "신규")):
            return "save"
        if any(keyword in corpus for keyword in ("수정", "변경", "update", "edit", "편집")):
            return "edit"
        if any(keyword in corpus for keyword in ("삭제", "remove", "delete", "제거")):
            return "delete"
        if any(keyword in corpus for keyword in ("권한", "인증", "보안", "접근제어")):
            return "authority"
        if any(keyword in corpus for keyword in ("팝업", "modal", "dialog", "layer")):
            return "popup"
        return "common"

    def _number_test_content_lines(self, value: Any) -> str:
        text = str(value or "").replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text or "\n" not in text:
            return text

        numbered_lines: list[str] = []
        for line in text.split("\n"):
            cleaned = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", line).strip()
            if not cleaned:
                continue
            numbered_lines.append(cleaned)
            if len(numbered_lines) >= 6:
                break

        if len(numbered_lines) <= 1:
            return numbered_lines[0] if numbered_lines else text

        return "\n".join(f"{index}. {line}" for index, line in enumerate(numbered_lines, start=1))

    def _screen_pages_from_third(
        self,
        screens: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not screens:
            return []

        page_numbers = [self._screen_page_number(screen) for screen in screens]
        if not any(page_number is not None for page_number in page_numbers):
            return screens

        filtered: list[dict[str, Any]] = []
        for screen, page_number in zip(screens, page_numbers, strict=False):
            if page_number is None or page_number >= 3:
                filtered.append(screen)
        return filtered

    def _screen_page_number(self, screen: dict[str, Any]) -> int | None:
        metadata = screen.get("metadata") or {}
        for key in (
            "page_no",
            "page_number",
            "page_index",
            "slide_no",
            "slide_index",
            "order",
        ):
            value = screen.get(key)
            if value in (None, ""):
                value = metadata.get(key)
            if value in (None, ""):
                continue
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                continue
        return None

    def _scenario_specs(
        self,
        requirement: dict[str, Any],
        *,
        screen_hint: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        requirement_text = str(requirement.get("description") or "").lower()
        hint_text = " ".join(
            str(value or "").lower()
            for value in (
                screen_hint.get("screen_name") if screen_hint else "",
                screen_hint.get("description") if screen_hint else "",
            )
        )
        corpus = f"{requirement_text} {hint_text}"

        specs: list[dict[str, str]] = [
            {"code": "01", "label": "정상", "focus": "정상 처리"},
        ]
        if any(keyword in corpus for keyword in ("조회", "검색", "list", "find", "목록")):
            specs.append({"code": "02", "label": "조회", "focus": "조회 조건 입력 및 결과 확인"})
        if any(keyword in corpus for keyword in ("등록", "저장", "추가", "create", "insert")):
            specs.append({"code": "03", "label": "저장", "focus": "저장 및 반영 확인"})
        if any(keyword in corpus for keyword in ("수정", "변경", "update", "edit")):
            specs.append({"code": "04", "label": "수정", "focus": "수정 및 반영 확인"})
        if any(keyword in corpus for keyword in ("삭제", "remove", "delete")):
            specs.append({"code": "05", "label": "삭제", "focus": "삭제 및 반영 확인"})
        if any(keyword in corpus for keyword in ("권한", "인증", "보안")):
            specs.append({"code": "06", "label": "권한", "focus": "권한 및 접근 제어"})
        if any(keyword in corpus for keyword in ("경계", "한도", "limit", "최대", "최소", "빈값", "필수")):
            specs.append({"code": "07", "label": "경계", "focus": "경계값 및 필수값 검증"})
        if any(keyword in corpus for keyword in ("오류", "예외", "실패", "invalid", "에러")):
            specs.append({"code": "08", "label": "예외", "focus": "오류 및 예외 처리"})

        deduped: list[dict[str, str]] = []
        seen = set()
        for spec in specs:
            key = spec["code"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(spec)
        return deduped

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
