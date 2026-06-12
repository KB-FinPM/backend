# EN: Core agent for generating requirement artifacts from structured context.
# KO: 구조화된 컨텍스트를 기반으로 요구사항 산출물을 생성하는 Core Agent입니다.

import json
from typing import Any

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
- 기능 구현과 직접 관련 있으면 기능요구사항으로 분류한다.
- 성능, 보안, 권한, 로그, 접근성, 운영, 백업, 장애대응은 비기능요구사항으로 분류한다.
- 한 번의 응답에서 최대 10개 요구사항만 추출한다.
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

    async def generate(self, request: AgentRequest) -> AgentResponse:
        logger.info(f"[{self.AGENT_NAME}] generate start | project_id={request.project_id}")

        try:
            result = await self._generate_with_orchestrator(request)
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

            logger.info(f"[{self.AGENT_NAME}] generate done")
            return AgentResponse(agent_name=self.AGENT_NAME, result=result)

        except Exception as exc:
            logger.error(f"[{self.AGENT_NAME}] error: {exc}")
            return AgentResponse(success=False, agent_name=self.AGENT_NAME, error=str(exc))

    async def _generate_with_orchestrator(
        self,
        request: AgentRequest,
    ) -> dict[str, Any] | None:
        orchestrator = (request.context or {}).get("generation_orchestrator")
        if orchestrator is None or not hasattr(orchestrator, "invoke_agent_llm"):
            logger.info(
                f"[{self.AGENT_NAME}] orchestrator unavailable | "
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

        logger.info(
            f"[{self.AGENT_NAME}] orchestrator path start | "
            f"project_id={request.project_id} | document_count={len(documents)}"
        )

        # 1) Existing 구축요건정의서 files often already contain structured
        # requirement tables. Extract deterministic candidates first, then send
        # them through the orchestrator LLM boundary so the Bedrock path and
        # logging are exercised consistently.
        table_atoms = orchestrator.extract_requirement_atoms_from_pipe_tables(documents)
        logger.info(
            f"[{self.AGENT_NAME}] table extraction result | "
            f"project_id={request.project_id} | table_atom_count={len(table_atoms)}"
        )
        if table_atoms:
            logger.info(
                f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} table path -> LLM | "
                f"project_id={request.project_id} | candidate_count={len(table_atoms)}"
            )
            chunk_items = []
            for index, atom in enumerate(table_atoms, start=1):
                prompt = self._build_table_item_prompt(request, atom, index, len(table_atoms))
                llm_result = await orchestrator.invoke_agent_llm(
                    system_prompt=TABLE_REFINEMENT_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    max_tokens=1800,
                )
                parsed_obj = parse_json_object(llm_result)
                parsed_items = parse_json_array(llm_result)
                parsed_item: dict[str, Any] | None = None
                if parsed_obj:
                    parsed_item = parsed_obj
                elif parsed_items:
                    parsed_item = parsed_items[0]

                if parsed_item is None:
                    chunk_items.append(
                        {
                            "requirement_id": atom.requirement_id,
                            "title": atom.title,
                            "description": atom.description,
                            "priority": atom.priority,
                            "source_document_id": atom.source_document_id,
                            "source_chunk_ids": atom.source_chunk_ids,
                            "source_doc": atom.metadata.get("source_doc") or atom.metadata.get("source_file_name") or atom.source_document_id,
                            "source_file_name": atom.metadata.get("source_file_name") or atom.metadata.get("source_doc") or atom.source_document_id,
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
                    )
                    continue

                parsed_item.setdefault("requirement_id", atom.requirement_id)
                parsed_item.setdefault("title", atom.title)
                parsed_item.setdefault("description", atom.description)
                parsed_item.setdefault("priority", atom.priority)
                parsed_item.setdefault("source_document_id", atom.source_document_id)
                parsed_item.setdefault("source_chunk_ids", atom.source_chunk_ids)
                parsed_item.setdefault("source_doc", atom.metadata.get("source_doc") or atom.metadata.get("source_file_name") or atom.source_document_id)
                parsed_item.setdefault("source_file_name", atom.metadata.get("source_file_name") or atom.metadata.get("source_doc") or atom.source_document_id)
                parsed_item.setdefault("acceptance_criteria", atom.acceptance_criteria)
                parsed_item.setdefault("rationale", atom.rationale)
                parsed_item.setdefault("category", atom.category)
                parsed_item.setdefault("requirement_type", atom.requirement_type)
                parsed_item.setdefault("biz_requirement_id", atom.biz_requirement_id)
                parsed_item.setdefault("biz_requirement_name", atom.biz_requirement_name)
                parsed_item.setdefault("domain", atom.domain)
                parsed_item.setdefault("feature", atom.feature)
                parsed_item.setdefault("note", atom.rationale)
                chunk_items.append(parsed_item)

            atoms = normalize_requirement_atoms(chunk_items, documents=None) if chunk_items else table_atoms
            atoms = assign_requirement_ids(deduplicate_requirement_atoms(atoms))
            result = atoms_to_requirement_artifact(
                atoms,
                project_id=request.project_id,
                generated_by=self.AGENT_NAME,
            )
            self._apply_request_metadata(result, request)
            return result

        # 2) Fallback to sample_0605 chunk-by-chunk LLM extraction when no
        # source requirement table is detected.
        logger.info(
            f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} chunk fallback path -> LLM | "
            f"project_id={request.project_id}"
        )
        atoms = []
        for idx, document in enumerate(documents, start=1):
            text = str(document.get("text") or "").strip()
            if not text:
                continue
            logger.info(
                f"[{self.AGENT_NAME}] {LLM_LOG_PREFIX} chunk LLM request | "
                f"project_id={request.project_id} | "
                f"chunk_index={idx} | chunk_id={document.get('chunk_id')} | "
                f"text_chars={len(text)}"
            )
            prompt = self._build_chunk_prompt(request, document, idx, len(documents))
            llm_result = await orchestrator.invoke_agent_llm(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=6000,
            )
            chunk_items = parse_json_array(llm_result)
            if not chunk_items:
                parsed_obj = parse_json_object(llm_result)
                if parsed_obj and isinstance(parsed_obj.get("requirements"), list):
                    chunk_items = [
                        item for item in parsed_obj["requirements"] if isinstance(item, dict)
                    ]
            for item in chunk_items:
                item.setdefault("source_document_id", document.get("document_id"))
                item.setdefault("source_chunk_id", document.get("chunk_id"))
                item.setdefault("source_section_path", [document.get("section_title") or ""])
                item.setdefault("source_doc", (document.get("metadata") or {}).get("source_file_name") or document.get("document_id"))
            atoms.extend(normalize_requirement_atoms(chunk_items, documents=None))

        atoms = assign_requirement_ids(deduplicate_requirement_atoms(atoms))
        if not atoms:
            return None
        result = atoms_to_requirement_artifact(
            atoms,
            project_id=request.project_id,
            generated_by=self.AGENT_NAME,
        )
        self._apply_request_metadata(result, request)
        return result

    def _build_table_prompt(
        self,
        request: AgentRequest,
        documents: list[dict[str, Any]],
        table_atoms: list[Any],
    ) -> str:
        context = {
            key: value
            for key, value in (request.context or {}).items()
            if key != "generation_orchestrator"
        }
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
                "text": str(document.get("text") or "")[:2000],
            }
            for document in documents[:20]
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

    def _build_table_item_prompt(
        self,
        request: AgentRequest,
        atom: Any,
        index: int,
        total: int,
    ) -> str:
        context = {
            key: value
            for key, value in (request.context or {}).items()
            if key != "generation_orchestrator"
        }
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
        context = {
            key: value
            for key, value in (request.context or {}).items()
            if key != "generation_orchestrator"
        }
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


requirement_agent = RequirementAgent()
