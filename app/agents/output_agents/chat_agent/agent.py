from typing import Any

from app.schemas.chat import ChatActionType, ChatCommandType, ChatState
from app.schemas.io_agent import (
    OutputAgentRequest,
    OutputAgentResponse,
    OutputResponseType,
)


class ChatOutputAgent:
    AGENT_NAME = "ChatOutputAgent"

    async def render(self, request: OutputAgentRequest) -> OutputAgentResponse:
        if request.response_type != OutputResponseType.CHAT_RESPONSE:
            return OutputAgentResponse(
                success=False,
                agent_name=self.AGENT_NAME,
                message="unsupported response type",
                error="unsupported response type",
            )

        display_payload = self.build_display_payload(request.result_json)
        return OutputAgentResponse(
            agent_name=self.AGENT_NAME,
            message=display_payload["message"],
            display_payload=display_payload,
            download_files=display_payload.get("download_files", []),
            artifact_refs=display_payload.get("artifact_refs", []),
        )

    def build_display_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        event = result_json.get("event")
        if event == "CONFIRMATION_REQUIRED":
            return self._confirmation_payload(result_json)
        if event == "ACTION_COMPLETED":
            return self._completed_payload(result_json)
        if event == "TODO_COMPLETED":
            return self._todo_completed_payload(result_json)
        if event == "ACTION_FAILED":
            return self._failed_payload(result_json)
        if event == "ACTION_CANCELLED":
            return {
                "state": ChatState.IDLE.value,
                "message": "요청을 취소했습니다.",
                "suggested_actions": [],
            }
        if event == "REQUIRED_INFO":
            return self._required_info_payload(result_json)
        if event == "GENERAL_QA":
            return self._general_qa_payload(result_json)

        return {
            "state": ChatState.IDLE.value,
            "message": "문서 생성이나 회의록 기반 할 일 추출이 필요하면 요청해 주세요.",
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _confirmation_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        action = result_json.get("pending_action") or {}
        action_type = action.get("action_type")
        payload = action.get("payload") or {}
        if action_type == ChatActionType.EXTRACT_ACTION_ITEMS.value:
            message = "회의록을 기준으로 TODO 목록을 추출할까요?"
            confirm_label = "TODO 추출하기"
        else:
            artifact_label = self._artifact_label(payload.get("target_artifact_type"))
            source_ids = payload.get("source_document_ids") or []
            source_documents = payload.get("source_documents") or []
            source_text = self._source_document_display_text(
                source_documents=source_documents,
                source_ids=source_ids,
                source_document_type=payload.get("source_document_type"),
            )
            message = f"{source_text}를 기준으로 {artifact_label}를 생성할까요?"
            confirm_label = "생성하기"

        return {
            "state": ChatState.WAITING_CONFIRMATION.value,
            "message": message,
            "pending_action": action,
            "suggested_actions": [
                {
                    "type": ChatCommandType.CONFIRM_PENDING_ACTION.value,
                    "label": confirm_label,
                    "payload": {"action_id": action.get("action_id")},
                },
                {
                    "type": ChatCommandType.CANCEL_PENDING_ACTION.value,
                    "label": "취소",
                    "payload": {"action_id": action.get("action_id")},
                },
            ],
        }

    def _completed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        generation_result = result_json.get("result") or {}
        if self._is_schedule_todo_result(generation_result):
            return self.build_schedule_todo_display(generation_result)

        artifact = generation_result.get("artifact") or {}
        generated = generation_result.get("generated") or {}
        exported_file = generation_result.get("exported_file") or {}
        artifact_type = artifact.get("artifact_type") or generated.get("artifact_type")
        message = self._artifact_completion_message(artifact_type, exported_file)

        return {
            "state": ChatState.COMPLETED.value,
            "message": message,
            "result": {},
            "artifact_refs": self._artifact_refs_payload(artifact),
            "download_files": self._download_files_payload(
                artifact=artifact,
                exported_file=exported_file,
            ),
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _failed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        error = result_json.get("error") or "request failed"
        return {
            "state": ChatState.FAILED.value,
            "message": self._user_error_message(str(error)),
            "result": {"error": error},
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _todo_completed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        result = result_json.get("result") or {}
        todos = result.get("todos") or []
        items = self._schedule_todo_items(todos)
        title = items[0]["title"] if items else "선택한 TODO"
        return {
            "state": ChatState.COMPLETED.value,
            "message": f'"{title}" TODO를 완료로 변경했습니다.',
            "result": {**result, "items": items},
            "display_type": "schedule_todos",
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _required_info_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        artifact_type = result_json.get("target_artifact_type")
        messages = {
            "REQUIREMENT_SPEC": (
                "요구사항 정의서를 생성하려면 구축요건정의서 또는 RFP가 필요합니다. "
                "구축요건 정의서를 업로드해주세요."
            ),
            "WBS": "WBS 생성을 위해 기준이 되는 요구사항 명세서 문서를 먼저 선택해 주세요.",
            "SCREEN_DESIGN": (
                "화면설계서 생성을 위해 요구사항 명세서 또는 관련 화면 기준 문서를 "
                "먼저 선택해 주세요."
            ),
        }
        return {
            "state": ChatState.WAITING_REQUIRED_INFO.value,
            "message": messages.get(
                artifact_type,
                "진행하려면 기준 문서를 먼저 업로드하거나 선택해 주세요.",
            ),
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _general_qa_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": ChatState.IDLE.value,
            "message": (
                "PM 문서와 산출물 관련 요청으로 이해했습니다. 현재는 문서 생성과 "
                "회의록 기반 할 일 추출을 중심으로 도와드릴 수 있습니다."
            ),
            "result": {
                "topic": result_json.get("topic"),
                "query": result_json.get("query"),
            },
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def build_schedule_todo_display(
        self,
        result_json: dict[str, Any],
    ) -> dict[str, Any]:
        todos = result_json.get("todos") or []
        items = self._schedule_todo_items(todos)
        legacy_items = self._legacy_schedule_todo_items(todos)
        count = len(items)
        message = (
            f"회의록을 기준으로 다음 TODO를 추출했습니다. 할 일 {count}건"
            if count
            else "회의록에서 바로 수행할 TODO를 찾지 못했습니다."
        )
        return {
            "state": ChatState.COMPLETED.value if count else ChatState.FAILED.value,
            "message": message,
            "result": {**result_json, "items": items},
            "items": legacy_items,
            "display_type": "schedule_todos",
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _schedule_todo_items(self, todos: list[Any]) -> list[dict[str, Any]]:
        items = []
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            assignee = todo.get("assignee") or "담당자 미정"
            due_date = todo.get("due_date") or "기한 미정"
            status = todo.get("status") or "TODO"
            items.append(
                {
                    "todo_id": todo.get("todo_id"),
                    "title": todo.get("title") or "제목 없음",
                    "assignee": assignee,
                    "due_date": due_date,
                    "related_document": todo.get("related_document")
                    or "회의록 기반 신규 TODO",
                    "status": self._todo_status_label(status, assignee, due_date),
                    "description": todo.get("description") or "",
                }
            )
        return items

    def _legacy_schedule_todo_items(self, todos: list[Any]) -> list[dict[str, Any]]:
        items = []
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            items.append(
                {
                    "todo_id": todo.get("todo_id"),
                    "title": todo.get("title") or "제목 없음",
                    "assignee": todo.get("assignee") or "미정",
                    "due_date": todo.get("due_date") or "미정",
                    "description": todo.get("description") or "",
                }
            )
        return items

    def _todo_status_label(
        self,
        status: str,
        assignee: str,
        due_date: str,
    ) -> str:
        if status == "DONE":
            return "완료"
        if status == "NEEDS_CONFIRMATION":
            return "확인 필요"
        if assignee == "담당자 미정" or due_date == "기한 미정":
            return "확인 필요"
        return "예정"

    def _is_schedule_todo_result(self, result_json: dict[str, Any]) -> bool:
        return (
            result_json.get("artifact_type") == "SCHEDULE_TODO_LIST"
            or "todos" in result_json
        )

    def _artifact_completion_message(
        self,
        artifact_type: str | None,
        exported_file: dict[str, Any],
    ) -> str:
        file_suffix = " 아래 파일을 확인해 주세요." if exported_file else ""
        messages = {
            "REQUIREMENT_SPEC": (
                "요구사항 정의서가 생성되었습니다. 아래 파일을 확인해주세요."
            ),
            "WBS": f"WBS 문서가 생성되었습니다. 주요 일정과 작업 항목을 확인해 주세요.{file_suffix}",
            "SCREEN_DESIGN": f"화면설계서 초안이 생성되었습니다.{file_suffix}",
        }
        return messages.get(
            artifact_type or "",
            f"요청한 산출물이 생성되었습니다.{file_suffix}",
        )

    def _user_error_message(self, error: str) -> str:
        normalized = error.lower()
        if "source document is required" in normalized:
            return "진행하려면 기준 문서를 먼저 업로드하거나 선택해 주세요."
        if "source document not found" in normalized:
            return "선택한 문서를 찾지 못했습니다. 문서를 다시 선택해 주세요."
        if "must be generated from" in normalized:
            return "선택한 문서 유형이 맞지 않습니다. 기준 문서를 다시 확인해 주세요."
        if "meeting_notes is required" in normalized:
            return "회의록 내용을 입력해 주세요."
        if "no action items were found" in normalized:
            return (
                "회의 내용에서 바로 추출할 할 일을 찾지 못했습니다. 담당자나 "
                "할 일이 드러나도록 내용을 조금 더 구체적으로 입력해 주세요."
            )
        if "matching todo not found" in normalized:
            return "완료 처리할 TODO를 찾지 못했습니다. TODO 제목을 조금 더 정확히 입력해 주세요."
        return "요청을 처리하지 못했습니다. 내용을 확인한 뒤 다시 시도해 주세요."

    def _default_recommended_prompts(self) -> list[dict[str, str]]:
        return [
            {
                "label": "요구사항 정의서 생성",
                "message": "요구사항 정의서 생성해줘",
            },
            {
                "label": "WBS 생성",
                "message": "WBS 만들어줘",
            },
            {
                "label": "회의록 할 일 추출",
                "message": "회의록에서 할 일 뽑아줘",
            },
        ]

    def _artifact_label(self, artifact_type: str | None) -> str:
        labels = {
            "REQUIREMENT_SPEC": "요구사항 정의서",
            "WBS": "WBS",
            "SCREEN_DESIGN": "화면설계서",
        }
        return labels.get(artifact_type or "", "산출물")

    def _artifact_refs_payload(self, artifact: dict[str, Any]) -> list[dict[str, Any]]:
        artifact_id = artifact.get("artifact_id")
        if not artifact_id:
            return []
        return [
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact.get("artifact_type"),
                "name": artifact.get("name"),
            }
        ]

    def _download_files_payload(
        self,
        *,
        artifact: dict[str, Any],
        exported_file: dict[str, Any],
    ) -> list[dict[str, Any]]:
        artifact_id = artifact.get("artifact_id")
        if not artifact_id:
            return []

        file_name = str(
            exported_file.get("file_name")
            or self._default_file_name(artifact.get("artifact_type"))
        )
        mime_type = str(
            exported_file.get("content_type")
            or self._default_mime_type(artifact.get("artifact_type"))
        )
        return [
            {
                "artifact_id": artifact_id,
                "file_name": file_name,
                "mime_type": mime_type,
            }
        ]

    def _default_file_name(self, artifact_type: str | None) -> str:
        if artifact_type == "REQUIREMENT_SPEC":
            return "요구사항명세서.xlsx"
        if artifact_type == "SCREEN_DESIGN":
            return "화면설계서.pptx"
        if artifact_type == "WBS":
            return "WBS.xlsx"
        return "산출물 다운로드"

    def _default_mime_type(self, artifact_type: str | None) -> str:
        if artifact_type in {"REQUIREMENT_SPEC", "WBS"}:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if artifact_type == "SCREEN_DESIGN":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return "application/octet-stream"

    def _source_document_display_text(
        self,
        *,
        source_documents: list[dict[str, Any]],
        source_ids: list[str],
        source_document_type: str | None,
    ) -> str:
        document_label = ""
        for document in source_documents:
            if isinstance(document, dict) and document.get("display_label"):
                document_label = str(document.get("display_label")).strip()
                break
        if not document_label:
            document_label = (
                "업로드한 구축요건 정의서"
                if source_document_type == "CONSTRUCTION_REQUIREMENT_DEFINITION"
                else "선택한 문서"
            )

        file_names = [
            str(document.get("file_name") or document.get("original_filename") or "").strip()
            for document in source_documents
            if isinstance(document, dict)
        ]
        file_names = [file_name for file_name in file_names if file_name]

        if file_names:
            if len(file_names) == 1:
                return f'{document_label} "{file_names[0]}"'
            quoted_names = ", ".join(f'"{file_name}"' for file_name in file_names)
            return f"{document_label} {quoted_names}"

        if source_ids:
            return document_label

        return "선택한 문서"


chat_output_agent = ChatOutputAgent()
