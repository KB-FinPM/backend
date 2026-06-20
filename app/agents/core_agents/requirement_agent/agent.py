# EN: Core agent for generating requirement artifacts from structured context.
# KO: 구조화된 컨텍스트를 기반으로 요구사항 산출물을 생성하는 Core Agent입니다.

import json
from time import perf_counter
from typing import Any, Callable

from app.core.config import settings
from app.core.logger import get_logger
from app.agents.core_agents.requirement_agent.document_preprocessor import (
    normalize_requirement_documents,
)
from app.schemas.agent import AgentRequest, AgentResponse
from util.agent_generation_utils import (
    assign_requirement_ids,
    atoms_to_requirement_artifact,
    deduplicate_requirement_atoms,
    normalize_requirement_atoms,
    parse_json_array,
    parse_json_object,
    extract_requirement_atoms_from_pipe_tables,
)
from util.agent_template_utils import mapper_summary_for_prompt

logger = get_logger(__name__)
LLM_LOG_PREFIX = "!!! LLM"


EXTRACTION_SYSTEM_PROMPT = """
너는 PM Agent의 구축요건정의서 분석기다.
입력 chunk에서 요구사항명세서에 들어갈 요구사항 atom을 추출하라.
반드시 JSON 배열만 반환한다.
각 항목 schema:
[
  {"category":"기능 | 비기능 | 인터페이스 | 데이터 | 정책 | 인프라 | 보안 | 운영","biz_requirement_id":"Biz요건ID 또는 빈 문자열","biz_requirement_name":"Biz요건명 또는 업무영역","requirement_name":"요구사항명","requirement_type":"기능요구사항 | 비기능요구사항","domain":"업무영역","feature":"기능명 또는 구축항목","description":"요구사항 설명","note":"검토의견 또는 비고"}
]
규칙:
- 문서에 없는 내용은 추측하지 않는다.
- 원문에 요구사항ID(BFE-xxxxx 등), Biz요건ID가 있으면 그대로 보존한다.
- 하나의 요구사항은 하나의 atom으로 분리한다.
- 표 형태 입력은 행 단위의 주요내용/상세를 각각 요구사항 후보로 분리한다.
- 중복 요구사항은 최대한 만들지 않는다.
- Biz요건명은 실제 요구사항명세서/WBS 그룹핑의 기준이 되므로 명확히 작성한다.
- description은 원문을 그대로 줄이는 수준이 아니라 기능 목적, 처리 방식,
  운영/제약 포인트를 포함해 조금 더 구체적으로 작성한다.
- acceptance_criteria는 검증 가능한 문장으로 2~4개 작성한다.
- 인프라 구축 프로젝트에서는 OCP, Kafka, EFK, CDC, API Gateway, Service Mesh, Monitoring, Logging, DB, 보안, 백업 등을 Biz요건명 후보로 본다.
- 개발 프로젝트에서는 업무, 화면, 기능, 인터페이스, 데이터, 권한, 배치 등을 Biz요건명 후보로 본다.
- source_document_context에 meeting_notes가 있으면 회의록 제목과 내용을 기준으로 요구사항을 보완/추가한다.
- 기능 구현과 직접 관련 있으면 기능요구사항으로 분류한다.
- 성능, 보안, 권한, 로그, 접근성, 운영, 백업, 장애대응은 비기능요구사항으로 분류한다.
- 각 description은 120자 이내로 요약한다.
- note는 50자 이내로 작성한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


TABLE_EXTRACTION_SYSTEM_PROMPT = """
너는 PM Agent의 구축요건정의서 표 분석기다.
입력으로 제공된 표 기반 요구사항 후보와 원문 chunk를 검토하여 요구사항명세서에 들어갈 atom을 정리하라.
반드시 JSON 배열만 반환한다.
각 항목 schema:
[
  {"category":"기능 | 비기능 | 인터페이스 | 데이터 | 정책 | 인프라 | 보안 | 운영","biz_requirement_id":"Biz요건ID 또는 빈 문자열","biz_requirement_name":"Biz요건명 또는 업무영역","requirement_name":"요구사항명","requirement_type":"기능요구사항 | 비기능요구사항","domain":"업무영역","feature":"기능명 또는 구축항목","description":"요구사항 설명","note":"검토의견 또는 비고","source_document_id":"문서ID","source_chunk_id":"chunkID"}
]
규칙:
- 원문 또는 후보에 있는 ID와 업무영역은 최대한 보존한다.
- 중복 요구사항은 병합한다.
- 각 description은 표와 원문 맥락을 반영해 1~2문장으로 구체화한다.
- acceptance_criteria는 실제 검증 가능한 문장으로 2~4개 작성한다.
- source_document_context에 meeting_notes가 있으면 회의록 제목과 내용을 함께 반영한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


TABLE_REFINEMENT_SYSTEM_PROMPT = """
너는 PM Agent의 구축요건정의서 행 단위 보정기다.
입력으로 주어지는 후보 1건만 보고, 같은 의미를 유지한 채 요구사항명세서용 내용을 다듬어라.
반드시 JSON 객체 1개만 반환한다.

스키마:
{
  "category":"기능 | 비기능 | 인터페이스 | 데이터 | 정책 | 인프라 | 보안 | 운영",
  "biz_requirement_id":"Biz요건ID 또는 빈 문자열",
  "biz_requirement_name":"Biz요건명 또는 업무영역",
  "requirement_name":"요구사항명",
  "requirement_type":"기능요구사항 | 비기능요구사항",
  "domain":"업무영역",
  "feature":"기능명 또는 구축항목",
  "description":"요구사항 설명",
  "note":"검토의견 또는 비고",
  "acceptance_criteria":["검증 가능한 문장"]
}

규칙:
- 후보 1건의 범위만 유지하고 다른 행, 다른 화면, 문서 전체를 섞지 않는다.
- description은 후보 내용을 바탕으로 목적/처리/제약을 1~2문장으로 구체화한다.
- description 길이는 120자 이내로 유지한다.
- requirement_name과 biz_requirement_name은 후보 값을 최대한 보존한다.
- acceptance_criteria는 2~4개만 작성한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


TABLE_BATCH_REFINEMENT_SYSTEM_PROMPT = """
너는 PM Agent의 구축요건정의서 행 단위 보정기다.
입력으로 주어지는 후보 목록만 보고, 각 후보를 같은 의미를 유지한 채 요구사항명세서용 내용으로 다듬어라.
반드시 JSON 배열만 반환한다.

스키마:
[
  {
    "category":"기능 | 비기능 | 인터페이스 | 데이터 | 정책 | 인프라 | 보안 | 운영",
    "biz_requirement_id":"Biz요건ID 또는 빈 문자열",
    "biz_requirement_name":"Biz요건명 또는 업무영역",
    "requirement_name":"요구사항명",
    "requirement_type":"기능요구사항 | 비기능요구사항",
    "domain":"업무영역",
    "feature":"기능명 또는 구축항목",
    "description":"요구사항 설명",
    "note":"검토의견 또는 비고",
    "acceptance_criteria":["검증 가능한 문장"]
  }
]

규칙:
- 입력 후보의 순서와 출력 배열의 순서를 반드시 맞춘다.
- 후보 하나당 결과 하나를 반환한다.
- 설명은 후보 내용을 바탕으로 목적/처리/제약을 1~2문장으로 구체화한다.
- description 길이는 120자 이내로 유지한다.
- requirement_name과 biz_requirement_name은 후보 값을 최대한 보존한다.
- acceptance_criteria는 2~4개만 작성한다.
- source_document_context에 meeting_notes가 있으면 회의록 제목과 내용을 함께 반영한다.
- JSON 외의 설명 문장은 절대 출력하지 않는다.
""".strip()


class RequirementAgent:
    """
    Generates requirement JSON from retrieved project context.

    The agent follows the original sample_0605 extraction flow more closely:
    each source chunk is analyzed independently, JSON-array atoms are merged,
    deduplicated, then BIZ/REQ IDs are assigned. Core agents still do not access
    S3, pgvector, Bedrock clients, or DB directly; model calls are delegated
    through GenerationOrchestrator.invoke_agent_llm().
    """

    AGENT_NAME = "RequirementAgent"

    def __init__(
        self,
        *,
        model_invoker: Any = None,
        requirement_atom_extractor: Callable[[list[dict]], list[Any]] = (
            extract_requirement_atoms_from_pipe_tables
        ),
    ) -> None:
        self.model_invoker = model_invoker
        self.requirement_atom_extractor = requirement_atom_extractor

    def with_model_invoker(self, model_invoker: Any) -> "RequirementAgent":
        return RequirementAgent(
            model_invoker=model_invoker,
            requirement_atom_extractor=self.requirement_atom_extractor,
        )

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}")
        started_at = perf_counter()

        try:
            result = await self._generate_with_model(request)
            if result is None:
                documents = normalize_requirement_documents(request.documents)
                atoms = normalize_requirement_atoms(None, documents=documents)
                atoms = assign_requirement_ids(deduplicate_requirement_atoms(atoms))
                if not atoms:
                    return AgentResponse(
                        success=False,
                        agent_name=self.AGENT_NAME,
                        error="No source document chunks available for requirement generation",
                    )
                result = atoms_to_requirement_artifact(
                    atoms,
                    project_id=request.project_id,
                    generated_by=self.AGENT_NAME,
                )
                self._apply_request_metadata(result, request)

            requirement_count = len(result.get("requirements", [])) if isinstance(result, dict) else 0
            logger.info(
                f"[{self.AGENT_NAME}] generate done | "
                f"project_id={request.project_id} | "
                f"requirements={requirement_count} | "
                f"duration_ms={int((perf_counter() - started_at) * 1000)}"
            )
            return AgentResponse(agent_name=self.AGENT_NAME, result=result)

        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    async def _generate_with_model(
        self,
        request: AgentRequest,
    ) -> dict[str, Any] | None:
        started_at = perf_counter()
        model_invoker = self.model_invoker
        if model_invoker is None or not hasattr(model_invoker, "invoke_agent_llm"):
            logger.info(
                f"[{self.AGENT_NAME}] model invoker unavailable | "
                f"project_id={request.project_id}"
            )
            return None

        documents = normalize_requirement_documents(request.documents)
        if not documents:
            logger.info(
                f"[{self.AGENT_NAME}] no normalized documents | "
                f"project_id={request.project_id}"
            )
            return None

        max_source_chunks = max(settings.GENERATION_MAX_SOURCE_CHUNKS, 1)
        if len(documents) > max_source_chunks:
            logger.info(
                f"[{self.AGENT_NAME}] source chunk cap applied | "
                f"project_id={request.project_id} | "
                f"original_count={len(documents)} | capped_count={max_source_chunks}"
            )
            documents = documents[:max_source_chunks]

        source_document_context = self._build_source_document_context(documents)
        request.context = {
            **(request.context or {}),
            "source_document_context": source_document_context,
        }

        logger.info(
            f"[{self.AGENT_NAME}] orchestrator path start | "
            f"project_id={request.project_id} | document_count={len(documents)}"
        )
        llm_call_count = 0

        # 1) Existing 구축요건정의서 files often already contain structured
        # requirement tables. Extract deterministic candidates first, then send
        # them through the orchestrator LLM boundary so the Bedrock path and
        # logging are exercised consistently.
        table_atoms = self.requirement_atom_extractor(documents)
        logger.info(
            f"[{self.AGENT_NAME}] table extraction result | "
            f"project_id={request.project_id} | table_atom_count={len(table_atoms)}"
        )
        if table_atoms:
            batch_size = max(settings.GENERATION_REQUIREMENT_TABLE_BATCH_SIZE, 1)
            batches = [
                table_atoms[index : index + batch_size]
                for index in range(0, len(table_atoms), batch_size)
            ]
            total_calls = len(batches)
            logger.info(
                f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} table path -> LLM | "
                f"project_id={request.project_id} | candidate_count={len(table_atoms)} | "
                f"batch_size={batch_size} | planned_calls={total_calls}"
            )
            chunk_items: list[dict[str, Any]] = []
            for batch_index, batch in enumerate(batches, start=1):
                prompt = self._build_table_batch_prompt(
                    request,
                    batch,
                    batch_index,
                    len(batches),
                )
                prompt_chars = len(prompt)
                logger.info(
                    f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} table batch start | "
                    f"project_id={request.project_id} | "
                    f"call={batch_index}/{total_calls} | "
                    f"batch_size={len(batch)} | prompt_chars={prompt_chars}"
                )
                llm_result = await self._invoke_model_or_fallback(
                    model_invoker,
                    system_prompt=TABLE_BATCH_REFINEMENT_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    call_index=batch_index,
                    call_total=total_calls,
                    call_label="requirement-table-batch",
                )
                if llm_result is None:
                    for atom in batch:
                        chunk_items.append(self._table_atom_fallback_payload(atom))
                    continue
                llm_call_count += 1
                parsed_items = self._parse_table_batch_response(llm_result)
                for atom, parsed_item in zip(batch, parsed_items):
                    chunk_items.append(self._merge_table_atom_with_result(atom, parsed_item))
                if len(parsed_items) < len(batch):
                    for atom in batch[len(parsed_items):]:
                        chunk_items.append(self._table_atom_fallback_payload(atom))
                logger.info(
                    f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} table batch done | "
                    f"project_id={request.project_id} | "
                    f"call={batch_index}/{total_calls} | "
                    f"parsed_items={len(parsed_items)} | "
                    f"accumulated_atoms={len(chunk_items)} | "
                    f"actual_llm_calls={llm_call_count}"
                )

            atoms = normalize_requirement_atoms(chunk_items, documents=None) if chunk_items else table_atoms
            atoms = assign_requirement_ids(deduplicate_requirement_atoms(atoms))
            result = atoms_to_requirement_artifact(
                atoms,
                project_id=request.project_id,
                generated_by=self.AGENT_NAME,
            )
            self._apply_request_metadata(result, request)
            logger.info(
                f"[{self.AGENT_NAME}] table path done | "
                f"project_id={request.project_id} | "
                f"actual_llm_calls={llm_call_count} | "
                f"table_atoms={len(table_atoms)} | "
                f"duration_ms={int((perf_counter() - started_at) * 1000)}"
            )
            return result

        # 2) Fallback to sample_0605 chunk-by-chunk LLM extraction when no
        # source requirement table is detected.
        runnable_documents = [
            document
            for document in documents
            if str(document.get("text") or "").strip()
        ]
        logger.info(
            f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} chunk fallback path -> LLM | "
            f"project_id={request.project_id} | planned_calls={len(runnable_documents)}"
        )
        atoms = []
        batch_size = max(settings.GENERATION_REQUIREMENT_BATCH_SIZE, 1)
        batches = [
            runnable_documents[index : index + batch_size]
            for index in range(0, len(runnable_documents), batch_size)
        ]
        total_calls = len(batches)
        for batch_index, batch in enumerate(batches, start=1):
            text_chars = sum(len(str(document.get("text") or "")) for document in batch)
            prompt = self._build_batch_prompt(
                request,
                batch,
                batch_index,
                len(batches),
            )
            prompt_chars = len(prompt)
            logger.info(
                f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} chunk batch start | "
                f"project_id={request.project_id} | "
                f"batch_index={batch_index} | batch_count={len(batches)} | "
                f"chunk_count={len(batch)} | text_chars={text_chars} | "
                f"prompt_chars={prompt_chars}"
            )
            llm_result = await self._invoke_model_or_fallback(
                model_invoker,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=prompt,
                call_index=batch_index,
                call_total=total_calls,
                call_label="requirement-batch",
            )
            if llm_result is None:
                return None
            llm_call_count += 1
            chunk_items = parse_json_array(llm_result)
            if not chunk_items:
                parsed_obj = parse_json_object(llm_result)
                if parsed_obj and isinstance(parsed_obj.get("requirements"), list):
                    chunk_items = [
                        item for item in parsed_obj["requirements"] if isinstance(item, dict)
                    ]
            fallback_document = batch[0] if batch else {}
            for item in chunk_items:
                source_chunk_id = item.get("source_chunk_id")
                source_document = self._document_by_chunk_id(batch, source_chunk_id)
                if source_document is None:
                    source_document = fallback_document
                item.setdefault("source_document_id", source_document.get("document_id"))
                item.setdefault("source_chunk_id", source_document.get("chunk_id"))
                item.setdefault("source_section_path", [source_document.get("section_title") or ""])
                item.setdefault(
                    "source_doc",
                    (source_document.get("metadata") or {}).get("source_file_name")
                    or source_document.get("document_id"),
                )
            atoms.extend(normalize_requirement_atoms(chunk_items, documents=None))
            logger.info(
                f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} chunk batch done | "
                f"project_id={request.project_id} | "
                f"batch_index={batch_index} | batch_count={len(batches)} | "
                f"parsed_items={len(chunk_items)} | accumulated_atoms={len(atoms)} | "
                f"actual_llm_calls={llm_call_count}"
            )

        atoms = assign_requirement_ids(deduplicate_requirement_atoms(atoms))
        if not atoms:
            return None
        result = atoms_to_requirement_artifact(
            atoms,
            project_id=request.project_id,
            generated_by=self.AGENT_NAME,
        )
        self._apply_request_metadata(result, request)
        logger.info(
            f"[{self.AGENT_NAME}] chunk fallback done | "
            f"project_id={request.project_id} | "
            f"actual_llm_calls={llm_call_count} | "
            f"runnable_documents={len(runnable_documents)} | "
            f"duration_ms={int((perf_counter() - started_at) * 1000)}"
        )
        return result

    async def _invoke_model_or_fallback(
        self,
        model_invoker: Any,
        **kwargs: Any,
    ) -> str | None:
        try:
            return await model_invoker.invoke_agent_llm(**kwargs)
        except RuntimeError as exc:
            if not self._allows_local_llm_fallback():
                raise
            logger.warning(
                f"[{self.AGENT_NAME}] LLM unavailable in non-production; "
                f"using deterministic fallback | label={kwargs.get('call_label') or 'n/a'} | "
                f"error_type={type(exc).__name__}"
            )
            return None

    def _allows_local_llm_fallback(self) -> bool:
        return str(settings.APP_ENV or "").strip().lower() not in {
            "prod",
            "production",
            "release",
        }

    def _build_table_prompt(
        self,
        request: AgentRequest,
        documents: list[dict[str, Any]],
        table_atoms: list[Any],
    ) -> str:
        context = dict(request.context or {})
        candidates = [
            {
                "requirement_id": atom.requirement_id,
                "category": atom.category,
                "biz_requirement_id": atom.biz_requirement_id,
                "biz_requirement_name": atom.biz_requirement_name,
                "requirement_name": atom.requirement_name or atom.title,
                "requirement_type": atom.requirement_type,
                "domain": atom.domain,
                "feature": atom.feature,
                "description": atom.description,
                "note": atom.rationale,
                "source_document_id": atom.source_document_id,
                "source_chunk_ids": atom.source_chunk_ids,
            }
            for atom in table_atoms
        ]
        source_chunks = [
            {
                "document_id": document.get("document_id"),
                "chunk_id": document.get("chunk_id"),
                "section_title": document.get("section_title"),
                "text": str(document.get("text") or ""),
            }
            for document in documents
        ]
        return f"""
Project ID: {request.project_id}
Context:
{json.dumps(context, ensure_ascii=False, default=str)}

Template mapper summary:
{mapper_summary_for_prompt()}

표 기반 요구사항 후보:
{json.dumps(candidates, ensure_ascii=False, default=str)}

원문 chunk:
{json.dumps(source_chunks, ensure_ascii=False, default=str)}
""".strip()

    def _build_table_batch_prompt(
        self,
        request: AgentRequest,
        batch: list[Any],
        index: int,
        total: int,
    ) -> str:
        context = dict(request.context or {})
        candidates = [
            {
                "requirement_id": atom.requirement_id,
                "category": atom.category,
                "biz_requirement_id": atom.biz_requirement_id,
                "biz_requirement_name": atom.biz_requirement_name,
                "requirement_name": atom.requirement_name or atom.title,
                "requirement_type": atom.requirement_type,
                "domain": atom.domain,
                "feature": atom.feature,
                "description": atom.description,
                "note": atom.rationale,
                "source_document_id": atom.source_document_id,
                "source_chunk_ids": atom.source_chunk_ids,
                "acceptance_criteria": atom.acceptance_criteria,
            }
            for atom in batch
        ]
        return f"""
Project ID: {request.project_id}
batch: {index}/{total}
Context:
{json.dumps(context, ensure_ascii=False, default=str)}

Template mapper summary:
{mapper_summary_for_prompt()}

후보 목록:
{json.dumps(candidates, ensure_ascii=False, default=str)}
""".strip()

    def _build_table_item_prompt(
        self,
        request: AgentRequest,
        atom: Any,
        index: int,
        total: int,
    ) -> str:
        context = dict(request.context or {})
        candidate = {
            "requirement_id": atom.requirement_id,
            "category": atom.category,
            "biz_requirement_id": atom.biz_requirement_id,
            "biz_requirement_name": atom.biz_requirement_name,
            "requirement_name": atom.requirement_name or atom.title,
            "requirement_type": atom.requirement_type,
            "domain": atom.domain,
            "feature": atom.feature,
            "description": atom.description,
            "note": atom.rationale,
            "source_document_id": atom.source_document_id,
            "source_chunk_ids": atom.source_chunk_ids,
            "acceptance_criteria": atom.acceptance_criteria,
        }
        return f"""
Project ID: {request.project_id}
Item: {index}/{total}
Context:
{json.dumps(context, ensure_ascii=False, default=str)}

Candidate:
{json.dumps(candidate, ensure_ascii=False, default=str)}
""".strip()

    def _apply_request_metadata(
        self,
        result: dict[str, Any],
        request: AgentRequest,
    ) -> None:
        result["metadata"] = self._metadata_with_request_context(
            result.get("metadata") or {},
            request,
        )

    def _metadata_with_request_context(
        self,
        metadata: dict[str, Any],
        request: AgentRequest,
    ) -> dict[str, Any]:
        context = request.context or {}
        author = (
            context.get("author")
            or context.get("writer")
            or context.get("created_by")
            or context.get("user_id")
        )
        project_name = context.get("project_name") or context.get("project_nm")
        enriched = {**metadata}
        if author:
            enriched["author"] = str(author)
        if project_name:
            enriched["project_name"] = str(project_name)
        return enriched

    def _build_chunk_prompt(
        self,
        request: AgentRequest,
        document: dict[str, Any],
        index: int,
        total: int,
    ) -> str:
        context = dict(request.context or {})
        metadata = document.get("metadata") or {}
        project_type = (
            context.get("project_type")
            or metadata.get("project_type")
            or "auto"
        )
        return f"""
Project ID: {request.project_id}
프로젝트유형: {project_type}
chunk: {index}/{total}
document_id: {document.get('document_id', '')}
chunk_id: {document.get('chunk_id', '')}
섹션: {document.get('section_title') or ''}
source_file: {metadata.get('source_file_name') or ''}

Template mapper summary:
{mapper_summary_for_prompt()}

내용:
{document.get('text', '')}
""".strip()

    def _build_batch_prompt(
        self,
        request: AgentRequest,
        documents: list[dict[str, Any]],
        index: int,
        total: int,
    ) -> str:
        context = dict(request.context or {})
        source_chunks = []
        for document in documents:
            metadata = document.get("metadata") or {}
            source_chunks.append(
                {
                    "document_id": document.get("document_id", ""),
                    "chunk_id": document.get("chunk_id", ""),
                    "section_title": document.get("section_title") or "",
                    "source_file": metadata.get("source_file_name") or "",
                    "text": str(document.get("text") or "")[: max(settings.GENERATION_REQUIREMENT_SOURCE_TEXT_LIMIT, 200)],
                }
            )
        return f"""
Project ID: {request.project_id}
batch: {index}/{total}
Context:
{json.dumps(context, ensure_ascii=False, default=str)}

Template mapper summary:
{mapper_summary_for_prompt()}

source_chunks:
{json.dumps(source_chunks, ensure_ascii=False, default=str)}
""".strip()

    def _build_source_document_context(
        self,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = {}
        document_order: list[str] = []
        for document in documents:
            document_id = str(document.get("document_id") or "").strip()
            if not document_id:
                continue
            if document_id not in grouped:
                grouped[document_id] = {
                    "document_id": document_id,
                    "document_type": self._document_type_from_metadata(document),
                    "source_file_name": self._document_title_from_metadata(document),
                    "chunk_count": 0,
                    "section_titles": [],
                    "highlights": [],
                }
                document_order.append(document_id)

            summary = grouped[document_id]
            summary["chunk_count"] = int(summary["chunk_count"]) + 1
            section_title = str(document.get("section_title") or "").strip()
            if section_title and section_title not in summary["section_titles"]:
                summary["section_titles"].append(section_title)
            text = str(document.get("text") or "").strip()
            if text:
                highlights = summary["highlights"]
                if len(highlights) < 3:
                    highlights.append(text[:240])

        ordered_documents = [grouped[document_id] for document_id in document_order]
        meeting_note_documents = [
            summary
            for summary in ordered_documents
            if summary["document_type"] == "MEETING_NOTES"
        ]
        construction_documents = [
            summary
            for summary in ordered_documents
            if summary["document_type"] == "CONSTRUCTION_REQUIREMENT_DEFINITION"
        ]
        return {
            "documents": ordered_documents,
            "meeting_notes": meeting_note_documents,
            "construction_requirement_documents": construction_documents,
            "meeting_note_titles": [
                summary["source_file_name"] or summary["document_id"]
                for summary in meeting_note_documents
            ],
        }

    def _document_type_from_metadata(self, document: dict[str, Any]) -> str:
        metadata = document.get("metadata") or {}
        raw_value = (
            metadata.get("document_type")
            or metadata.get("source_document_type")
            or metadata.get("documentType")
            or metadata.get("sourceDocumentType")
            or ""
        )
        return str(raw_value).upper() or "UNKNOWN"

    def _document_title_from_metadata(self, document: dict[str, Any]) -> str:
        metadata = document.get("metadata") or {}
        return str(
            metadata.get("source_file_name")
            or metadata.get("document_file_name")
            or metadata.get("file_name")
            or document.get("section_title")
            or document.get("document_id")
            or "",
        ).strip()

    def _document_by_chunk_id(
        self,
        documents: list[dict[str, Any]],
        chunk_id: Any,
    ) -> dict[str, Any] | None:
        if not chunk_id:
            return None
        for document in documents:
            if str(document.get("chunk_id") or "") == str(chunk_id):
                return document
        return None

    def _parse_table_batch_response(self, llm_result: str) -> list[dict[str, Any]]:
        parsed_items = parse_json_array(llm_result)
        if parsed_items:
            return parsed_items

        parsed_obj = parse_json_object(llm_result)
        if not parsed_obj:
            return []
        if isinstance(parsed_obj.get("requirements"), list):
            return [item for item in parsed_obj["requirements"] if isinstance(item, dict)]
        return [parsed_obj]

    def _merge_table_atom_with_result(
        self,
        atom: Any,
        parsed_item: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = self._table_atom_fallback_payload(atom)
        if not parsed_item:
            return payload
        payload.update(
            {
                "category": parsed_item.get("category") or payload["category"],
                "biz_requirement_id": parsed_item.get("biz_requirement_id")
                or payload["biz_requirement_id"],
                "biz_requirement_name": parsed_item.get("biz_requirement_name")
                or payload["biz_requirement_name"],
                "title": parsed_item.get("requirement_name")
                or parsed_item.get("title")
                or payload["title"],
                "description": parsed_item.get("description") or payload["description"],
                "requirement_type": parsed_item.get("requirement_type")
                or payload["requirement_type"],
                "domain": parsed_item.get("domain") or payload["domain"],
                "feature": parsed_item.get("feature") or payload["feature"],
                "note": parsed_item.get("note") or payload["note"],
                "acceptance_criteria": parsed_item.get("acceptance_criteria")
                or payload["acceptance_criteria"],
            }
        )
        return payload

    def _table_atom_fallback_payload(self, atom: Any) -> dict[str, Any]:
        return {
            "requirement_id": atom.requirement_id,
            "title": atom.title,
            "description": atom.description,
            "priority": atom.priority,
            "source_document_id": atom.source_document_id,
            "source_chunk_ids": atom.source_chunk_ids,
            "source_doc": atom.metadata.get("source_doc")
            or atom.metadata.get("source_file_name")
            or atom.source_document_id,
            "source_file_name": atom.metadata.get("source_file_name")
            or atom.metadata.get("source_doc")
            or atom.source_document_id,
            "acceptance_criteria": atom.acceptance_criteria,
            "rationale": atom.rationale,
            "category": atom.category,
            "requirement_type": atom.requirement_type,
            "biz_requirement_id": atom.biz_requirement_id,
            "biz_requirement_name": atom.biz_requirement_name,
            "domain": atom.domain,
            "feature": atom.feature,
            "note": atom.rationale,
        }


requirement_agent = RequirementAgent()
