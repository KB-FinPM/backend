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
        if event == "ACTION_STARTED":
            return self._started_payload(result_json)
        if event == "ACTION_COMPLETED":
            return self._completed_payload(result_json)
        if event == "ARTIFACT_DOWNLOAD_READY":
            return self._artifact_download_ready_payload(result_json)
        if event == "ARTIFACT_DOWNLOAD_REQUIRED_INFO":
            return self._artifact_download_required_info_payload(result_json)
        if event == "TODO_COMPLETED":
            return self._todo_completed_payload(result_json)
        if event == "SCHEDULE_RESULT":
            return self._schedule_result_payload(result_json)
        if event == "NO_PENDING_ACTION":
            return self._no_pending_action_payload(result_json)
        if event == "ACTION_FAILED":
            return self._failed_payload(result_json)
        if event == "ACTION_CANCELLED":
            return {
                "state": ChatState.IDLE.value,
                "message": "요청을 취소했습니다.",
                "suggested_actions": [],
            }
        if event == "CLARIFICATION_REQUIRED":
            return self._clarification_payload(result_json)
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
            cancel_label = "다른 회의록 업로드"
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
            cancel_label = "취소"

        return {
            "state": ChatState.WAITING_CONFIRMATION.value,
            "message": self._with_large_document_message(message, payload),
            "pending_action": action,
            "suggested_actions": [
                {
                    "type": ChatCommandType.CONFIRM_PENDING_ACTION.value,
                    "label": confirm_label,
                    "payload": {"action_id": action.get("action_id")},
                },
                {
                    "type": ChatCommandType.CANCEL_PENDING_ACTION.value,
                    "label": cancel_label,
                    "payload": {"action_id": action.get("action_id")},
                },
            ],
        }

    def _with_large_document_message(
        self,
        message: str,
        payload: dict[str, Any],
    ) -> str:
        large_document_message = self._large_document_message(
            payload.get("large_document_hint") or {}
        )
        if not large_document_message:
            return message
        return f"{message}\n{large_document_message}"

    def _large_document_message(self, hint: dict[str, Any]) -> str:
        if not isinstance(hint, dict) or not hint.get("is_large_document"):
            return ""
        chunk_count = hint.get("chunk_count")
        chunk_text = f" 예상 chunk 수: {chunk_count}." if chunk_count else ""
        return (
            "문서가 큰 경우 chunk/batch 처리에 시간이 걸릴 수 있습니다."
            f"{chunk_text}"
        )

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

    def _artifact_download_ready_payload(
        self,
        result_json: dict[str, Any],
    ) -> dict[str, Any]:
        artifact = result_json.get("artifact") or {}
        exported_file = {
            "file_name": result_json.get("file_name"),
            "content_type": result_json.get("content_type"),
            "download_url": result_json.get("download_url"),
        }
        artifact_type = artifact.get("artifact_type")
        artifact_label = self._artifact_label(artifact_type)
        return {
            "state": ChatState.COMPLETED.value,
            "message": f"{artifact_label} 다운로드를 준비했습니다.",
            "result": {
                "artifact_id": artifact.get("artifact_id"),
                "artifact_type": artifact_type,
                "filename": result_json.get("file_name"),
            },
            "artifact_refs": self._artifact_refs_payload(artifact),
            "download_files": self._download_files_payload(
                artifact=artifact,
                exported_file=exported_file,
            ),
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _artifact_download_required_info_payload(
        self,
        result_json: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "state": ChatState.WAITING_REQUIRED_INFO.value,
            "message": "다운로드할 산출물을 선택해 주세요.",
            "result": {
                "missing_fields": result_json.get("missing_fields") or ["artifact_id"],
                "available_artifacts": result_json.get("available_artifacts") or [],
            },
            "download_files": [],
            "artifact_refs": result_json.get("available_artifacts") or [],
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _started_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        action = result_json.get("pending_action") or {}
        action_id = action.get("action_id") or result_json.get("action_id")
        return {
            "state": ChatState.EXECUTING_ACTION.value,
            "message": "문서 생성을 시작하겠습니다.",
            "pending_action": action,
            "result": {
                "action_id": action_id,
                "job_id": action_id,
                "status": "EXECUTING",
                "generation_progress": self._safe_progress_payload(
                    result_json.get("generation_progress")
                ),
            },
            "suggested_actions": [],
            "recommended_prompts": [],
        }

    def _failed_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        error = result_json.get("error") or "request failed"
        message = self._user_error_message(str(error))
        if self._should_expose_failure_detail(str(error)):
            message = f"{message}\n원인: {error}"
        return {
            "state": ChatState.FAILED.value,
            "message": message,
            "result": {
                "error": error,
                "generation_progress": self._safe_progress_payload(
                    result_json.get("generation_progress")
                ),
            },
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
            "message": f'"{title}" 업무를 완료 처리했습니다.',
            "result": {**result, "items": items},
            "display_type": "schedule_todos",
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _schedule_result_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        result = result_json.get("result") or {}
        action = result.get("action")
        status = result.get("status")
        if status == "REQUIRED_INFO":
            return self._schedule_required_info_payload(result)
        if action == "SHOW_CURRENT_WEEK":
            return self._current_week_payload(result)
        if action in {
            "SHOW_THIS_WEEK_TODOS",
            "SHOW_NEXT_WEEK_TODOS",
            "SHOW_TODAY_TODOS",
            "SHOW_OVERDUE_TODOS",
            "SHOW_ASSIGNEE_TODOS",
            "ASSISTANT_BRIEFING",
            "COMPARE_WEEKLY_MEETING_TODOS",
        }:
            return self._schedule_query_payload(result)
        if action == "COMPLETE_TODO":
            return self._complete_todo_payload(result)
        if self._is_schedule_todo_result(result):
            return self.build_schedule_todo_display(result)
        return {
            "state": ChatState.IDLE.value,
            "message": "일정관리 요청을 처리했습니다.",
            "result": result,
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _no_pending_action_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        action = result_json.get("action")
        verb = "취소할" if action == "CANCEL" else "확인할"
        return {
            "state": ChatState.IDLE.value,
            "message": f"현재 {verb} 작업이 없습니다. 진행할 작업을 다시 입력해 주세요.",
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _clarification_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        corrections = self._safe_corrections(result_json.get("corrections"))
        message = result_json.get("question") or "어떤 요청인지 조금만 더 알려주세요."
        correction_notice = self._correction_notice(corrections)
        if correction_notice:
            message = f"{correction_notice}\n{message}"
        candidates = result_json.get("candidates") or []
        return {
            "state": ChatState.WAITING_REQUIRED_INFO.value,
            "message": message,
            "result": {
                "semantic_slots": result_json.get("semantic_slots") or {},
                "clarification_required": True,
                "candidates": candidates,
                "command_actions": self._clarification_command_actions(candidates),
            },
            "corrections": corrections,
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _safe_corrections(self, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        corrections = []
        for item in value:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if source and target:
                corrections.append({"source": source, "target": target})
        return corrections

    def _correction_notice(self, corrections: list[dict[str, str]]) -> str:
        if not corrections:
            return ""
        messages = [
            f"'{item['source']}'을 '{item['target']}'으로 이해했어요."
            for item in corrections[:3]
        ]
        return " ".join(messages)

    def _clarification_command_actions(
        self,
        candidates: list[Any],
    ) -> list[dict[str, str]]:
        labels = {
            "REQUIREMENT_SPEC": "요구사항 명세서",
            "WBS": "WBS",
            "SCREEN_DESIGN": "화면설계서",
            "UNITTEST_SPEC": "단위테스트케이스",
        }
        return [
            {
                "label": labels.get(str(candidate), str(candidate)),
                "message": f"{labels.get(str(candidate), str(candidate))} 만들어줘",
            }
            for candidate in candidates
            if str(candidate)
        ]

    def _required_info_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        artifact_type = result_json.get("target_artifact_type")
        missing_fields = result_json.get("missing_fields") or []
        if artifact_type == "WBS" and "project_start_date" in missing_fields:
            return {
                "state": ChatState.WAITING_REQUIRED_INFO.value,
                "message": "WBS 생성을 위해 프로젝트 시작일을 입력해주세요.",
                "result": {
                    "missing_fields": missing_fields,
                    "start_date_request": {
                        "label": "프로젝트 시작일",
                        "originalMessage": result_json.get("query") or "WBS 만들어줘",
                    },
                },
                "suggested_actions": [],
                "recommended_prompts": self._default_recommended_prompts(),
            }

        messages = {
            "REQUIREMENT_SPEC": (
                "요구사항 정의서를 만들려면 구축요건 정의서를 업로드해주세요.\n"
                "기술협상회의록이 있으면 함께 선택할 수 있습니다."
            ),
            "WBS": (
                "WBS를 만들려면 요구사항 정의서를 업로드해주세요.\n"
                "요구사항 정의서를 먼저 생성한 뒤 WBS를 만들 수 있습니다."
            ),
            "SCREEN_DESIGN": (
                "화면설계서를 만들려면 요구사항 정의서를 업로드해주세요.\n"
                "요구사항 정의서를 먼저 생성한 뒤 화면설계서를 만들 수 있습니다."
            ),
            "UNITTEST_SPEC": (
                "단위테스트케이스를 만들려면 화면설계서를 업로드해주세요.\n"
                "화면설계서를 먼저 생성한 뒤 단위테스트케이스를 만들 수 있습니다."
            ),
        }
        upload_request = self._upload_request_payload(
            artifact_type=artifact_type,
            original_message=result_json.get("query"),
        )
        result = {
            "required_source_document_types": result_json.get(
                "required_source_document_types"
            )
            or [],
        }
        if upload_request:
            result["upload_request"] = upload_request
        command_actions = self._missing_source_command_actions(artifact_type)
        if command_actions:
            result["command_actions"] = command_actions

        return {
            "state": ChatState.WAITING_REQUIRED_INFO.value,
            "message": messages.get(
                artifact_type,
                "산출물 생성을 위한 기준 문서를 업로드해주세요.",
            ),
            "result": result,
            "suggested_actions": [],
            "recommended_prompts": self._default_recommended_prompts(),
        }

    def _schedule_required_info_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        metadata = result.get("metadata") or {}
        required_context = str(metadata.get("required_context") or "").upper()
        missing_fields = result.get("missing_fields") or []
        if result.get("assistant_message"):
            message = str(result.get("assistant_message"))
            upload_request = None
            command_actions = []
        elif required_context == "WBS" or "wbs" in missing_fields:
            if metadata.get("has_requirement_source"):
                message = (
                    "현재 프로젝트에서 WBS를 찾지 못했습니다. 기존 WBS를 업로드하거나, "
                    "등록된 요구사항 정의서를 기준으로 WBS를 생성할 수 있습니다."
                )
                upload_request = {
                    "required": True,
                    "label": "WBS 업로드",
                    "acceptedTypes": [".xlsx"],
                    "documentType": "WBS",
                    "originalMessage": "WBS 기준으로 일정 알려줘",
                }
                command_actions = [
                    {
                        "label": "WBS 생성",
                        "message": "요구사항 정의서를 기준으로 WBS 생성해줘",
                    }
                ]
            else:
                message = (
                    "현재 프로젝트에서 WBS를 찾지 못했습니다. WBS를 업로드하거나, "
                    "요구사항 정의서를 먼저 생성한 뒤 WBS를 생성해 주세요."
                )
                upload_request = {
                    "required": True,
                    "label": "WBS 업로드",
                    "acceptedTypes": [".xlsx"],
                    "documentType": "WBS",
                    "originalMessage": "WBS 기준으로 일정 알려줘",
                }
                command_actions = [
                    {
                        "label": "요구사항 정의서 생성",
                        "message": "요구사항 정의서 생성해줘",
                    }
                ]
        elif required_context == "MEETING_NOTES" or "meeting_notes" in missing_fields:
            message = "회의록 내용을 붙여넣거나 주간회의 문서를 업로드해 주세요."
            upload_request = {
                "required": True,
                "label": "회의록 업로드",
                "acceptedTypes": self._meeting_upload_accept_types(),
                "documentType": "MEETING_NOTES",
                "originalMessage": "회의록 보고 TODO 정리해줘",
                "requestType": "MEETING_TODO_EXTRACTION",
                "resumeAfterUpload": True,
                "hideOutputFormat": True,
                "startMessage": "회의록에서 TODO를 추출하고 있습니다.",
            }
            command_actions = []
        elif required_context == "ASSIGNEE" or "assignee" in missing_fields:
            message = "담당자 이름을 알려주시면 남은 업무를 확인해 드릴게요."
            upload_request = None
            command_actions = []
        else:
            message = "일정 확인에 필요한 프로젝트 기준 정보가 부족합니다."
            upload_request = None
            command_actions = []

        payload_result = dict(result)
        if upload_request:
            payload_result["upload_request"] = upload_request
        if command_actions:
            payload_result["command_actions"] = command_actions
        return {
            "state": ChatState.WAITING_REQUIRED_INFO.value,
            "message": message,
            "result": payload_result,
            "suggested_actions": [],
            "recommended_prompts": self._schedule_recommended_prompts(),
        }

    def _general_qa_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        topic = result_json.get("topic")
        query = result_json.get("query")
        return {
            "state": ChatState.IDLE.value,
            "message": self._pm_concept_answer(topic=topic, query=query),
            "result": {
                "topic": topic,
                "query": query,
            },
            "suggested_actions": [],
            "recommended_prompts": self._topic_recommended_prompts(topic),
        }

    def _upload_request_payload(
        self,
        *,
        artifact_type: str | None,
        original_message: Any,
    ) -> dict[str, Any] | None:
        source_types = {
            "REQUIREMENT_SPEC": (
                "CONSTRUCTION_REQUIREMENT_DEFINITION",
                "구축요건 정의서 업로드",
            ),
            "WBS": ("REQUIREMENT_SPEC", "요구사항 정의서 업로드"),
            "SCREEN_DESIGN": ("REQUIREMENT_SPEC", "요구사항 정의서 업로드"),
            "UNITTEST_SPEC": ("SCREEN_DESIGN", "화면설계서 업로드"),
        }
        if artifact_type not in source_types:
            return None
        document_type, label = source_types[artifact_type]
        return {
            "required": True,
            "label": label,
            "acceptedTypes": self._document_upload_accept_types(),
            "documentType": document_type,
            "originalMessage": str(
                original_message or f"{self._artifact_label(artifact_type)} 생성해줘"
            ),
        }

    def _document_upload_accept_types(self) -> list[str]:
        return [
            ".pdf",
            "application/pdf",
            ".docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls",
            "application/vnd.ms-excel",
            ".md",
            ".txt",
            "text/plain",
            ".csv",
            ".json",
            "application/json",
            ".log",
        ]

    def _meeting_upload_accept_types(self) -> list[str]:
        return [
            ".pdf",
            "application/pdf",
            ".docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls",
            "application/vnd.ms-excel",
            ".txt",
            "text/plain",
        ]

    def _missing_source_command_actions(
        self,
        artifact_type: str | None,
    ) -> list[dict[str, str]]:
        return []

    def _pm_concept_answer(self, *, topic: Any, query: Any) -> str:
        topic_value = str(topic or "")
        if topic_value == "REQUIREMENT_SPEC":
            return (
                "요구사항 정의서는 구축요건정의서나 RFP의 내용을 실제 개발·구축 범위로 "
                "쪼개 정리한 기준 문서입니다. 보통 요구사항 ID, 구분, 요구사항명, 상세 내용, "
                "우선순위, 출처 같은 항목을 담고, 이후 WBS, 화면설계서, 단위테스트케이스를 "
                "만드는 기준으로 사용합니다."
            )
        if topic_value == "CONSTRUCTION_REQUIREMENT_DEFINITION":
            return (
                "구축요건정의서는 고객이 원하는 구축 범위, 업무 요건, 제약 조건, 연동 대상, "
                "일정 조건 등을 정리한 선행 문서입니다. RFP와 비슷하게 요구사항 정의서를 "
                "만들 때 입력 자료로 쓰이며, 내용이 구체적일수록 이후 산출물의 품질이 좋아집니다."
            )
        if topic_value == "WBS":
            return (
                "WBS는 프로젝트 범위를 작업 단위로 나누고 단계, 담당자, 기간, 선후관계를 "
                "정리한 일정 관리 문서입니다. PM Agent에서는 요구사항 정의서를 기준으로 분석, "
                "설계, 개발·구축, 테스트, 이행 같은 단계별 작업을 구성합니다."
            )
        if topic_value == "SCREEN_DESIGN":
            return (
                "화면설계서는 요구사항을 사용자가 보는 화면 흐름과 입력·출력 항목으로 옮긴 "
                "문서입니다. 현재 흐름에서는 요구사항 정의서의 기능·비기능 요구사항을 기준으로 "
                "화면 단위 초안을 생성합니다."
            )
        if topic_value == "UNITTEST_SPEC":
            return (
                "단위테스트케이스는 기능이 요구사항대로 동작하는지 확인하기 위한 테스트 조건, "
                "입력값, 기대 결과를 정리한 문서입니다. 요구사항 정의서나 화면설계서를 기준으로 작성합니다."
            )
        if topic_value == "ACTION_ITEMS":
            return (
                "TODO 또는 액션아이템은 회의나 업무 협의에서 정해진 후속 작업입니다. "
                "담당자, 기한, 관련 산출물, 상태를 함께 관리하면 누락 없이 진행 상황을 확인할 수 있습니다."
            )
        if topic_value == "MEETING_NOTES":
            return (
                "회의록은 논의 내용, 결정 사항, 이슈, 후속 작업을 남기는 문서입니다. "
                "회의록 내용을 붙여넣고 할 일 추출을 요청하면 담당자와 기한이 보이는 TODO를 정리할 수 있습니다."
            )

        normalized_query = str(query or "").strip()
        if normalized_query:
            return (
                "현재는 PM 산출물 생성과 일정 관리 중심으로 답변할 수 있습니다. "
                "요구사항 정의서, 구축요건정의서, WBS, 화면설계서, 회의록 TODO에 대해 "
                "궁금한 점을 물어보거나 산출물 생성을 요청해 주세요."
            )
        return "문서 생성이나 회의록 기반 할 일 추출이 필요하면 요청해 주세요."

    def _topic_recommended_prompts(self, topic: Any) -> list[dict[str, str]]:
        topic_value = str(topic or "")
        if topic_value == "REQUIREMENT_SPEC":
            return [
                {"label": "요구사항 정의서 생성", "message": "요구사항 정의서 생성해줘"},
                {"label": "구축요건정의서 설명", "message": "구축요건정의서가 뭐야?"},
                {"label": "WBS 생성", "message": "WBS 만들어줘"},
            ]
        if topic_value == "CONSTRUCTION_REQUIREMENT_DEFINITION":
            return [
                {"label": "요구사항 정의서 생성", "message": "요구사항 정의서 생성해줘"},
                {"label": "요구사항 정의서 설명", "message": "요구사항 정의서가 뭐야?"},
                {"label": "회의록 할 일 추출", "message": "회의록에서 할 일 뽑아줘"},
            ]
        if topic_value in {"ACTION_ITEMS", "MEETING_NOTES"}:
            return [
                {"label": "회의록 할 일 추출", "message": "회의록에서 할 일 뽑아줘"},
                {"label": "이번 주 일정", "message": "이번 주 해야 할 일 알려줘"},
                {"label": "요구사항 정의서 생성", "message": "요구사항 정의서 생성해줘"},
            ]
        return self._default_recommended_prompts()

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

    def _current_week_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        week_context = result.get("week_context") or {}
        status = result.get("status")
        if status == "REQUIRED_INFO":
            message = "프로젝트 시작일이 있어야 현재 주차를 계산할 수 있습니다."
        elif status == "BEFORE_PROJECT_START":
            message = "아직 프로젝트 시작 전입니다."
        elif status == "AFTER_PROJECT_END":
            message = "프로젝트 종료일 이후입니다."
        else:
            current_week = week_context.get("current_week")
            message = f"프로젝트 시작일 기준 현재는 {current_week}주차입니다."
        return {
            "state": ChatState.COMPLETED.value
            if status == "SUCCESS"
            else ChatState.WAITING_REQUIRED_INFO.value,
            "message": message,
            "result": result,
            "suggested_actions": [],
            "recommended_prompts": self._schedule_recommended_prompts(),
        }

    def _schedule_query_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        todos = result.get("todos") or []
        items = self._schedule_todo_items(todos)
        action = result.get("action")
        if result.get("assistant_message"):
            message = str(result.get("assistant_message"))
        elif action == "SHOW_OVERDUE_TODOS":
            message = (
                f"기한이 지난 TODO는 {len(items)}건입니다."
                if items
                else "기한이 지난 TODO가 없습니다."
            )
        elif action == "SHOW_NEXT_WEEK_TODOS":
            message = (
                f"다음 주 진행해야 할 업무는 {len(items)}건입니다."
                if items
                else "다음 주 진행해야 할 업무가 없습니다."
            )
        elif action == "SHOW_TODAY_TODOS":
            message = (
                f"오늘 챙겨야 할 업무는 {len(items)}건입니다."
                if items
                else "오늘 챙겨야 할 업무가 없습니다."
            )
        elif action == "SHOW_ASSIGNEE_TODOS":
            assignee = (result.get("metadata") or {}).get("assignee") or "해당 담당자"
            message = (
                f"{assignee} 담당자의 남은 업무는 {len(items)}건입니다."
                if items
                else f"{assignee} 담당자의 남은 업무가 없습니다."
            )
        elif action == "ASSISTANT_BRIEFING":
            message = (
                f"WBS와 기존 TODO를 기준으로 이번 주에 챙겨야 할 일을 {len(items)}건 정리했습니다."
                if items
                else "WBS와 기존 TODO 기준으로 이번 주에 바로 표시할 업무가 없습니다."
            )
        elif action == "COMPARE_WEEKLY_MEETING_TODOS":
            message = (
                "지난 회의와 이번 회의의 TODO를 비교했습니다."
                if items
                else "비교할 회의 TODO가 없습니다."
            )
        else:
            message = (
                f"이번 주 진행해야 할 TODO는 {len(items)}건입니다."
                if items
                else "이번 주 진행해야 할 TODO가 없습니다."
            )
        return {
            "state": ChatState.COMPLETED.value,
            "message": message,
            "result": {
                **result,
                "items": items,
                "schedule_table": self._schedule_table(items),
            },
            "display_type": "schedule_todos",
            "suggested_actions": [],
            "recommended_prompts": self._schedule_recommended_prompts(),
        }

    def _complete_todo_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        status = result.get("status")
        if status == "SUCCESS":
            todos = result.get("todos") or []
            items = self._schedule_todo_items(todos)
            title = items[0]["title"] if items else "선택한 TODO"
            return {
                "state": ChatState.COMPLETED.value,
                "message": (
                    f'"{title}" 업무를 완료 처리했습니다. '
                    f"남은 업무는 {len(result.get('remaining_todos') or [])}건입니다."
                ),
                "result": {
                    **result,
                    "items": items,
                    "schedule_table": self._schedule_table(items),
                },
                "display_type": "schedule_todos",
                "suggested_actions": [],
                "recommended_prompts": self._schedule_recommended_prompts(),
            }
        if status == "CLARIFICATION_REQUIRED":
            candidates = result.get("candidates") or []
            items = self._schedule_todo_items(candidates)
            return {
                "state": ChatState.WAITING_REQUIRED_INFO.value,
                "message": (
                    "완료 처리할 업무를 특정하지 못했습니다. "
                    "아래 TODO 중 어떤 업무를 완료했는지 선택해 주세요."
                ),
                "result": {
                    **result,
                    "items": items,
                    "schedule_table": self._schedule_table(items),
                },
                "display_type": "schedule_todos",
                "suggested_actions": [],
                "recommended_prompts": self._schedule_recommended_prompts(),
            }
        return {
            "state": ChatState.FAILED.value,
            "message": "완료 처리할 TODO를 찾지 못했습니다. TODO 제목을 조금 더 정확히 입력해 주세요.",
            "result": result,
            "suggested_actions": [],
            "recommended_prompts": self._schedule_recommended_prompts(),
        }

    def _schedule_todo_items(self, todos: list[Any]) -> list[dict[str, Any]]:
        items = []
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            assignee = todo.get("assignee_display") or todo.get("assignee") or "담당자 미정"
            due_date = todo.get("due_date") or todo.get("planned_end_date") or "기한 미정"
            status = str(todo.get("status") or "TODO")
            status_display = todo.get("status_display") or self._todo_status_value(
                status,
                assignee,
                due_date,
            )
            status_key = str(status).upper()
            is_completed = status_key in {"DONE", "COMPLETED"} or str(
                status_display
            ) == "완료"
            source_type = todo.get("source_type") or todo.get("source_artifact_type")
            related_document = (
                todo.get("related_artifact")
                or todo.get("source_label")
                or todo.get("source_document_name")
                or todo.get("related_document")
                or ("WBS" if str(source_type or "").upper() == "WBS" else "회의록 기반 신규 TODO")
            )
            todo_id = todo.get("todo_id")
            actions = (
                []
                if is_completed or not todo_id
                else [
                    {
                        "type": "COMPLETE_TODO",
                        "label": "완료",
                        "todo_id": todo_id,
                    }
                ]
            )
            items.append(
                {
                    "todo_id": todo_id,
                    "title": todo.get("title") or "제목 없음",
                    "assignee": assignee,
                    "due_date": due_date,
                    "related_document": related_document,
                    "source_type": source_type,
                    "source_document_id": todo.get("source_document_id"),
                    "status": status_display,
                    "status_code": status_key,
                    "description": todo.get("description") or "",
                    "actions": actions,
                }
            )
        return items

    def _schedule_table(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "columns": ["할 일", "담당자", "기한", "출처", "상태"],
            "items": items,
        }

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

    def _todo_status_value(
        self,
        status: str,
        assignee: str,
        due_date: str,
    ) -> str:
        if status in {"TODO", "NEEDS_CONFIRMATION", "DONE", "OVERDUE"}:
            return status
        if assignee == "담당자 미정" or due_date == "기한 미정":
            return "NEEDS_CONFIRMATION"
        return "TODO"

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
            "WBS": f"WBS가 생성되었습니다.{file_suffix}",
            "SCREEN_DESIGN": f"화면설계서가 생성되었습니다.{file_suffix}",
            "UNITTEST_SPEC": f"단위테스트케이스가 생성되었습니다.{file_suffix}",
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

    def _should_expose_failure_detail(self, error: str) -> bool:
        normalized = error.lower()
        return any(
            marker in normalized
            for marker in (
                "artifactexportservice",
                "artifact export",
                "template file not found",
                "s3 upload",
                "upload failed",
                "failed to upload",
            )
        )

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

    def _schedule_recommended_prompts(self) -> list[dict[str, str]]:
        return [
            {
                "label": "이번 주 할 일",
                "message": "이번 주 해야 할 일 알려줘",
            },
            {
                "label": "기한 지난 업무",
                "message": "기한 지난 업무 보여줘",
            },
            {
                "label": "현재 주차",
                "message": "지금 프로젝트 몇 주차야?",
            },
        ]

    def _artifact_label(self, artifact_type: str | None) -> str:
        labels = {
            "REQUIREMENT_SPEC": "요구사항 정의서",
            "WBS": "WBS",
            "SCREEN_DESIGN": "화면설계서",
            "UNITTEST_SPEC": "단위테스트계획서",
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
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": artifact.get("artifact_type"),
            "file_name": file_name,
            "mime_type": mime_type,
            "content_type": mime_type,
        }
        download_url = exported_file.get("download_url")
        if download_url:
            payload["download_url"] = download_url
        return [payload]

    def _safe_progress_payload(self, progress: Any) -> dict[str, Any]:
        return dict(progress) if isinstance(progress, dict) else {}

    def _default_file_name(self, artifact_type: str | None) -> str:
        if artifact_type == "REQUIREMENT_SPEC":
            return "요구사항명세서.xlsx"
        if artifact_type == "SCREEN_DESIGN":
            return "화면설계서.pptx"
        if artifact_type == "WBS":
            return "WBS.xlsx"
        if artifact_type == "UNITTEST_SPEC":
            return "단위테스트케이스.xlsx"
        return "산출물 다운로드"

    def _default_mime_type(self, artifact_type: str | None) -> str:
        if artifact_type in {"REQUIREMENT_SPEC", "WBS", "UNITTEST_SPEC"}:
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
                else "업로드한 요구사항 명세서"
                if source_document_type == "REQUIREMENT_SPEC"
                else "선택한 문서"
            )

        file_names = [
            str(
                document.get("file_name")
                or document.get("original_filename")
                or document.get("name")
                or ""
            ).strip()
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
