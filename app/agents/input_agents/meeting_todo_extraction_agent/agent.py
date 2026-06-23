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
from app.core.todo_description import (
    build_meeting_todo_description,
    is_generic_todo_description,
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
        payload = self._normalize_llm_payload(payload, document=document)
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

    def _normalize_llm_payload(
        self,
        payload: dict[str, Any],
        *,
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(payload)
        if "todo_items" not in normalized and isinstance(normalized.get("items"), list):
            normalized["todo_items"] = normalized["items"]
        if "candidate_items" not in normalized and isinstance(
            normalized.get("excluded_candidates"), list
        ):
            normalized["candidate_items"] = [
                {
                    "title": str(item.get("title") or item.get("text") or "")[:80],
                    "classification": item.get("classification")
                    if item.get("classification")
                    in {
                        "candidate",
                        "issue_or_requirement",
                        "requirement_candidate",
                        "issue",
                        "not_todo",
                    }
                    else "issue_or_requirement",
                    "reason": item.get("reason") or "할일로 확정하지 않았습니다.",
                    "source_sentence": item.get("source_sentence")
                    or item.get("text")
                    or "",
                }
                for item in normalized["excluded_candidates"]
                if isinstance(item, dict)
            ]

        todo_items = normalized.get("todo_items")
        if isinstance(todo_items, list):
            normalized_items: list[dict[str, Any]] = []
            for item in todo_items:
                if not isinstance(item, dict):
                    continue
                title = self._compact_llm_title(item.get("title"))
                if not title:
                    continue
                item["title"] = title
                status = str(item.get("status") or "").strip().upper()
                if status in {"진행전", "NOT_STARTED", "OPEN", "PENDING"}:
                    item["status"] = "TODO"
                elif status not in {"TODO", "NEEDS_CONFIRMATION"}:
                    item["status"] = "NEEDS_CONFIRMATION"
                item["confidence"] = self._normalize_confidence(item.get("confidence"))
                item.setdefault("source_type", "MEETING_NOTE")
                item.setdefault("classification", "todo")
                item.setdefault("related_document", "")
                item["due_date"] = self._normalize_empty_string(item.get("due_date"))
                item["due_date_text"] = (
                    str(item.get("due_date_text") or "").strip()
                    or ("미정" if item.get("due_date") in (None, "") else str(item.get("due_date")))
                )
                item["needs_confirmation"] = self._normalize_confirmation_list(
                    item.get("needs_confirmation"),
                    due_date=item.get("due_date"),
                    due_date_text=item.get("due_date_text"),
                )
                item["description"] = self._normalize_llm_description(item)
                item["source_sentence"] = str(item.get("source_sentence") or "").strip()
                if not item["source_sentence"]:
                    item["source_sentence"] = str(item.get("description") or title)
                normalized_items.append(item)
            normalized["todo_items"] = normalized_items
        if document:
            normalized.setdefault("meeting_date", document.get("meeting_date"))
        return normalized

    def _compact_llm_title(self, value: Any) -> str:
        title = re.sub(r"\s+", " ", str(value or "")).strip(" -:：,，.")
        if len(title) <= 60:
            return title
        for delimiter in ("에 대해", " 관련", " 기준"):
            if delimiter in title[:80]:
                title = title.split(delimiter, 1)[0].strip()
                break
        return title[:60].rstrip(" -:：,，.")

    def _normalize_confidence(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        text = str(value or "").strip().lower()
        return {"high": 0.9, "medium": 0.7, "low": 0.5}.get(text, 0.6)

    def _normalize_empty_string(self, value: Any) -> Any | None:
        if value in ("", "미정", "null", "None"):
            return None
        return value

    def _normalize_confirmation_list(
        self,
        value: Any,
        *,
        due_date: Any,
        due_date_text: Any,
    ) -> list[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        elif value:
            items = [str(value).strip()]
        else:
            items = []
        if not due_date and str(due_date_text or "").strip() in {"", "미정"} and "기한" not in items:
            items.append("기한")
        return items

    def _normalize_llm_description(self, item: dict[str, Any]) -> str:
        description = str(item.get("description") or "").strip()
        if description and not is_generic_todo_description(description):
            return description
        return build_meeting_todo_description(
            title=item.get("title"),
            source_sentence=item.get("source_sentence"),
            description=description,
            assignee=item.get("assignee"),
            due_date_text=item.get("due_date_text") or item.get("due_date"),
        )


meeting_todo_extraction_agent = MeetingTodoExtractionAgent()
