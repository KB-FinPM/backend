from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.agents.input_agents.meeting_todo_extraction_agent.candidate_collector import (
    MeetingTodoCandidateCollector,
)
from app.agents.input_agents.meeting_todo_extraction_agent.context_retriever import (
    MeetingTodoContextRetriever,
)
from app.agents.input_agents.meeting_todo_extraction_agent.normalizer import (
    MeetingTodoNormalizer,
)
from app.agents.input_agents.meeting_todo_extraction_agent.prompts import (
    MEETING_TODO_JSON_RULES,
    MEETING_TODO_SYSTEM_PROMPT,
)
from app.agents.input_agents.meeting_todo_extraction_agent.schemas import (
    MeetingTodoExtractionResult,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


class MeetingTodoExtractionAgent:
    AGENT_NAME = "MeetingTodoExtractionAgent"

    def __init__(
        self,
        *,
        collector: MeetingTodoCandidateCollector | None = None,
        normalizer: MeetingTodoNormalizer | None = None,
        context_retriever: MeetingTodoContextRetriever | None = None,
        llm_service: Any | None = None,
        use_llm_by_default: bool = False,
    ) -> None:
        self.collector = collector or MeetingTodoCandidateCollector()
        self.normalizer = normalizer or MeetingTodoNormalizer()
        self.context_retriever = context_retriever or MeetingTodoContextRetriever()
        self.llm_service = llm_service
        self.use_llm_by_default = use_llm_by_default

    async def extract(
        self,
        *,
        project_id: str,
        meeting_notes: str,
        permission_scope: list[str] | None = None,
        source_document_ids: list[str] | None = None,
        source_chunk_ids: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, candidates = self.collector.collect(meeting_notes)
        query = "\n".join(candidate.source_sentence for candidate in candidates[:8])
        vector_context = await self.context_retriever.retrieve(
            project_id=project_id,
            permission_scope=permission_scope or [],
            query=query or meeting_notes[:1000],
            document_ids=source_document_ids,
        )

        should_use_llm = bool(
            self.llm_service is not None
            and (context or {}).get("use_llm", self.use_llm_by_default)
        )
        llm_result: MeetingTodoExtractionResult | None = None
        llm_error: str | None = None
        if should_use_llm:
            try:
                llm_result = await self._extract_with_llm(
                    document=document.model_dump(mode="json"),
                    candidates=[candidate.model_dump(mode="json") for candidate in candidates],
                    vector_context=vector_context,
                )
            except Exception as exc:
                llm_error = str(exc)
                logger.warning(
                    "[%s] LLM extraction fallback | project_id=%s | error=%s",
                    self.AGENT_NAME,
                    project_id,
                    exc,
                )

        if llm_result is not None and llm_result.todo_items:
            result = llm_result
            result.meeting_document = document
            result.candidates = candidates
            metadata = {
                **result.metadata,
                "extraction_strategy": "hybrid_rule_llm_rag",
                "fallback_used": False,
                "llm_used": True,
                "vector_context_used": bool(vector_context),
                "candidate_count": len(candidates),
            }
            result.metadata = metadata
            return result.model_dump(mode="json")

        todo_items, candidate_items = self.normalizer.normalize_candidates(
            document=document,
            candidates=candidates,
            source_document_id=(source_document_ids or [None])[0],
            source_chunk_ids=source_chunk_ids or [],
        )
        result = MeetingTodoExtractionResult(
            meeting_date=document.meeting_date,
            todo_items=todo_items,
            candidate_items=candidate_items,
            meeting_document=document,
            candidates=candidates,
            metadata={
                "extraction_strategy": "hybrid_rule_llm_rag",
                "fallback_used": True,
                "fallback_reason": llm_error or "llm_not_configured",
                "llm_used": False,
                "vector_context_used": bool(vector_context),
                "candidate_count": len(candidates),
                "todo_count": len(todo_items),
                "candidate_item_count": len(candidate_items),
            },
        )
        return result.model_dump(mode="json")

    async def _extract_with_llm(
        self,
        *,
        document: dict[str, Any],
        candidates: list[dict[str, Any]],
        vector_context: list[dict[str, Any]],
    ) -> MeetingTodoExtractionResult:
        prompt = json.dumps(
            {
                "meeting_document": document,
                "todo_candidates": candidates,
                "vector_context": vector_context[:4],
                "rules": MEETING_TODO_JSON_RULES,
            },
            ensure_ascii=False,
        )
        response_text = await self.llm_service.invoke(
            prompt,
            system=MEETING_TODO_SYSTEM_PROMPT,
            call_label="meeting_todo_extraction",
        )
        payload = self._parse_json_response(response_text)
        try:
            return MeetingTodoExtractionResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"invalid meeting todo extraction JSON: {exc}") from exc

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        text = str(response_text or "").strip()
        if not text:
            raise ValueError("empty LLM response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("LLM response must be a JSON object")
        return payload


meeting_todo_extraction_agent = MeetingTodoExtractionAgent()
