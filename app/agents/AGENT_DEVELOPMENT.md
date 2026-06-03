<!-- EN: Development contract for FINPM agent implementers. -->
<!-- KO: FINPM Agent 구현/이식 개발자를 위한 계약 문서입니다. -->

# FINPM Agent Development Guide

This document is the working contract for agent developers and backend
integration. Agent code must fit this backend boundary so it can be mounted
without changing FastAPI routers, repositories, or storage code.

## Current Product Flow

The active FINPM MVP scope is:

```text
Artifact generation:
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
REQUIREMENT_SPEC -> WBS
REQUIREMENT_SPEC -> SCREEN_DESIGN

Schedule management:
MEETING_NOTES -> lightweight todo list
```

Detailed meeting/action-item requirements are not finalized yet. Keep schedule
management minimal until the product spec is clarified.

## Architecture Boundary

```text
Router
-> Service
-> Orchestrator
-> Input/Core/Output Agent
-> Validator
-> Service/Repository/Storage
```

Rules:

- Routers must not call LLMs directly.
- Routers must not access DB, S3, or vector stores directly.
- Agents must not create FastAPI responses.
- Agents must not access DB, S3, repositories, or vector stores directly.
- Core Agents must process structured JSON-like input only.
- LLM calls must go through `app.core.llm.llm_service`.
- Orchestrators own flow control, context assembly, validation, and
  post-processing.

## Agent Types

### Input Agent

Purpose:

```text
User/raw/file input
-> normalized FINPM internal JSON
```

Contract:

```python
from app.schemas.io_agent import InputAgentRequest, InputAgentResponse

async def parse(request: InputAgentRequest) -> InputAgentResponse:
    ...
```

Current implementation:

- `app/agents/input_agents/document_parser_agent/agent.py`
- `DocumentParserAgent`
- Handles `InputType.FILE` for text-like files.

Do not add upload, S3, or DB logic to Input Agents.

### Core Agent

Purpose:

```text
Structured JSON/context
-> PM artifact JSON
```

Contract:

```python
from app.schemas.agent import AgentRequest, AgentResponse

async def generate(request: AgentRequest) -> AgentResponse:
    ...
```

Current adapter slots:

- `ArtifactAgent`
  - `app/agents/core_agents/artifact_agent/agent.py`
  - Unified artifact-generation boundary used by the backend.
  - It currently delegates to Requirement/WBS/Screen adapters internally.
  - If the delivered source is one integrated document-generation agent, replace
    this class first.
- `RequirementAgent`
  - `app/agents/core_agents/requirement_agent/agent.py`
  - Active implementation exists.
- `WbsAgent`
  - `app/agents/core_agents/wbs_agent/agent.py`
  - Placeholder adapter. Replace only the inside of `generate`.
- `ScreenDesignAgent`
  - `app/agents/core_agents/screen_design_agent/agent.py`
  - Placeholder adapter. Replace only the inside of `generate`.
- `ScheduleManagementAgent`
  - `app/agents/core_agents/schedule_management_agent/agent.py`
  - Placeholder adapter for meeting-notes-based todo extraction.

The backend intentionally calls the unified `ArtifactAgent` boundary from the
generation orchestrator. Specialized agents may remain internal delegates, or
they may be folded into one integrated artifact-generation source later.

### Output Agent

Purpose:

```text
Internal artifact/result JSON
-> user-facing API/display/export payload
```

Contract:

```python
from app.schemas.io_agent import OutputAgentRequest, OutputAgentResponse

async def render(request: OutputAgentRequest) -> OutputAgentResponse:
    ...
```

Current implementation:

- `app/agents/output_agents/markdown_agent/agent.py`
- `MarkdownOutputAgent`
- Handles `OutputResponseType.ARTIFACT_EXPORT` with `output_format="markdown"`.

## Core Agent Input Shape

Core Agents receive `AgentRequest`:

```python
AgentRequest(
    project_id="PRJ-001",
    documents=[
        {
            "chunk_id": "CHUNK-001",
            "project_id": "PRJ-001",
            "document_id": "DOC-001",
            "chunk_index": 0,
            "text": "...",
            "section_title": None,
            "metadata": {},
        }
    ],
    context={
        "source_document_ids": ["DOC-001"],
        "document_ids": ["DOC-001"],
        "source_document_type": "REQUIREMENT_SPEC",
        "target_artifact_type": "WBS",
        "template": {
            "template_id": "TPL-REQ-SPEC-DEFAULT",
            "template_version": "v1",
            "content": "...",
            "placeholders": {},
        },
        "query": "optional user request",
        "permission_scope": ["project:read", "artifact:generate"],
    },
)
```

Agents may read `documents` and `context`, but must not call retrieval again.

## Core Agent Output Shape

Return `AgentResponse`.

Success:

```python
AgentResponse(
    success=True,
    agent_name="WbsAgent",
    result={...},
)
```

Failure:

```python
AgentResponse(
    success=False,
    agent_name="WbsAgent",
    error="reason",
)
```

Never raise user-facing errors for expected validation/generation failures.
Return `AgentResponse(success=False, error="...")` instead.

## Minimal Artifact Schemas

Backend currently enforces only the minimum needed for validation, storage, and
traceability. Agent developers may put detailed fields under `metadata` until a
more specific schema is agreed.

### Requirement Artifact

Schema:

- `app/schemas/requirement.py`

Minimum item fields:

- `requirement_id`
- `title`
- `description`
- `priority`
- `source_document_id`
- `source_chunk_ids`
- `acceptance_criteria`
- `rationale`

### WBS Artifact

Schema:

- `app/schemas/wbs.py`

Minimum result:

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

### Screen Design Artifact

Schema:

- `app/schemas/screen_design.py`

Minimum result:

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

## Traceability Contract

Artifact relationships are stored through:

- `app/models/artifact_link.py`
- `app/schemas/traceability.py`
- `app/services/traceability_service.py`

Active relation types:

```text
CONSTRUCTION_REQUIREMENT_DEFINITION -> REQUIREMENT_SPEC
DERIVED_FROM

REQUIREMENT_SPEC -> WBS
DECOMPOSED_TO

REQUIREMENT_SPEC -> SCREEN_DESIGN
DESIGNED_BY
```

Agent outputs should include stable item IDs so the backend can create links:

- Requirement: `requirement_id`
- WBS: `task_id`
- Screen Design: `screen_id`

## Template Contract

Agents do not load templates. The orchestrator resolves templates and passes
the resolved template under `AgentRequest.context["template"]`.

Use this as read-only generation guidance.

## Where To Put Agent Code

Integrated artifact-generation source:

```text
app/agents/core_agents/artifact_agent/agent.py
```

Use this path if the delivered source owns all artifact generation in one
agent.

WBS:

```text
app/agents/core_agents/wbs_agent/agent.py
```

Replace:

```python
async def generate(self, request: AgentRequest) -> AgentResponse:
    ...
```

Screen Design:

```text
app/agents/core_agents/screen_design_agent/agent.py
```

Replace:

```python
async def generate(self, request: AgentRequest) -> AgentResponse:
    ...
```

Do not change router code for agent implementation.

Schedule management:

```text
app/agents/core_agents/schedule_management_agent/agent.py
```

Keep the first implementation lightweight: meeting notes or text context in,
todo-like schedule items out. Do not add detailed requirement elaboration here
until the schedule-management spec is clarified.

## Tests Required From Agent Developers

Add tests under `tests/agents/`.

Required cases:

- Success with valid `AgentRequest`.
- Failure with missing/empty required context.
- Output matches the minimal schema.
- LLM wrapper failure returns `AgentResponse(success=False)`.

Recommended command:

```bash
python -m pytest tests/agents -q
```

Before handoff, full backend test should pass:

```bash
python -m pytest -q
```

## Current TODOs

- TODO: Replace `WbsAgent` placeholder with real agent source.
- TODO: Replace `ScreenDesignAgent` placeholder with real agent source.
- TODO: Decide whether delivered artifact-generation code replaces
  `ArtifactAgent` as one integrated agent or remains delegated by artifact type.
- TODO: Replace `ScheduleManagementAgent` placeholder after meeting/todo scope
  is finalized.
- TODO: Create artifact links automatically after WBS/Screen generation.
- TODO: Add PDF/DOCX Input Agents.
- TODO: Add embedding/vector-store indexing.
- TODO: Add DOCX/PDF/XLSX Output Agents.
- TODO: Connect real Bedrock invocation in `app.core.llm`.
