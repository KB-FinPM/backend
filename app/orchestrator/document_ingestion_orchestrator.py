# EN: Orchestrates uploaded document ingestion flows.
# KO: 업로드 문서 수집/처리 흐름을 제어하는 Orchestrator입니다.

import inspect
from typing import Any
from uuid import uuid4

from app.agents.input_agents.document_parser_agent.agent import (
    DocumentParserAgent,
    document_parser_agent,
)
from app.rag.chunking import split_text_into_chunks
from app.rag.embedding import EmbeddingService, embedding_service
from app.repositories.document_repository import DocumentRepository
from app.schemas.artifact import DocumentMetadata, DocumentStatus, DocumentType
from app.schemas.io_agent import InputAgentRequest, InputFilePayload, InputType
from app.schemas.progress import build_generation_progress, build_progress_segment


class DocumentIngestionOrchestrator:
    """Coordinates parsing, chunking, persistence, and status transitions."""

    def __init__(
        self,
        parser: DocumentParserAgent = document_parser_agent,
        embedding_service: EmbeddingService = embedding_service,
    ) -> None:
        self.parser = parser
        self.embedding_service = embedding_service

    async def ingest_uploaded_document(
        self,
        *,
        document_repository: DocumentRepository,
        document_id: str,
        project_id: str,
        document_type: DocumentType,
        file_name: str,
        storage_path: str,
        file_bytes: bytes,
        parsed_context: dict | None = None,
        progress_reporter: Any = None,
    ) -> DocumentMetadata:
        # TODO: Add PDF/DOCX parser agents and embedding/vector-store indexing after
        # text ingestion is stable.
        document = await document_repository.create_document(
            document_id=document_id,
            project_id=project_id,
            document_type=document_type,
            file_name=file_name,
            storage_path=storage_path,
        )

        parsed_response = None
        if parsed_context is None:
            parsed_response = await self.parser.parse(
                InputAgentRequest(
                    project_id=project_id,
                    input_type=InputType.FILE,
                    files=[
                        InputFilePayload(
                            file_name=file_name,
                            file_bytes=file_bytes,
                        )
                    ],
                    context={
                        "document_id": document_id,
                        "document_type": document_type.value,
                        "storage_path": storage_path,
                    },
                )
            )
            if not parsed_response.success:
                return await self._mark_failed(
                    document_repository=document_repository,
                    document=document,
                )
            parsed_context = parsed_response.structured_context

        parsed_text = str(parsed_context.get("text", ""))
        parsed_metadata = parsed_context.get("metadata", {})
        parser_name = parsed_context.get("parser_name")
        if parsed_response is not None:
            parser_name = parsed_response.agent_name

        generated_requirements = parsed_context.get("requirements")
        wbs_context = parsed_context.get("wbs_context") or parsed_metadata.get(
            "wbs_context"
        )
        if isinstance(wbs_context, dict) and isinstance(
            wbs_context.get("rows"), list
        ) and wbs_context.get("rows"):
            base_metadata = {
                key: value
                for key, value in parsed_metadata.items()
                if key != "wbs_context"
            }
            context_summary = {
                key: value
                for key, value in wbs_context.items()
                if key != "rows"
            }
            row_items: list[dict[str, object]] = []
            for index, row in enumerate(wbs_context.get("rows") or []):
                if not isinstance(row, dict):
                    continue
                text = " | ".join(
                    str(value)
                    for value in [
                        row.get("row_number"),
                        row.get("level"),
                        row.get("wbs_id") or row.get("ID"),
                        row.get("title") or row.get("WBS명"),
                        row.get("planned_start_date") or row.get("시작예정일"),
                        row.get("planned_end_date") or row.get("종료예정일"),
                        row.get("raw_assignee") or row.get("작업자"),
                        row.get("artifact") or row.get("산출물"),
                        row.get("raw_status") or row.get("작업상태"),
                    ]
                    if value not in (None, "")
                )
                row_items.append(
                    {
                        "chunk_index": index,
                        "text": text or str(row.get("title") or row.get("WBS명") or "WBS"),
                        "section_title": str(row.get("title") or row.get("WBS명") or "WBS"),
                        "chunk_metadata": {
                            **base_metadata,
                            "parser_name": parser_name or "DocumentParserAgent",
                            "document_type": document_type.value,
                            "source_document_type": document_type.value,
                            "document_file_name": file_name,
                            "source_file_name": file_name,
                            "wbs_context": context_summary,
                            "wbs_row": row,
                        },
                    }
                )
            await self._embed_and_store_items(
                document_repository=document_repository,
                project_id=project_id,
                document_id=document_id,
                items=row_items,
                progress_reporter=progress_reporter,
            )
        elif (
            parsed_metadata.get("artifact_type") == "REQUIREMENT_SPEC"
            and isinstance(generated_requirements, list)
            and generated_requirements
        ):
            requirement_items: list[dict[str, object]] = []
            for index, requirement in enumerate(generated_requirements):
                if not isinstance(requirement, dict):
                    continue
                metadata = requirement.get("metadata") or {}
                text = "\n".join(
                    str(value)
                    for value in [
                        requirement.get("requirement_id"),
                        metadata.get("biz_requirement_name"),
                        metadata.get("domain"),
                        requirement.get("title"),
                        requirement.get("description"),
                    ]
                    if value
                )
                requirement_items.append(
                    {
                        "chunk_index": index,
                        "text": text,
                        "section_title": str(metadata.get("biz_requirement_name") or "요구사항"),
                        "chunk_metadata": {
                            **parsed_metadata,
                            "parser_name": parser_name or "ArtifactExportService",
                            "document_type": document_type.value,
                            "source_document_type": document_type.value,
                            "document_file_name": file_name,
                            "source_file_name": file_name,
                            "requirement": requirement,
                        },
                    }
                )
            await self._embed_and_store_items(
                document_repository=document_repository,
                project_id=project_id,
                document_id=document_id,
                items=requirement_items,
                progress_reporter=progress_reporter,
            )
        elif (
            parsed_metadata.get("artifact_type") == "SCREEN_DESIGN"
            and isinstance(parsed_context.get("screens"), list)
            and parsed_context.get("screens")
        ):
            screen_items: list[dict[str, object]] = []
            base_metadata = {
                key: value for key, value in parsed_metadata.items() if key != "screens"
            }
            for index, screen in enumerate(parsed_context.get("screens") or []):
                if not isinstance(screen, dict):
                    continue
                metadata = screen.get("metadata") or {}
                display_items = metadata.get("display_items") or screen.get(
                    "display_items"
                )
                if isinstance(display_items, list):
                    display_items_text = ", ".join(str(item) for item in display_items)
                else:
                    display_items_text = str(display_items or "")
                source_requirement_ids = ", ".join(
                    str(value).strip()
                    for value in screen.get("source_requirement_ids") or []
                    if str(value).strip()
                )
                text = " | ".join(
                    str(value or "")
                    for value in [
                        screen.get("screen_id"),
                        screen.get("name") or screen.get("screen_name"),
                        screen.get("description"),
                        display_items_text,
                        source_requirement_ids,
                    ]
                )
                screen_items.append(
                    {
                        "chunk_index": index,
                        "text": text,
                        "section_title": str(
                            screen.get("name")
                            or screen.get("screen_name")
                            or screen.get("screen_id")
                            or "SCREEN"
                        ),
                        "chunk_metadata": {
                            **base_metadata,
                            "parser_name": parser_name or "ArtifactExportService",
                            "document_type": document_type.value,
                            "source_document_type": document_type.value,
                            "document_file_name": file_name,
                            "source_file_name": file_name,
                            "screen": screen,
                            "screen_artifact": {
                                "artifact_type": "SCREEN_DESIGN",
                                "screens": [screen],
                                "metadata": parsed_metadata.get("metadata") or {},
                            },
                        },
                    }
                )
            await self._embed_and_store_items(
                document_repository=document_repository,
                project_id=project_id,
                document_id=document_id,
                items=screen_items,
                progress_reporter=progress_reporter,
            )
        else:
            chunks = split_text_into_chunks(parsed_text)
            if not chunks:
                return await self._mark_failed(
                    document_repository=document_repository,
                    document=document,
                )

            chunk_items = [
                {
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "section_title": chunk.section_title,
                    "chunk_metadata": {
                        **chunk.metadata,
                        **parsed_metadata,
                        "parser_name": parser_name or "InputOrchestrator",
                        "document_type": document_type.value,
                        "source_document_type": document_type.value,
                        "document_file_name": file_name,
                        "source_file_name": file_name,
                    },
                }
                for chunk in chunks
            ]
            await self._embed_and_store_items(
                document_repository=document_repository,
                project_id=project_id,
                document_id=document_id,
                items=chunk_items,
                progress_reporter=progress_reporter,
            )

        indexed_document = await document_repository.update_document_status(
            project_id=project_id,
            document_id=document_id,
            status=DocumentStatus.INDEXED,
        )
        return indexed_document or document

    async def _embed_and_store_items(
        self,
        *,
        document_repository: DocumentRepository,
        project_id: str,
        document_id: str,
        items: list[dict[str, object]],
        progress_reporter: Any = None,
    ) -> None:
        total = len(items)
        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="INPUT_AGENT_DOCUMENT_ANALYSIS",
                stage_label="Input Agent 문서 분석 중",
                progress=25,
                progress_text="문서 chunk 준비 중",
                sub_progress=build_progress_segment(
                    progress_type="CHUNK_PROCESSING",
                    label="원본 문서 chunk 처리",
                    current=total,
                    total=total,
                    unit="chunks",
                ),
            ),
        )
        if total <= 0:
            return

        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="INPUT_AGENT_DOCUMENT_ANALYSIS",
                stage_label="Input Agent 문서 분석 중",
                progress=30,
                progress_text="임베딩 처리 중",
                sub_progress=build_progress_segment(
                    progress_type="EMBEDDING",
                    label="임베딩 처리",
                    current=0,
                    total=total,
                    unit="chunks",
                ),
            ),
        )
        embeddings = await self.embedding_service.embed_texts(
            [str(item["text"]) for item in items]
        )
        await self._emit_progress(
            progress_reporter,
            build_generation_progress(
                stage="INPUT_AGENT_DOCUMENT_ANALYSIS",
                stage_label="Input Agent 문서 분석 중",
                progress=35,
                progress_text="임베딩 처리 중",
                sub_progress=build_progress_segment(
                    progress_type="EMBEDDING",
                    label="임베딩 처리",
                    current=len(embeddings),
                    total=total,
                    unit="chunks",
                ),
            ),
        )

        for index, (item, embedding) in enumerate(zip(items, embeddings), start=1):
            await document_repository.create_chunk(
                chunk_id=f"CHUNK-{uuid4().hex[:12].upper()}",
                project_id=project_id,
                document_id=document_id,
                chunk_index=int(item["chunk_index"]),
                text=str(item["text"]),
                section_title=str(item["section_title"]),
                chunk_metadata=item["chunk_metadata"],
                embedding=embedding,
            )
            await self._emit_progress(
                progress_reporter,
                build_generation_progress(
                    stage="INPUT_AGENT_DOCUMENT_ANALYSIS",
                    stage_label="Input Agent 문서 분석 중",
                    progress=40,
                    progress_text="인덱싱 처리 중",
                    sub_progress=build_progress_segment(
                        progress_type="INDEXING",
                        label="인덱싱 처리",
                        current=index,
                        total=total,
                        unit="chunks",
                    ),
                ),
            )

    async def _emit_progress(
        self,
        progress_reporter: Any,
        payload: dict[str, Any],
    ) -> None:
        if progress_reporter is None:
            return
        result = progress_reporter(payload)
        if inspect.isawaitable(result):
            await result

    async def _mark_failed(
        self,
        *,
        document_repository: DocumentRepository,
        document: DocumentMetadata,
    ) -> DocumentMetadata:
        failed_document = await document_repository.update_document_status(
            project_id=document.project_id,
            document_id=document.document_id,
            status=DocumentStatus.FAILED,
        )
        return failed_document or document


document_ingestion_orchestrator = DocumentIngestionOrchestrator()
