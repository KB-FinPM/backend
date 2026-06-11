from datetime import date, datetime
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_item import ActionItemModel
from app.repositories.project_repository import ensure_project


class ActionItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_extracted_todos(
        self,
        *,
        project_id: str,
        todos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        await ensure_project(self.session, project_id=project_id)
        saved_items: list[dict[str, Any]] = []
        for todo in todos:
            action_item = ActionItemModel(
                action_item_id=self._new_todo_id(),
                project_id=project_id,
                title=str(todo.get("title") or "").strip(),
                description=todo.get("description"),
                owner=todo.get("assignee"),
                due_date=self._parse_iso_date(todo.get("due_date")),
                due_date_text=todo.get("due_date"),
                related_document=todo.get("related_document"),
                source_type=todo.get("source_type") or "MEETING_MINUTES",
                status=todo.get("status") or "TODO",
                source_document_id=todo.get("source_document_id"),
            )
            self.session.add(action_item)
            saved_items.append(self._to_todo_dict(action_item))

        await self.session.commit()
        return saved_items

    async def complete_matching_todo(
        self,
        *,
        project_id: str,
        title_query: str,
    ) -> dict[str, Any] | None:
        normalized_query = self._normalize_text(title_query)
        if not normalized_query:
            return None

        statement = select(ActionItemModel).where(
            ActionItemModel.project_id == project_id,
            ActionItemModel.status != "DONE",
        )
        result = await self.session.execute(statement)
        candidates = result.scalars().all()
        best_match: ActionItemModel | None = None
        best_score = 0
        for candidate in candidates:
            score = self._match_score(normalized_query, candidate.title)
            if score > best_score:
                best_match = candidate
                best_score = score

        if best_match is None or best_score < 2:
            return None

        best_match.status = "DONE"
        best_match.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(best_match)
        return self._to_todo_dict(best_match)

    async def complete_todo_by_id(
        self,
        *,
        project_id: str,
        todo_id: str,
    ) -> dict[str, Any] | None:
        if not todo_id:
            return None
        statement = select(ActionItemModel).where(
            ActionItemModel.project_id == project_id,
            ActionItemModel.action_item_id == todo_id,
            ActionItemModel.status != "DONE",
        )
        result = await self.session.execute(statement)
        item = result.scalar_one_or_none()
        if item is None:
            return None

        item.status = "DONE"
        item.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_todo_dict(item)

    async def list_project_todos(self, *, project_id: str) -> list[dict[str, Any]]:
        statement = (
            select(ActionItemModel)
            .where(ActionItemModel.project_id == project_id)
            .order_by(ActionItemModel.created_at.desc())
        )
        result = await self.session.execute(statement)
        return [self._to_todo_dict(item) for item in result.scalars().all()]

    def _to_todo_dict(self, item: ActionItemModel) -> dict[str, Any]:
        return {
            "project_id": item.project_id,
            "todo_id": item.action_item_id,
            "title": item.title,
            "description": item.description,
            "assignee": item.owner,
            "due_date": item.due_date_text
            or (item.due_date.isoformat() if item.due_date else None),
            "related_document": item.related_document,
            "source_type": item.source_type,
            "status": item.status,
            "source_document_id": item.source_document_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def _new_todo_id(self) -> str:
        return f"TODO-{uuid4().hex[:12].upper()}"

    def _parse_iso_date(self, value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    def _normalize_text(self, value: str) -> str:
        return "".join(str(value).lower().split())

    def _match_score(self, normalized_query: str, title: str) -> int:
        normalized_title = self._normalize_text(title)
        if not normalized_title:
            return 0
        if normalized_title in normalized_query or normalized_query in normalized_title:
            return len(normalized_title)

        query_text = str(normalized_query).replace("완료", " ")
        query_tokens = {token for token in query_text.split() if token}
        title_tokens = {token for token in title.lower().split() if token}
        if not query_tokens or not title_tokens:
            compact_title_tokens = [
                token for token in re.split(r"[^0-9A-Za-z가-힣]+", title.lower()) if token
            ]
            return sum(1 for token in compact_title_tokens if token in normalized_query)
        return len(query_tokens & title_tokens)
