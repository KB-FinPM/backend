# FINPM Source Structure And Contract Rules

FINPM backend is organized around a JSON-centric PM Agent architecture.
The easiest way to explain the current source is:

```text
Frontend
-> FastAPI Router
-> Service
-> Orchestrator
-> Input/Core/Output Agent
-> Validator
-> Repository / Storage / DB
```

The core rule is:

```text
Agents process structured JSON.
Routers handle HTTP.
Services handle use cases.
Orchestrators control flow.
Repositories access DB.
```

## 1. Current Source Structure

```text
backend/app/
  main.py                 FastAPI app, router registration, common exception handling
  dependencies.py         FastAPI dependency injection factories

  api/                    HTTP API routers
  services/               Business/use-case services
  orchestrator/           Flow control and context assembly

  agents/
    input_agents/         Convert raw input into internal JSON
    core_agents/          Generate and validate PM artifact JSON
    output_agents/        Convert internal JSON into API/UI/export payloads

  schemas/                Pydantic request/response/agent/artifact contracts
  repositories/           DB access layer
  models/                 SQLAlchemy ORM models
  rag/                    Retrieval/search boundary
  storage/                S3/file storage boundary
  core/                   Config, logger, LLM wrapper, exceptions
```

Important files:

```text
backend/app/main.py
backend/app/dependencies.py
backend/app/api/generation.py
backend/app/orchestrator/generation_orchestrator.py
backend/app/agents/AGENT_DEVELOPMENT.md
backend/app/schemas/
```

## 2. Responsibility Separation

### Router Layer

Location:

```text
backend/app/api/
```

Routers receive HTTP requests and return API responses.

Routers can:

```text
- Validate request body through Pydantic schemas
- Check required request fields
- Call Services
- Raise ApiError for HTTP-level failures
- Format final API response through OutputOrchestrator
```

Routers must not:

```text
- Call LLM directly
- Access DB directly
- Access S3 directly
- Access vector store directly
- Implement Agent logic
```

Example:

```text
POST /generate/requirement
POST /generate/wbs
POST /generate/screen-design
```

These are implemented in:

```text
backend/app/api/generation.py
```

### Service Layer

Location:

```text
backend/app/services/
```

Services are stable use-case boundaries between routers and deeper backend logic.

Examples:

```text
GenerationService   -> delegates artifact generation to GenerationOrchestrator
DocumentService     -> coordinates document upload, lookup, ingestion
ArtifactService     -> creates and reads generated artifacts
ScheduleService     -> delegates schedule/todo extraction
TemplateService     -> resolves generation templates
TraceabilityService -> manages artifact links
```

Services may use repositories or orchestrators.
Agents should not use repositories directly.

### Orchestrator Layer

Location:

```text
backend/app/orchestrator/
```

Orchestrators own flow control, context assembly, validation, and post-processing.

The main generation flow is:

```text
GenerationRequest
-> resolve generation flow
-> resolve template
-> retrieve project-scoped document chunks
-> build AgentRequest
-> call ArtifactAgent
-> validate AgentResponse.result
-> persist Artifact
-> return GenerationResponse
```

Implemented in:

```text
backend/app/orchestrator/generation_orchestrator.py
```

Important rule:

```text
Vector/search context must always include project_id and permission_scope.
```

Current retrieval call:

```python
documents = await retrieval.search(
    project_id=request.project_id,
    permission_scope=request.permission_scope,
    query=request.query or "",
)
```

### Agent Layer

Location:

```text
backend/app/agents/
```

There are three agent types.

```text
Input Agent:
  Raw user/file input -> normalized FINPM internal JSON

Core Agent:
  Structured JSON/context -> PM artifact JSON

Output Agent:
  Internal result JSON -> user-facing API/display/export payload
```

Current implementations:

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

Current placeholder adapters:

```text
WbsAgent
ScreenDesignAgent
ScheduleManagementAgent
```

This means the routes and contracts exist, but the real WBS, screen design, and
schedule/todo generation agents still need implementation.

### Repository Layer

Location:

```text
backend/app/repositories/
```

Repositories are the only layer that should directly handle DB persistence
queries.

Examples:

```text
DocumentRepository      -> documents and document chunks
ArtifactRepository      -> artifacts, versions, source document links
ArtifactLinkRepository  -> traceability links
TemplateRepository      -> templates
```

The intended path is:

```text
Router -> Service -> Repository -> SQLAlchemy Model
```

Not:

```text
Router -> Repository
Agent -> Repository
Agent -> DB
```

## 3. Data Flow

### Requirement Generation

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

### WBS Generation

```text
POST /generate/wbs
-> validates source document type REQUIREMENT_SPEC
-> target_artifact_type = WBS
-> same GenerationService / GenerationOrchestrator path
-> ArtifactAgent dispatches to WbsAgent
```

Current status:

```text
WbsAgent is a placeholder and returns success=False.
```

### Screen Design Generation

```text
POST /generate/screen-design
-> validates source document type REQUIREMENT_SPEC
-> target_artifact_type = SCREEN_DESIGN
-> same GenerationService / GenerationOrchestrator path
-> ArtifactAgent dispatches to ScreenDesignAgent
```

Current status:

```text
ScreenDesignAgent is a placeholder and returns success=False.
```

### Schedule Todo Extraction

```text
POST /schedule/todos
-> InputOrchestrator.normalize(MEETING_NOTES)
-> ScheduleService.extract_todos()
-> ScheduleOrchestrator.extract_todos()
-> ScheduleManagementAgent.generate()
-> ValidatorAgent.validate()
-> OutputOrchestrator.format()
```

Current status:

```text
ScheduleManagementAgent is a placeholder and returns success=False.
```

## 4. API Request Contracts

Main generation request:

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

Important compatibility detail:

```text
document_ids is a deprecated alias for source_document_ids.
The model validator syncs both fields.
```

Schedule request:

```python
class ScheduleTodoRequest(BaseModel):
    project_id: str
    meeting_notes: str
    source_document_ids: list[str]
    user_id: str | None
    permission_scope: list[str]
```

## 5. Shared Enum Contracts

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

## 6. Agent Interface Contract

All Core Agents receive:

```python
class AgentRequest(BaseModel):
    project_id: str
    documents: list[dict]
    context: dict | None
```

All Core Agents return:

```python
class AgentResponse(BaseModel):
    success: bool = True
    agent_name: str
    result: Any = None
    error: str | None = None
```

Expected failure style:

```python
return AgentResponse(
    success=False,
    agent_name="WbsAgent",
    error="WBS generation agent is not implemented yet",
)
```

Core Agents should not raise user-facing HTTP errors for normal generation
failures. They should return `AgentResponse(success=False, error="...")`.

## 7. Core Agent Rules

Core Agents must:

```text
- Process structured JSON-like input only
- Return structured JSON-like output only
- Use AgentRequest and AgentResponse
- Use app.core.llm.llm_service for LLM calls
- Include stable item IDs in generated artifacts
```

Core Agents must not:

```text
- Access DB directly
- Access S3 directly
- Access repositories directly
- Access vector stores directly
- Create FastAPI Response objects
- Perform HTTP routing logic
- Call Bedrock/boto3 directly
```

LLM access must go through:

```text
backend/app/core/llm.py
```

Current status:

```text
LLMService is still a mock wrapper.
Real Bedrock invocation is marked TODO.
```

## 8. Core Agent Input Shape

The GenerationOrchestrator builds an AgentRequest like this:

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

Agents may read `documents` and `context`, but must not call retrieval again.

## 9. Validation Contract

Generated results are validated by:

```text
backend/app/agents/core_agents/validator_agent/agent.py
```

The validator selects schema by result keys:

```text
requirements -> RequirementArtifact
tasks        -> WbsArtifact
screens      -> ScreenDesignArtifact
todos        -> ScheduleTodoList
```

Minimum Requirement artifact:

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

Minimum WBS artifact:

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

Minimum Screen Design artifact:

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

Minimum Schedule Todo artifact:

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

## 10. Retrieval Contract

Current retrieval boundary:

```text
backend/app/rag/retrieval.py
```

Current implementation:

```text
MVP keyword search over stored document chunks.
```

Future replacement:

```text
OpenSearch or pgvector similarity search.
```

Stable contract:

```python
async def search(
    project_id: str,
    permission_scope: list[str],
    query: str,
    top_k: int = 5,
) -> list[dict]:
    ...
```

Mandatory rule:

```text
Search must be project-scoped.
Search must check permission_scope.
```

Current permission behavior:

```text
If "project:read" is not included in permission_scope, return [].
```

## 11. Template Contract

Agents do not load templates.

The orchestrator resolves templates through TemplateService and passes the
resolved template into:

```text
AgentRequest.context["template"]
```

Agents should treat template content as read-only generation guidance.

## 12. Traceability Contract

Traceability is represented by artifact links.

Related files:

```text
backend/app/models/artifact_link.py
backend/app/schemas/traceability.py
backend/app/services/traceability_service.py
backend/app/repositories/artifact_link_repository.py
```

Active relation types:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
DERIVED_FROM

REQUIREMENT_SPEC -> WBS
DECOMPOSED_TO

REQUIREMENT_SPEC -> SCREEN_DESIGN
DESIGNED_BY
```

Agent outputs should include stable IDs so links can be created:

```text
Requirement:   requirement_id
WBS:           task_id
Screen Design: screen_id
```

## 13. Current MVP Scope

Active target flows:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
REQUIREMENT_SPEC -> WBS
REQUIREMENT_SPEC -> SCREEN_DESIGN
MEETING_NOTES -> SCHEDULE_TODO_LIST
```

Current implementation status:

```text
Requirement generation:
  Implemented with RequirementAgent and mock LLM fallback behavior.

WBS generation:
  API and orchestration exist.
  WbsAgent is still placeholder.

Screen design generation:
  API and orchestration exist.
  ScreenDesignAgent is still placeholder.

Schedule todo extraction:
  API and orchestration exist.
  ScheduleManagementAgent is still placeholder.

Real Bedrock:
  LLMService wrapper exists.
  Actual Bedrock call is TODO.

Vector search:
  RetrievalService boundary exists.
  Current search is keyword-based DB chunk search.
  pgvector/OpenSearch integration is TODO.
```

## 14. Team Rules Summary

Use these as the main rules when explaining the codebase:

```text
1. JSON is the internal contract.
2. Core Agents only process structured JSON.
3. Input Agents convert external/raw input into internal JSON.
4. Output Agents convert internal JSON into user-facing payloads.
5. Orchestrators control flow, context assembly, validation, and post-processing.
6. Routers never call LLMs directly.
7. Routers never access DB directly.
8. Agents never access DB, S3, repositories, or vector stores directly.
9. Services and Repositories own persistence boundaries.
10. LLM output must be validated before storage or response.
11. Retrieval must include project_id and permission_scope.
12. MVP first, extensible later.
```

## 15. One-Sentence Explanation

FINPM backend is a JSON-centric PM Agent platform where FastAPI routers handle
HTTP contracts, Services expose use cases, Orchestrators control agent workflows,
Agents generate or transform structured JSON, Validators enforce artifact
contracts, and Repositories own DB access.
