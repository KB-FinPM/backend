# EN: Business service for lightweight schedule/todo management.

from typing import Any

from app.orchestrator.schedule_orchestrator import (
    ScheduleOrchestrator,
    schedule_orchestrator,
)
from app.repositories.action_item_repository import ActionItemRepository
from app.repositories.artifact_repository import ArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import ArtifactType, DocumentType
from app.schemas.request import ScheduleTodoRequest
from app.schemas.response import ScheduleTodoResponse


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

    async def run_query(
        self,
        *,
        project_id: str,
        schedule_action: str,
        context: dict[str, Any] | None = None,
        permission_scope: list[str] | None = None,
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
            response.success
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
