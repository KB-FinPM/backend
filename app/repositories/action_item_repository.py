from datetime import date, datetime
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.todo_description import normalize_todo_description
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
            due_date_text = self._normalize_due_date_text(
                todo.get("due_date"),
                default_today=True,
            )
            action_item = ActionItemModel(
                action_item_id=self._new_todo_id(),
                project_id=project_id,
                title=str(todo.get("title") or "").strip(),
                description=normalize_todo_description(todo) or None,
                owner=todo.get("assignee"),
                due_date=self._parse_iso_date(due_date_text),
                due_date_text=due_date_text,
                related_document=todo.get("related_document"),
                source_type=todo.get("source_type") or "MEETING_MINUTES",
                status=todo.get("status") or "TODO",
                source_document_id=todo.get("source_document_id"),
            )
            self.session.add(action_item)
            saved_items.append(self._to_todo_dict(action_item))

        await self.session.commit()
        return saved_items

    async def upsert_wbs_todos(
        self,
        *,
        project_id: str,
        todos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        await ensure_project(self.session, project_id=project_id)
        saved_items: list[dict[str, Any]] = []
        for todo in todos:
            title = str(todo.get("title") or "").strip()
            if not title:
                continue

            action_item_id = self._stable_wbs_todo_id(
                project_id=project_id,
                todo=todo,
            )
            statement = select(ActionItemModel).where(
                ActionItemModel.project_id == project_id,
                ActionItemModel.action_item_id == action_item_id,
            )
            result = await self.session.execute(statement)
            action_item = result.scalar_one_or_none()
            if action_item is None:
                action_item = ActionItemModel(
                    action_item_id=action_item_id,
                    project_id=project_id,
                    title=title,
                    source_type="WBS",
                    status=str(todo.get("status") or "TODO"),
                )
                self.session.add(action_item)

            action_item.title = title
            action_item.description = normalize_todo_description(
                {**todo, "title": title, "source_type": "WBS"},
            ) or None
            action_item.owner = todo.get("assignee")
            due_date = self._normalize_due_date_text(
                todo.get("due_date") or todo.get("planned_end_date"),
                default_today=True,
            )
            action_item.due_date = self._parse_iso_date(due_date)
            action_item.due_date_text = due_date
            action_item.related_document = (
                todo.get("related_document")
                or todo.get("related_artifact")
                or "WBS"
            )
            action_item.source_type = "WBS"
            action_item.source_document_id = todo.get("source_document_id")
            if action_item.status != "DONE":
                action_item.status = str(todo.get("status") or "TODO")
            action_item.updated_at = datetime.utcnow()

            saved_items.append(
                {
                    **todo,
                    **self._to_todo_dict(action_item),
                    "related_artifact": todo.get("related_artifact") or "WBS",
                    "planned_start_date": todo.get("planned_start_date"),
                    "planned_end_date": todo.get("planned_end_date"),
                    "assignee_display": todo.get("assignee_display"),
                    "status_display": (
                        "완료"
                        if action_item.status == "DONE"
                        else todo.get("status_display")
                    ),
                    "metadata": todo.get("metadata") or {},
                }
            )

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

        now = datetime.utcnow()
        best_match.status = "DONE"
        best_match.updated_at = now
        best_match.completed_at = best_match.completed_at or now
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
        )
        result = await self.session.execute(statement)
        item = result.scalar_one_or_none()
        if item is None:
            return None

        now = datetime.utcnow()
        if item.status != "DONE":
            item.status = "DONE"
            item.completed_at = item.completed_at or now
        elif item.completed_at is None:
            item.completed_at = now
        item.updated_at = now
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

    async def save_imported_todos(
        self,
        *,
        project_id: str,
        todos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        await ensure_project(self.session, project_id=project_id)
        saved_items: list[dict[str, Any]] = []
        for todo in todos:
            title = str(todo.get("title") or "").strip()
            if not title:
                continue
            due_date_text = self._normalize_due_date_text(
                todo.get("due_date") or todo.get("due_date_text"),
                default_today=False,
            )
            action_item = ActionItemModel(
                action_item_id=self._new_todo_id(),
                project_id=project_id,
                title=title,
                description=normalize_todo_description(
                    {**todo, "title": title},
                    source_type=todo.get("source_type"),
                )
                or None,
                owner=todo.get("assignee"),
                due_date=self._parse_iso_date(due_date_text),
                due_date_text=due_date_text,
                related_document=(
                    todo.get("source_document_name")
                    or todo.get("related_document")
                    or todo.get("related_artifact")
                ),
                source_type=todo.get("source_type") or "MEETING_NOTES",
                status=self._storage_status(todo.get("status")),
                source_document_id=todo.get("source_document_id"),
            )
            self.session.add(action_item)
            saved_items.append(self._to_todo_dict(action_item))

        await self.session.commit()
        return saved_items

    async def update_todo(
        self,
        *,
        project_id: str,
        todo_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        statement = select(ActionItemModel).where(
            ActionItemModel.project_id == project_id,
            ActionItemModel.action_item_id == todo_id,
        )
        result = await self.session.execute(statement)
        item = result.scalar_one_or_none()
        if item is None:
            return None

        if "title" in values and values["title"] is not None:
            item.title = str(values["title"] or "").strip() or item.title
        if "assignee" in values:
            item.owner = values.get("assignee")
        if "description" in values:
            item.description = values.get("description")
        if "due_date" in values:
            due_date_value = self._normalize_due_date_text(
                values.get("due_date"),
                default_today=False,
            )
            item.due_date = self._parse_iso_date(due_date_value)
            item.due_date_text = due_date_value
        if "status" in values and values["status"] is not None:
            status_value = self._storage_status(values.get("status"))
            item.status = status_value
            now = datetime.utcnow()
            if status_value == "DONE":
                item.completed_at = item.completed_at or now
            elif item.completed_at is not None:
                item.completed_at = None

        item.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_todo_dict(item)

    async def delete_todo(self, *, project_id: str, todo_id: str) -> bool:
        result = await self.session.execute(
            delete(ActionItemModel).where(
                ActionItemModel.project_id == project_id,
                ActionItemModel.action_item_id == todo_id,
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

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
            "completed_at": (
                item.completed_at.isoformat() if item.completed_at else None
            ),
        }

    def _new_todo_id(self) -> str:
        return f"TODO-{uuid4().hex[:12].upper()}"

    def _stable_wbs_todo_id(
        self,
        *,
        project_id: str,
        todo: dict[str, Any],
    ) -> str:
        identity = "|".join(
            str(value or "")
            for value in [
                project_id,
                todo.get("source_document_id"),
                todo.get("source_document_name"),
                todo.get("wbs_id"),
                todo.get("row_number"),
                todo.get("todo_id"),
                todo.get("title"),
            ]
        )
        return f"TODO-WBS-{uuid5(NAMESPACE_URL, identity).hex[:12].upper()}"

    def _normalize_due_date_text(
        self,
        value: Any,
        *,
        default_today: bool = False,
    ) -> str | None:
        parsed_date = self._parse_iso_date(value)
        if parsed_date is not None:
            return parsed_date.isoformat()
        if default_today:
            return date.today().isoformat()
        return None

    def _parse_iso_date(self, value: Any) -> date | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        if text.upper() in {"NONE", "NULL", "TBD", "N/A", "NA", "미정"}:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

        year_first = re.search(
            r"(?P<year>\d{4})\s*(?:[./-]|년)\s*"
            r"(?P<month>\d{1,2})\s*(?:[./-]|월)\s*"
            r"(?P<day>\d{1,2})",
            text,
        )
        if year_first:
            return self._safe_date(
                int(year_first.group("year")),
                int(year_first.group("month")),
                int(year_first.group("day")),
            )

        yearless = re.search(
            r"(?<!\d)(?P<month>\d{1,2})\s*(?:[./-]|월)\s*"
            r"(?P<day>\d{1,2})\s*(?:일)?(?!\d)",
            text,
        )
        if yearless:
            today = date.today()
            return self._safe_date(
                today.year,
                int(yearless.group("month")),
                int(yearless.group("day")),
            )
        return None

    def _safe_date(self, year: int, month: int, day: int) -> date | None:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _storage_status(self, value: Any) -> str:
        normalized = str(value or "").strip().upper()
        aliases = {
            "NOT_STARTED": "NOT_STARTED",
            "TODO": "NOT_STARTED",
            "PENDING": "NOT_STARTED",
            "OPEN": "NOT_STARTED",
            "NEEDS_CONFIRMATION": "NOT_STARTED",
            "IN_PROGRESS": "IN_PROGRESS",
            "DOING": "IN_PROGRESS",
            "DONE": "DONE",
            "COMPLETED": "DONE",
            "COMPLETE": "DONE",
            "CLOSED": "DONE",
        }
        return aliases.get(normalized, "NOT_STARTED")

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").lower()
        for token in (
            "완료했습니다",
            "완료했어",
            "완료",
            "끝났어",
            "끝냈어",
            "끝",
            "처리했어",
            "처리",
            "했습니다",
            "했어",
            "done",
            "complete",
            "todo",
            "업무",
        ):
            text = text.replace(token, " ")
        compact = re.sub(r"[^0-9a-z가-힣]+", "", text)
        for token in ("그리고", "및", "and", "와", "과"):
            compact = compact.replace(token, "")
        return compact

    def _match_score(self, normalized_query: str, title: str) -> int:
        normalized_title = self._normalize_text(title)
        if not normalized_title:
            return 0
        if normalized_title in normalized_query or normalized_query in normalized_title:
            return len(normalized_title)

        query_text = self._normalize_text(normalized_query)
        query_tokens = {token for token in re.split(r"[^0-9a-z가-힣]+", query_text) if token}
        title_tokens = {token for token in title.lower().split() if token}
        if not query_tokens or not title_tokens:
            compact_title_tokens = [
                token for token in re.split(r"[^0-9A-Za-z가-힣]+", title.lower()) if token
            ]
            return sum(1 for token in compact_title_tokens if token in normalized_query)
        return len(query_tokens & title_tokens)
