# EN: Business service for lightweight schedule/todo management.

from datetime import date, datetime
import re
from typing import Any

from app.orchestrator.schedule_orchestrator import (
    ScheduleOrchestrator,
    schedule_orchestrator,
)
from app.core.todo_description import normalize_todo_description
from app.repositories.action_item_repository import ActionItemRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse
from app.schemas.todo import (
    TodoImportCommitResponse,
    TodoImportPreviewResponse,
    TodoItem,
    TodoListResponse,
)


class ScheduleService:
    """Coordinates schedule-management use cases without exposing agents to routers."""

    def __init__(
        self,
        orchestrator: ScheduleOrchestrator = schedule_orchestrator,
        action_item_repository: ActionItemRepository | None = None,
        document_repository: DocumentRepository | None = None,
        artifact_repository: ArtifactRepository | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.action_item_repository = action_item_repository
        self.document_repository = document_repository
        self.artifact_repository = artifact_repository

    async def extract_todos(
        self,
        request: ScheduleTodoRequest,
        *,
        structured_context: dict[str, Any] | None = None,
    ) -> ScheduleTodoResponse:
        request = await self._request_with_source_document_notes(request)
        response = await self.orchestrator.extract_todos(
            request,
            structured_context=structured_context,
        )
        if (
            response.success
            and self.action_item_repository is not None
            and isinstance(response.result, dict)
        ):
            todos = response.result.get("todos") or []
            if todos:
                saved_todos = await self.action_item_repository.save_extracted_todos(
                    project_id=request.project_id,
                    todos=todos,
                )
                response.result = {
                    **response.result,
                    "todos": saved_todos,
                    "metadata": {
                        **(response.result.get("metadata") or {}),
                        "saved": True,
                        "todo_count": len(saved_todos),
                    },
                }
        return response

    async def complete_todo(
        self,
        *,
        project_id: str,
        title_query: str,
    ) -> ScheduleTodoResponse:
        if self.action_item_repository is None:
            return ScheduleTodoResponse(
                success=False,
                project_id=project_id,
                message="todo storage is not available",
                result={},
            )

        todos = await self.action_item_repository.list_project_todos(
            project_id=project_id,
        )
        match_response = await self.orchestrator.run_schedule_action(
            project_id=project_id,
            action="COMPLETE_TODO",
            context={
                "target_text": title_query,
                "todos": todos,
            },
        )
        if not match_response.success:
            return match_response

        result = match_response.result if isinstance(match_response.result, dict) else {}
        if result.get("status") != "READY_TO_UPDATE":
            return ScheduleTodoResponse(
                project_id=project_id,
                message="todo match requires follow-up",
                result=result,
            )

        matched_todo = result.get("matched_todo") or {}
        return await self.complete_todo_by_id(
            project_id=project_id,
            todo_id=str(matched_todo.get("todo_id") or ""),
        )

    async def complete_todo_by_id(
        self,
        *,
        project_id: str,
        todo_id: str,
    ) -> ScheduleTodoResponse:
        if self.action_item_repository is None:
            return ScheduleTodoResponse(
                success=False,
                project_id=project_id,
                message="todo storage is not available",
                result={
                    "action": "COMPLETE_TODO",
                    "status": "STORAGE_UNAVAILABLE",
                    "message_key": "TODO_STORAGE_UNAVAILABLE",
                },
            )

        completed_todo = await self.action_item_repository.complete_todo_by_id(
            project_id=project_id,
            todo_id=todo_id,
        )
        if completed_todo is None:
            return ScheduleTodoResponse(
                success=False,
                project_id=project_id,
                message="matching todo not found",
                result={
                    "action": "COMPLETE_TODO",
                    "status": "NOT_FOUND",
                    "message_key": "TODO_NOT_FOUND",
                },
            )

        remaining_todos = [
            todo
            for todo in await self.action_item_repository.list_project_todos(
                project_id=project_id,
            )
            if str(todo.get("status") or "").upper() != "DONE"
        ]

        return ScheduleTodoResponse(
            project_id=project_id,
            message="todo completed",
            result={
                "artifact_type": "SCHEDULE_TODO_LIST",
                "action": "COMPLETE_TODO",
                "status": "SUCCESS",
                "matched_todo": {
                    "todo_id": completed_todo.get("todo_id"),
                    "title": completed_todo.get("title"),
                    "next_status": "DONE",
                },
                "todos": [completed_todo, *remaining_todos],
                "remaining_todos": remaining_todos,
                "metadata": {
                    "event": "TODO_COMPLETED",
                    "remaining_todo_count": len(remaining_todos),
                },
            },
        )

    async def list_todos(
        self,
        *,
        project_id: str,
        status_filter: str | None = None,
        source_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> TodoListResponse:
        todos = await self._stored_todos(project_id=project_id)
        document_names = await self._document_name_map(project_id=project_id)
        normalized_source_type = (
            self._normalize_source_type(source_type) if source_type else None
        )
        items = [
            self._todo_item(todo, document_names=document_names)
            for todo in todos
            if self._matches_todo_filters(
                todo,
                status_filter=status_filter,
                source_type=normalized_source_type,
                date_from=date_from,
                date_to=date_to,
            )
        ]
        return TodoListResponse(items=items)

    async def update_todo(
        self,
        *,
        project_id: str,
        todo_id: str,
        values: dict[str, Any],
    ) -> TodoItem | None:
        if self.action_item_repository is None:
            return None
        updated = await self.action_item_repository.update_todo(
            project_id=project_id,
            todo_id=todo_id,
            values=values,
        )
        if updated is None:
            return None
        document_names = await self._document_name_map(project_id=project_id)
        return self._todo_item(updated, document_names=document_names)

    async def delete_todo(self, *, project_id: str, todo_id: str) -> bool:
        if self.action_item_repository is None:
            return False
        return await self.action_item_repository.delete_todo(
            project_id=project_id,
            todo_id=todo_id,
        )

    async def preview_todo_import(
        self,
        *,
        project_id: str,
        document_id: str,
        document_type: str,
    ) -> TodoImportPreviewResponse:
        if self.document_repository is None:
            return TodoImportPreviewResponse(
                metadata={"error": "DOCUMENT_STORAGE_UNAVAILABLE"}
            )
        document = await self.document_repository.get_document(
            project_id=project_id,
            document_id=document_id,
        )
        if document is None:
            return TodoImportPreviewResponse(
                metadata={"error": "DOCUMENT_NOT_FOUND", "document_id": document_id}
            )

        source_type = self._normalize_source_type(document_type)
        candidates = await self._preview_candidates_from_document(
            project_id=project_id,
            document_id=document_id,
            document_name=document.file_name,
            source_type=source_type,
        )
        existing = await self._stored_todos(project_id=project_id)
        document_names = await self._document_name_map(project_id=project_id)
        new_items: list[TodoItem] = []
        duplicate_items = []
        for candidate in candidates:
            duplicate = self._find_duplicate(
                candidate.model_dump(mode="json"),
                existing,
                document_names=document_names,
            )
            if duplicate is None:
                new_items.append(candidate)
                continue
            matched, duplicate_level = duplicate
            duplicate_items.append(
                {
                    "candidate": candidate,
                    "matched_existing": self._todo_item(
                        matched,
                        document_names=document_names,
                    ),
                    "duplicate_level": duplicate_level,
                }
            )

        return TodoImportPreviewResponse(
            new_items=new_items,
            duplicate_items=duplicate_items,
            metadata={
                "document_id": document_id,
                "document_type": source_type,
                "candidate_count": len(candidates),
                "new_count": len(new_items),
                "duplicate_count": len(duplicate_items),
            },
        )

    async def commit_todo_import(
        self,
        *,
        project_id: str,
        items: list[dict[str, Any]],
        duplicate_decisions: list[dict[str, str]] | None = None,
    ) -> TodoImportCommitResponse:
        if self.action_item_repository is None:
            return TodoImportCommitResponse(
                metadata={"error": "TODO_STORAGE_UNAVAILABLE"}
            )
        decisions = {
            str(item.get("client_import_id") or item.get("todo_id") or ""): str(
                item.get("decision") or ""
            ).upper()
            for item in duplicate_decisions or []
        }
        selected_items = []
        skipped_items = []
        for item in items:
            item_id = str(item.get("client_import_id") or item.get("todo_id") or "")
            if decisions.get(item_id) == "SKIP":
                skipped_items.append(item)
                continue
            selected_items.append(item)

        saved = await self.action_item_repository.save_imported_todos(
            project_id=project_id,
            todos=selected_items,
        )
        document_names = await self._document_name_map(project_id=project_id)
        return TodoImportCommitResponse(
            saved_items=[
                self._todo_item(todo, document_names=document_names) for todo in saved
            ],
            skipped_items=[
                self._todo_item(item, document_names=document_names)
                for item in skipped_items
            ],
            metadata={
                "saved_count": len(saved),
                "skipped_count": len(skipped_items),
            },
        )

    async def _request_with_source_document_notes(
        self,
        request: ScheduleTodoRequest,
    ) -> ScheduleTodoRequest:
        if self.document_repository is None or not request.source_document_ids:
            return request

        document_text = await self._load_source_document_text(
            project_id=request.project_id,
            document_ids=request.source_document_ids,
        )
        if not document_text:
            return request

        meeting_notes = "\n".join(
            part
            for part in [document_text, request.meeting_notes]
            if str(part or "").strip()
        )
        return request.model_copy(update={"meeting_notes": meeting_notes})

    async def _load_source_document_text(
        self,
        *,
        project_id: str,
        document_ids: list[str],
    ) -> str:
        lines: list[str] = []
        for document_id in document_ids:
            chunks = await self.document_repository.list_chunks_by_document(
                project_id=project_id,
                document_id=document_id,
            )
            for chunk in chunks:
                text = str(getattr(chunk, "text", "") or "").strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)

    async def _stored_todos(self, *, project_id: str) -> list[dict[str, Any]]:
        if self.action_item_repository is None:
            return []
        return await self.action_item_repository.list_project_todos(
            project_id=project_id,
        )

    async def _document_name_map(self, *, project_id: str) -> dict[str, str]:
        if self.document_repository is None:
            return {}
        documents = await self.document_repository.list_documents_by_project(
            project_id=project_id,
        )
        return {document.document_id: document.file_name for document in documents}

    def _todo_item(
        self,
        todo: dict[str, Any],
        *,
        document_names: dict[str, str] | None = None,
    ) -> TodoItem:
        source_document_id = todo.get("source_document_id")
        due_date = self._normalize_due_date_text(
            todo.get("due_date") or todo.get("due_date_text"),
            default_today=True,
        )
        start_date = self._normalize_due_date_text(
            todo.get("start_date") or todo.get("planned_start_date"),
            default_today=False,
        )
        end_date = self._normalize_due_date_text(
            todo.get("end_date") or todo.get("planned_end_date"),
            default_today=False,
        )
        if not start_date and not end_date and due_date:
            start_date = due_date
            end_date = due_date
        elif start_date and not end_date:
            end_date = start_date
        elif end_date and not start_date:
            start_date = end_date
        if start_date and end_date and end_date < start_date:
            start_date, end_date = end_date, start_date
        due_date = end_date or due_date
        source_document_name = (
            todo.get("source_document_name")
            or (document_names or {}).get(str(source_document_id or ""))
            or todo.get("related_document")
        )
        source_sentence = todo.get("source_sentence")
        metadata = todo.get("metadata") if isinstance(todo.get("metadata"), dict) else {}
        source_sentence = source_sentence or metadata.get("source_sentence")
        description = normalize_todo_description(
            {
                **todo,
                "source_sentence": source_sentence,
            },
            source_type=todo.get("source_type"),
        )
        return TodoItem(
            todo_id=str(
                todo.get("client_import_id")
                or todo.get("todo_id")
                or todo.get("action_item_id")
                or ""
            ),
            title=str(todo.get("title") or "").strip(),
            assignee=todo.get("assignee") or todo.get("owner"),
            start_date=start_date,
            end_date=end_date,
            due_date=due_date,
            due_date_text=due_date,
            status=self._ui_status(todo.get("status")),
            source_type=self._normalize_source_type(todo.get("source_type")),
            source_document_id=source_document_id,
            source_document_name=source_document_name,
            related_document=todo.get("related_document") or source_document_name,
            description=description,
            source_sentence=source_sentence or description,
            created_at=todo.get("created_at"),
            updated_at=todo.get("updated_at"),
        )

    def _matches_todo_filters(
        self,
        todo: dict[str, Any],
        *,
        status_filter: str | None,
        source_type: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        if status_filter and self._ui_status(todo.get("status")) != status_filter:
            return False
        if source_type and self._normalize_source_type(todo.get("source_type")) != source_type:
            return False
        start_date = str(todo.get("start_date") or todo.get("due_date") or "")[:10]
        end_date = str(todo.get("end_date") or todo.get("due_date") or start_date)[:10]
        if date_from and (not end_date or end_date < date_from):
            return False
        if date_to and (not start_date or start_date > date_to):
            return False
        return True

    async def _preview_candidates_from_document(
        self,
        *,
        project_id: str,
        document_id: str,
        document_name: str,
        source_type: str,
    ) -> list[TodoItem]:
        if source_type == "WBS":
            return await self._preview_wbs_candidates(
                project_id=project_id,
                document_id=document_id,
                document_name=document_name,
            )
        return await self._preview_meeting_candidates(
            project_id=project_id,
            document_id=document_id,
            document_name=document_name,
        )

    async def _preview_meeting_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
        document_name: str,
    ) -> list[TodoItem]:
        meeting_notes = await self._load_source_document_text(
            project_id=project_id,
            document_ids=[document_id],
        )
        if not meeting_notes.strip():
            return []
        response = await self.orchestrator.extract_todos(
            ScheduleTodoRequest(
                project_id=project_id,
                meeting_notes=meeting_notes,
                source_document_ids=[document_id],
            ),
            structured_context={
                "source": "todo_manager_import",
                "schedule_action": "EXTRACT_TODOS_FROM_MEETING",
            },
        )
        result = response.result if isinstance(response.result, dict) else {}
        return self._candidate_items(
            result.get("todos") or [],
            source_type="MEETING_NOTES",
            document_id=document_id,
            document_name=document_name,
        )

    async def _preview_wbs_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
        document_name: str,
    ) -> list[TodoItem]:
        wbs_context = await self._load_wbs_context_for_document(
            project_id=project_id,
            document_id=document_id,
            document_name=document_name,
        )
        response = await self.orchestrator.run_schedule_action(
            project_id=project_id,
            action="SHOW_ALL_TODOS",
            context={
                "wbs_context": wbs_context,
                "normalized_input": {
                    "entities": {
                        "source": "WBS",
                        "status_filter": "ALL",
                        "time_filter": "ALL_PERIOD",
                    }
                },
            },
        )
        result = response.result if isinstance(response.result, dict) else {}
        return self._candidate_items(
            result.get("todos") or [],
            source_type="WBS",
            document_id=document_id,
            document_name=document_name,
        )

    async def _load_wbs_context_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
        document_name: str,
    ) -> dict[str, Any]:
        if self.document_repository is None:
            return {"source_document_names": [document_name], "rows": [], "tasks": []}
        rows: list[dict[str, Any]] = []
        chunks = await self.document_repository.list_chunks_by_document(
            project_id=project_id,
            document_id=document_id,
        )
        for chunk in chunks:
            metadata = chunk.chunk_metadata or {}
            row = metadata.get("wbs_row")
            if isinstance(row, dict):
                rows.append(
                    {
                        **row,
                        "source_document_id": document_id,
                        "source_document_name": document_name,
                    }
                )
            metadata_context = metadata.get("wbs_context")
            if isinstance(metadata_context, dict):
                for metadata_row in metadata_context.get("rows") or []:
                    if isinstance(metadata_row, dict):
                        rows.append(
                            {
                                **metadata_row,
                                "source_document_id": document_id,
                                "source_document_name": document_name,
                            }
                        )
        return {
            "source_document_names": [document_name],
            "rows": self._dedupe_wbs_rows(rows),
            "tasks": [],
        }

    def _candidate_items(
        self,
        todos: list[dict[str, Any]],
        *,
        source_type: str,
        document_id: str,
        document_name: str,
    ) -> list[TodoItem]:
        items: list[TodoItem] = []
        for index, todo in enumerate(todos):
            if not isinstance(todo, dict):
                continue
            normalized = {
                **todo,
                "client_import_id": f"IMPORT-{index + 1:03d}",
                "source_type": source_type,
                "source_document_id": document_id,
                "source_document_name": document_name,
                "related_document": document_name,
            }
            item = self._todo_item(normalized, document_names={document_id: document_name})
            if item.title:
                items.append(item)
        return items

    def _find_duplicate(
        self,
        candidate: dict[str, Any],
        existing: list[dict[str, Any]],
        *,
        document_names: dict[str, str],
    ) -> tuple[dict[str, Any], str] | None:
        best_match = None
        best_score = 0.0
        for item in existing:
            score = self._duplicate_score(candidate, item)
            if score > best_score:
                best_match = item
                best_score = score
        if best_match is None or best_score < 0.55:
            return None
        level = "DUPLICATE_HIGH" if best_score >= 0.82 else "DUPLICATE_POSSIBLE"
        return best_match, level

    def _duplicate_score(self, candidate: dict[str, Any], existing: dict[str, Any]) -> float:
        title_score = self._text_similarity(candidate.get("title"), existing.get("title"))
        description_score = self._text_similarity(
            candidate.get("description"),
            existing.get("description"),
        )
        assignee_match = self._field_match(
            candidate.get("assignee"),
            existing.get("assignee") or existing.get("owner"),
        )
        due_match = self._field_match(candidate.get("due_date"), existing.get("due_date"))
        score = max(title_score, (title_score * 0.62) + (description_score * 0.22))
        if assignee_match:
            score += 0.08
        if due_match:
            score += 0.08
        return min(score, 1.0)

    def _text_similarity(self, left: Any, right: Any) -> float:
        left_tokens = self._text_tokens(left)
        right_tokens = self._text_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        if left_tokens == right_tokens:
            return 0.76
        overlap = len(left_tokens & right_tokens)
        return overlap / max(len(left_tokens | right_tokens), 1)

    def _text_tokens(self, value: Any) -> set[str]:
        normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", str(value or "").lower())
        return {token for token in normalized.split() if len(token) >= 2}

    def _field_match(self, left: Any, right: Any) -> bool:
        left_text = str(left or "").strip()
        right_text = str(right or "").strip()
        return bool(left_text and right_text and left_text == right_text)

    def _normalize_due_date_text(
        self,
        value: Any,
        *,
        default_today: bool = False,
    ) -> str | None:
        parsed_date = self._parse_due_date(value)
        if parsed_date is not None:
            return parsed_date.isoformat()
        if default_today:
            return date.today().isoformat()
        return None

    def _parse_due_date(self, value: Any) -> date | None:
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

    def _ui_status(self, value: Any) -> str:
        status = str(value or "").strip().upper()
        if status in {"DONE", "COMPLETED", "COMPLETE", "CLOSED"}:
            return "DONE"
        if status in {"IN_PROGRESS", "DOING"}:
            return "IN_PROGRESS"
        return "NOT_STARTED"

    def _normalize_source_type(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        if "WBS" in text:
            return "WBS"
        if "MANUAL" in text or "DIRECT" in text:
            return "MANUAL"
        return "MEETING_NOTES"

    async def run_query(
        self,
        *,
        project_id: str,
        schedule_action: str,
        context: dict[str, Any] | None = None,
        permission_scope: list[str] | None = None,
        persist_wbs_todos: bool = True,
    ) -> ScheduleTodoResponse:
        todos: list[dict[str, Any]] = []
        if self.action_item_repository is not None:
            todos = await self.action_item_repository.list_project_todos(
                project_id=project_id,
            )

        assembled_context = dict(context or {})
        if not self._has_wbs_rows(assembled_context):
            wbs_context = await self._load_wbs_context(project_id=project_id)
            if wbs_context.get("rows") or wbs_context.get("tasks"):
                assembled_context["wbs_context"] = wbs_context

        if self._has_wbs_rows(assembled_context):
            todos = [
                todo
                for todo in todos
                if str(todo.get("source_type") or "").upper() != "WBS"
            ]

        assembled_context = {
            **assembled_context,
            "todos": todos,
            "permission_scope": permission_scope or ["project:read"],
        }
        response = await self.orchestrator.run_schedule_action(
            project_id=project_id,
            action=schedule_action,
            context=assembled_context,
        )
        if (
            persist_wbs_todos
            and response.success
            and self.action_item_repository is not None
            and isinstance(response.result, dict)
        ):
            response.result = await self._persist_wbs_todos(
                project_id=project_id,
                result=response.result,
            )
        return response

    def _has_wbs_rows(self, context: dict[str, Any]) -> bool:
        wbs_context = context.get("wbs_context")
        if isinstance(wbs_context, dict) and (
            wbs_context.get("rows") or wbs_context.get("tasks")
        ):
            return True
        return bool(context.get("wbs_tasks") or context.get("wbs_items"))

    async def _load_wbs_context(self, *, project_id: str) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        tasks: list[dict[str, Any]] = []
        source_documents: list[str] = []

        if self.artifact_repository is not None:
            artifacts = await self.artifact_repository.list_artifacts_by_project(
                project_id=project_id,
            )
            for artifact in artifacts:
                if str(artifact.artifact_type or "").upper() != ArtifactType.WBS.value:
                    continue
                result_json = artifact.result_json or {}
                artifact_tasks = self._extract_generated_wbs_tasks(result_json)
                if isinstance(artifact_tasks, list):
                    source_name = artifact.name or artifact.artifact_id
                    source_documents.append(source_name)
                    tasks.extend(
                        {
                            **task,
                            "source_artifact_id": artifact.artifact_id,
                            "source_artifact_type": ArtifactType.WBS.value,
                            "artifact_type": ArtifactType.WBS.value,
                            "document_type": DocumentType.WBS.value,
                            "source_type": "generated",
                            "source_document_name": source_name,
                        }
                        for task in artifact_tasks
                        if isinstance(task, dict)
                    )
            if tasks:
                return {
                    "source_document_names": source_documents,
                    "rows": [],
                    "tasks": self._dedupe_wbs_rows(tasks),
                }

        if self.document_repository is not None:
            documents = await self.document_repository.list_documents_by_project(
                project_id=project_id,
            )
            for document in documents:
                if str(document.document_type or "").upper() != DocumentType.WBS.value:
                    continue
                source_documents.append(document.file_name)
                chunks = await self.document_repository.list_chunks_by_document(
                    project_id=project_id,
                    document_id=document.document_id,
                )
                for chunk in chunks:
                    metadata = chunk.chunk_metadata or {}
                    row = metadata.get("wbs_row")
                    if isinstance(row, dict):
                        rows.append(
                            {
                                **row,
                                "source_document_id": document.document_id,
                                "source_document_name": row.get(
                                    "source_document_name"
                                )
                                or document.file_name,
                            }
                        )
                    metadata_context = metadata.get("wbs_context")
                    if isinstance(metadata_context, dict):
                        for metadata_row in metadata_context.get("rows") or []:
                            if isinstance(metadata_row, dict):
                                rows.append(
                                    {
                                        **metadata_row,
                                        "source_document_id": document.document_id,
                                        "source_document_name": metadata_row.get(
                                            "source_document_name"
                                        )
                                        or document.file_name,
                                    }
                                )

        return {
            "source_document_names": source_documents,
            "rows": self._dedupe_wbs_rows(rows),
            "tasks": self._dedupe_wbs_rows(tasks),
        }

    def _extract_generated_wbs_tasks(self, result_json: dict[str, Any]) -> list[dict[str, Any]]:
        candidate_lists = [
            result_json.get("tasks"),
            result_json.get("rows"),
            result_json.get("wbs_items"),
            result_json.get("items"),
            result_json.get("work_items"),
        ]
        for nested_key in ("wbs", "generated", "result", "data"):
            nested = result_json.get(nested_key)
            if not isinstance(nested, dict):
                continue
            candidate_lists.extend(
                [
                    nested.get("tasks"),
                    nested.get("rows"),
                    nested.get("wbs_items"),
                    nested.get("items"),
                    nested.get("work_items"),
                ]
            )

        for candidate in candidate_lists:
            if isinstance(candidate, list) and any(
                isinstance(item, dict) for item in candidate
            ):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    async def _persist_wbs_todos(
        self,
        *,
        project_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        todos = result.get("todos") or []
        if not isinstance(todos, list):
            return result

        wbs_todos = [
            todo
            for todo in todos
            if isinstance(todo, dict)
            and str(todo.get("source_type") or "").upper() == "WBS"
        ]
        if not wbs_todos:
            return result
        if not hasattr(self.action_item_repository, "upsert_wbs_todos"):
            return result

        saved_wbs_todos = await self.action_item_repository.upsert_wbs_todos(
            project_id=project_id,
            todos=wbs_todos,
        )
        saved_iter = iter(saved_wbs_todos)
        merged_todos: list[dict[str, Any]] = []
        for todo in todos:
            if (
                isinstance(todo, dict)
                and str(todo.get("source_type") or "").upper() == "WBS"
            ):
                merged_todos.append(next(saved_iter, todo))
            else:
                merged_todos.append(todo)

        return {
            **result,
            "todos": merged_todos,
            "metadata": {
                **(result.get("metadata") or {}),
                "wbs_todos_saved": True,
                "wbs_todo_count": len(saved_wbs_todos),
            },
        }

    def _dedupe_wbs_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (
                str(row.get("row_number") or row.get("rowNumber") or ""),
                str(row.get("wbs_id") or row.get("id") or row.get("ID") or ""),
                str(row.get("title") or row.get("name") or row.get("WBS명") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped
