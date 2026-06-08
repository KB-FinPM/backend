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
    extract_requirement_atoms_from_pipe_tables,
    normalize_requirement_atoms,
    parse_json_array,
    parse_json_object,
)
from util.agent_template_utils import mapper_summary_for_prompt

logger = get_logger(__name__)


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
- 인프라 구축 프로젝트에서는 OCP, Kafka, EFK, CDC, API Gateway, Service Mesh, Monitoring, Logging, DB, 보안, 백업 등을 Biz요건명 후보로 본다.
- 개발 프로젝트에서는 업무, 화면, 기능, 인터페이스, 데이터, 권한, 배치 등을 Biz요건명 후보로 본다.
- 기능 구현과 직접 관련 있으면 기능요구사항으로 분류한다.
- 성능, 보안, 권한, 로그, 접근성, 운영, 백업, 장애대응은 비기능요구사항으로 분류한다.
- 한 번의 응답에서 최대 10개 요구사항만 추출한다.
- 각 description은 120자 이내로 요약한다.
- note는 50자 이내로 작성한다.
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
            return None

        documents = normalize_requirement_documents(request.documents)
        if not documents:
            return None

        # 1) Existing 구축요건정의서 files often already contain structured
        # requirement tables. Preserve those rows and IDs first; this matches
        # the pre-merge output much more closely than summarizing through LLM.
        table_atoms = extract_requirement_atoms_from_pipe_tables(documents)
        if table_atoms:
            atoms = assign_requirement_ids(deduplicate_requirement_atoms(table_atoms))
            return atoms_to_requirement_artifact(
                atoms,
                project_id=request.project_id,
                generated_by=self.AGENT_NAME,
            )

        # 2) Fallback to sample_0605 chunk-by-chunk LLM extraction when no
        # source requirement table is detected.
        atoms = []
        for idx, document in enumerate(documents, start=1):
            text = str(document.get("text") or "").strip()
            if not text:
                continue
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
        return atoms_to_requirement_artifact(
            atoms,
            project_id=request.project_id,
            generated_by=self.AGENT_NAME,
        )

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
