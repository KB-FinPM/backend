# EN: Core agent for generating requirement artifacts from structured context.
# KO: 구조화된 컨텍스트를 기반으로 요구사항 산출물을 생성하는 Core Agent입니다.

import json
import re
from typing import Any

from app.core.llm import llm_service
from app.core.logger import get_logger
from app.schemas.agent import AgentRequest, AgentResponse

logger = get_logger(__name__)


class RequirementAgent:
    """
    Generates requirement JSON from retrieved project context.

    The agent may call the shared LLM wrapper, but it returns structured JSON only
    and never accesses DB, S3, vector stores, or FastAPI response objects.
    """

    AGENT_NAME = "RequirementAgent"

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}")

        try:
            prompt = self._build_prompt(request)
            llm_result = await llm_service.invoke(prompt)
            result = self._parse_llm_json(llm_result)
            if result is None:
                result = self._build_draft_from_documents(request)
            if result is None:
                return AgentResponse(
                    success=False,
                    agent_name=self.AGENT_NAME,
                    error="No source document chunks available for requirement generation",
                )

            logger.info(f"[{self.AGENT_NAME}] generate done")
            return AgentResponse(
                agent_name=self.AGENT_NAME,
                result=result,
            )

        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                error=str(exc),
            )

    def _build_prompt(self, request: AgentRequest) -> str:
        context = "\n".join(
            json.dumps(document, ensure_ascii=False) for document in request.documents
        )
        return (
            "Generate a REQUIREMENT_SPEC artifact as valid JSON only.\n"
            "Schema: {artifact_type, requirements[], metadata}.\n"
            "Each requirement must include requirement_id, title, description, "
            "priority, source_document_id, source_chunk_ids, acceptance_criteria.\n\n"
            f"Project ID: {request.project_id}\n"
            f"Context: {json.dumps(request.context or {}, ensure_ascii=False)}\n\n"
            f"Source chunks:\n{context}"
        )

    def _parse_llm_json(self, llm_result: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(llm_result)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", llm_result, flags=re.DOTALL)
        if match is None:
            return None

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        return parsed if isinstance(parsed, dict) else None

    def _build_draft_from_documents(
        self,
        request: AgentRequest,
    ) -> dict[str, Any] | None:
        if not request.documents:
            return None

        requirements: list[dict[str, Any]] = []
        for index, document in enumerate(request.documents, start=1):
            text = str(document.get("text", "")).strip()
            if not text:
                continue

            requirement_id = f"RQ-{index:03d}"
            chunk_id = document.get("chunk_id")
            requirements.append(
                {
                    "requirement_id": requirement_id,
                    "title": self._build_title(text, requirement_id),
                    "description": self._build_description(text),
                    "priority": "SHOULD",
                    "source_document_id": document.get("document_id"),
                    "source_chunk_ids": [chunk_id] if chunk_id else [],
                    "acceptance_criteria": [
                        f"The delivered system satisfies {requirement_id}."
                    ],
                    "rationale": "Drafted from retrieved project document chunk.",
                }
            )

        if not requirements:
            return None

        return {
            "artifact_type": "REQUIREMENT_SPEC",
            "requirements": requirements,
            "metadata": {
                "project_id": request.project_id,
                "generated_by": self.AGENT_NAME,
                "source_chunk_count": len(request.documents),
            },
        }

    def _build_title(self, text: str, requirement_id: str) -> str:
        first_line = text.splitlines()[0].strip()
        first_sentence = first_line.split(".")[0].strip()
        if first_sentence:
            return first_sentence[:80]

        return f"Requirement {requirement_id}"

    def _build_description(self, text: str) -> str:
        return text[:500]


requirement_agent = RequirementAgent()
