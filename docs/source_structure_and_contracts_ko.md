# FINPM 소스 구조와 인터페이스 및 계약 규칙

FINPM 백엔드는 JSON 중심의 PM Agent 아키텍처로 구성되어 있습니다.
현재 소스 구조는 아래 흐름으로 설명하는 것이 가장 이해하기 쉽습니다.

```text
Frontend
-> FastAPI Router
-> Service
-> Orchestrator
-> Input/Core/Output Agent
-> Validator
-> Repository / Storage / DB
```

핵심 규칙은 다음과 같습니다.

```text
Agent는 구조화된 JSON을 처리한다.
Router는 HTTP를 처리한다.
Service는 유스케이스를 처리한다.
Orchestrator는 전체 흐름을 제어한다.
Repository는 DB 접근을 담당한다.
```

## 1. 현재 소스 구조

```text
backend/app/
  main.py                 FastAPI 앱, 라우터 등록, 공통 예외 처리
  dependencies.py         FastAPI 의존성 주입 팩토리

  api/                    HTTP API 라우터
  services/               비즈니스/유스케이스 서비스
  orchestrator/           흐름 제어와 context 조립

  agents/
    input_agents/         외부 입력을 내부 JSON으로 변환
    core_agents/          PM 산출물 JSON 생성 및 검증
    output_agents/        내부 JSON을 API/UI/export payload로 변환

  schemas/                Pydantic 요청/응답/Agent/Artifact 계약
  repositories/           DB 접근 계층
  models/                 SQLAlchemy ORM 모델
  rag/                    검색/RAG 경계
  storage/                S3/file storage 경계
  core/                   설정, 로거, LLM wrapper, 예외
```

중요 파일:

```text
backend/app/main.py
backend/app/dependencies.py
backend/app/api/generation.py
backend/app/orchestrator/generation_orchestrator.py
backend/app/agents/AGENT_DEVELOPMENT.md
backend/app/schemas/
```

## 2. 책임 분리

### Router 계층

위치:

```text
backend/app/api/
```

Router는 HTTP 요청을 받고 API 응답을 반환합니다.

Router가 할 수 있는 일:

```text
- Pydantic schema를 통한 request body 검증
- 필수 요청 값 확인
- Service 호출
- HTTP 수준 실패에 대한 ApiError 발생
- OutputOrchestrator를 통한 최종 응답 포맷 정리
```

Router가 하면 안 되는 일:

```text
- LLM 직접 호출
- DB 직접 접근
- S3 직접 접근
- Vector Store 직접 접근
- Agent 로직 구현
```

예시 API:

```text
POST /generate/requirement
POST /generate/wbs
POST /generate/screen-design
```

구현 위치:

```text
backend/app/api/generation.py
```

### Service 계층

위치:

```text
backend/app/services/
```

Service는 Router와 내부 처리 로직 사이의 안정적인 유스케이스 경계입니다.

예시:

```text
GenerationService   -> 산출물 생성 요청을 GenerationOrchestrator로 위임
DocumentService     -> 문서 업로드, 조회, ingestion 조정
ArtifactService     -> 생성 산출물 저장 및 조회
ScheduleService     -> 일정/todo 추출 흐름 위임
TemplateService     -> 생성 템플릿 resolve
TraceabilityService -> artifact link 관리
```

Service는 Repository 또는 Orchestrator를 사용할 수 있습니다.
Agent는 Repository를 직접 사용하면 안 됩니다.

### Orchestrator 계층

위치:

```text
backend/app/orchestrator/
```

Orchestrator는 flow control, context assembly, validation, post-processing을 담당합니다.

주요 생성 흐름:

```text
GenerationRequest
-> generation flow resolve
-> template resolve
-> project-scoped document chunks 검색
-> AgentRequest 생성
-> ArtifactAgent 호출
-> AgentResponse.result 검증
-> Artifact 저장
-> GenerationResponse 반환
```

구현 위치:

```text
backend/app/orchestrator/generation_orchestrator.py
```

중요 규칙:

```text
Vector/search context에는 항상 project_id와 permission_scope가 포함되어야 한다.
```

현재 retrieval 호출:

```python
documents = await retrieval.search(
    project_id=request.project_id,
    permission_scope=request.permission_scope,
    query=request.query or "",
)
```

### Agent 계층

위치:

```text
backend/app/agents/
```

Agent는 세 종류입니다.

```text
Input Agent:
  Raw user/file input -> normalized FINPM internal JSON

Core Agent:
  Structured JSON/context -> PM artifact JSON

Output Agent:
  Internal result JSON -> user-facing API/display/export payload
```

현재 구현된 Agent:

```text
Input:
  DocumentParserAgent

Core:
  ArtifactAgent
  RequirementAgent
  ValidatorAgent

Output:
  MarkdownOutputAgent
```

현재 placeholder adapter:

```text
WbsAgent
ScreenDesignAgent
ScheduleManagementAgent
```

즉, 라우트와 계약은 존재하지만 WBS, 화면설계, 일정/todo 생성 Agent의 실제 구현은 아직 필요합니다.

### Repository 계층

위치:

```text
backend/app/repositories/
```

Repository는 DB persistence query를 직접 다루는 계층입니다.

예시:

```text
DocumentRepository      -> 문서와 문서 chunk
ArtifactRepository      -> 산출물, 버전, source document link
ArtifactLinkRepository  -> traceability link
TemplateRepository      -> template
```

의도된 호출 경로:

```text
Router -> Service -> Repository -> SQLAlchemy Model
```

금지되는 경로:

```text
Router -> Repository
Agent -> Repository
Agent -> DB
```

## 3. 데이터 흐름

### 요구사항 생성

```text
POST /generate/requirement
-> generation.py
-> _validate_source_documents()
-> InputOrchestrator.normalize()
-> GenerationService.generate_artifact()
-> GenerationOrchestrator.generate_artifact()
-> RetrievalService.search()
-> ArtifactAgent.generate()
-> RequirementAgent.generate()
-> ValidatorAgent.validate()
-> ArtifactService.create_artifact()
-> OutputOrchestrator.format()
-> GenerationResponse
```

### WBS 생성

```text
POST /generate/wbs
-> source document type이 REQUIREMENT_SPEC인지 검증
-> target_artifact_type = WBS
-> 동일한 GenerationService / GenerationOrchestrator 경로 사용
-> ArtifactAgent가 WbsAgent로 dispatch
```

현재 상태:

```text
WbsAgent는 placeholder이며 success=False를 반환한다.
```

### 화면설계 생성

```text
POST /generate/screen-design
-> source document type이 REQUIREMENT_SPEC인지 검증
-> target_artifact_type = SCREEN_DESIGN
-> 동일한 GenerationService / GenerationOrchestrator 경로 사용
-> ArtifactAgent가 ScreenDesignAgent로 dispatch
```

현재 상태:

```text
ScreenDesignAgent는 placeholder이며 success=False를 반환한다.
```

### 일정 Todo 추출

```text
POST /schedule/todos
-> InputOrchestrator.normalize(MEETING_NOTES)
-> ScheduleService.extract_todos()
-> ScheduleOrchestrator.extract_todos()
-> ScheduleManagementAgent.generate()
-> ValidatorAgent.validate()
-> OutputOrchestrator.format()
```

현재 상태:

```text
ScheduleManagementAgent는 placeholder이며 success=False를 반환한다.
```

## 4. API Request 계약

주요 생성 요청:

```python
class GenerationRequest(BaseModel):
    project_id: str
    source_document_ids: list[str]
    document_ids: list[str]
    source_document_type: DocumentType | None
    target_artifact_type: ArtifactType
    template_id: str | None
    template_version: str | None
    query: str | None
    permission_scope: list[str]
```

호환성 관련 중요 사항:

```text
document_ids는 source_document_ids의 deprecated alias다.
model validator가 두 필드를 동기화한다.
```

일정 요청:

```python
class ScheduleTodoRequest(BaseModel):
    project_id: str
    meeting_notes: str
    source_document_ids: list[str]
    user_id: str | None
    permission_scope: list[str]
```

## 5. 공통 Enum 계약

Document types:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION
REQUIREMENT_SPEC
MEETING_NOTES
UNKNOWN
```

Artifact types:

```text
REQUIREMENT_SPEC
SCREEN_DESIGN
WBS
ACTION_ITEMS
```

Document statuses:

```text
UPLOADED
PARSED
INDEXED
FAILED
```

Artifact statuses:

```text
CREATED
VALIDATED
EXPORTED
FAILED
```

## 6. Agent 인터페이스 계약

모든 Core Agent는 아래 입력을 받습니다.

```python
class AgentRequest(BaseModel):
    project_id: str
    documents: list[dict]
    context: dict | None
```

모든 Core Agent는 아래 응답을 반환합니다.

```python
class AgentResponse(BaseModel):
    success: bool = True
    agent_name: str
    result: Any = None
    error: str | None = None
```

실패 응답 예시:

```python
return AgentResponse(
    success=False,
    agent_name="WbsAgent",
    error="WBS generation agent is not implemented yet",
)
```

Core Agent는 일반적인 생성 실패 상황에서 사용자-facing HTTP error를 직접 raise하지 않습니다.
대신 `AgentResponse(success=False, error="...")` 형태로 반환합니다.

## 7. Core Agent 규칙

Core Agent가 해야 하는 일:

```text
- 구조화된 JSON-like input 처리
- 구조화된 JSON-like output 반환
- AgentRequest와 AgentResponse 사용
- LLM 호출 시 app.core.llm.llm_service 사용
- 생성 산출물에 안정적인 item ID 포함
```

Core Agent가 하면 안 되는 일:

```text
- DB 직접 접근
- S3 직접 접근
- Repository 직접 접근
- Vector Store 직접 접근
- FastAPI Response 객체 생성
- HTTP routing logic 수행
- Bedrock/boto3 직접 호출
```

LLM 접근은 반드시 아래 wrapper를 통해야 합니다.

```text
backend/app/core/llm.py
```

현재 상태:

```text
LLMService는 아직 mock wrapper다.
실제 Bedrock invocation은 TODO 상태다.
```

## 8. Core Agent 입력 형태

GenerationOrchestrator는 다음과 같은 형태의 AgentRequest를 생성합니다.

```python
AgentRequest(
    project_id=request.project_id,
    documents=documents,
    context={
        "source_document_ids": request.source_document_ids,
        "document_ids": request.document_ids,
        "source_document_type": "REQUIREMENT_SPEC",
        "target_artifact_type": "WBS",
        "template": template_context,
        "query": request.query,
        "permission_scope": request.permission_scope,
    },
)
```

Agent는 `documents`와 `context`를 읽을 수 있습니다.
하지만 retrieval을 다시 호출하면 안 됩니다.

## 9. Validation 계약

생성 결과는 아래 Validator가 검증합니다.

```text
backend/app/agents/core_agents/validator_agent/agent.py
```

Validator는 result key를 기준으로 schema를 선택합니다.

```text
requirements -> RequirementArtifact
tasks        -> WbsArtifact
screens      -> ScreenDesignArtifact
todos        -> ScheduleTodoList
```

최소 Requirement artifact:

```json
{
  "artifact_type": "REQUIREMENT_SPEC",
  "requirements": [
    {
      "requirement_id": "RQ-001",
      "title": "Login",
      "description": "User can log in.",
      "priority": "SHOULD",
      "source_document_id": "DOC-001",
      "source_chunk_ids": ["CHUNK-001"],
      "acceptance_criteria": ["Login succeeds with valid credentials."],
      "rationale": "Derived from source document."
    }
  ],
  "metadata": {}
}
```

최소 WBS artifact:

```json
{
  "artifact_type": "WBS",
  "tasks": [
    {
      "task_id": "WBS-001",
      "name": "Build login",
      "description": "Optional",
      "source_requirement_ids": ["RQ-001"],
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

최소 Screen Design artifact:

```json
{
  "artifact_type": "SCREEN_DESIGN",
  "screens": [
    {
      "screen_id": "SCR-001",
      "name": "Login screen",
      "description": "Optional",
      "source_requirement_ids": ["RQ-001"],
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

최소 Schedule Todo artifact:

```json
{
  "artifact_type": "SCHEDULE_TODO_LIST",
  "todos": [
    {
      "todo_id": "TODO-001",
      "title": "Confirm login scope",
      "description": "Optional",
      "assignee": "Optional",
      "due_date": "2026-06-07",
      "source_document_id": "DOC-001",
      "source_chunk_ids": ["CHUNK-001"],
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

## 10. Retrieval 계약

현재 retrieval 경계:

```text
backend/app/rag/retrieval.py
```

현재 구현:

```text
MVP용 stored document chunk keyword search.
```

향후 교체 대상:

```text
OpenSearch 또는 pgvector similarity search.
```

유지해야 하는 stable contract:

```python
async def search(
    project_id: str,
    permission_scope: list[str],
    query: str,
    top_k: int = 5,
) -> list[dict]:
    ...
```

필수 규칙:

```text
Search는 반드시 project-scoped여야 한다.
Search는 반드시 permission_scope를 확인해야 한다.
```

현재 권한 동작:

```text
permission_scope에 "project:read"가 없으면 []를 반환한다.
```

## 11. Template 계약

Agent는 template을 직접 load하지 않습니다.

Orchestrator가 TemplateService를 통해 template을 resolve한 뒤 아래 위치로 전달합니다.

```text
AgentRequest.context["template"]
```

Agent는 template content를 read-only generation guidance로 취급해야 합니다.

## 12. Traceability 계약

Traceability는 artifact link로 표현됩니다.

관련 파일:

```text
backend/app/models/artifact_link.py
backend/app/schemas/traceability.py
backend/app/services/traceability_service.py
backend/app/repositories/artifact_link_repository.py
```

활성 relation types:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
DERIVED_FROM

REQUIREMENT_SPEC -> WBS
DECOMPOSED_TO

REQUIREMENT_SPEC -> SCREEN_DESIGN
DESIGNED_BY
```

Agent 출력에는 link 생성을 위해 안정적인 ID가 포함되어야 합니다.

```text
Requirement:   requirement_id
WBS:           task_id
Screen Design: screen_id
```

## 13. 현재 MVP 범위

활성 target flow:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
REQUIREMENT_SPEC -> WBS
REQUIREMENT_SPEC -> SCREEN_DESIGN
MEETING_NOTES -> SCHEDULE_TODO_LIST
```

현재 구현 상태:

```text
Requirement generation:
  RequirementAgent와 mock LLM fallback 동작이 구현되어 있다.

WBS generation:
  API와 orchestration은 존재한다.
  WbsAgent는 아직 placeholder다.

Screen design generation:
  API와 orchestration은 존재한다.
  ScreenDesignAgent는 아직 placeholder다.

Schedule todo extraction:
  API와 orchestration은 존재한다.
  ScheduleManagementAgent는 아직 placeholder다.

Real Bedrock:
  LLMService wrapper는 존재한다.
  실제 Bedrock 호출은 TODO다.

Vector search:
  RetrievalService boundary는 존재한다.
  현재 검색은 keyword 기반 DB chunk search다.
  pgvector/OpenSearch 연동은 TODO다.
```

## 14. 팀 공통 규칙 요약

코드베이스 설명 시 아래 규칙을 중심으로 이야기하면 됩니다.

```text
1. JSON이 내부 계약이다.
2. Core Agent는 구조화된 JSON만 처리한다.
3. Input Agent는 외부/raw 입력을 내부 JSON으로 변환한다.
4. Output Agent는 내부 JSON을 사용자-facing payload로 변환한다.
5. Orchestrator는 flow, context assembly, validation, post-processing을 제어한다.
6. Router는 LLM을 직접 호출하지 않는다.
7. Router는 DB에 직접 접근하지 않는다.
8. Agent는 DB, S3, Repository, Vector Store에 직접 접근하지 않는다.
9. Service와 Repository가 persistence boundary를 담당한다.
10. LLM output은 저장 또는 응답 전에 반드시 검증한다.
11. Retrieval에는 project_id와 permission_scope가 반드시 포함되어야 한다.
12. MVP first, extensible later 원칙을 따른다.
```

## 15. 한 문장 요약

FINPM 백엔드는 JSON 중심의 PM Agent 플랫폼이며, FastAPI Router는 HTTP
계약을 담당하고, Service는 유스케이스를 제공하며, Orchestrator는 Agent
workflow를 제어하고, Agent는 구조화된 JSON을 생성/변환하며, Validator는
산출물 계약을 검증하고, Repository는 DB 접근을 담당합니다.
