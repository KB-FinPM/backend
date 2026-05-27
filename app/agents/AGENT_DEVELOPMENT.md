<!-- EN: Development guide for FINPM agent implementers. -->
<!-- KO: FINPM Agent 구현 개발자를 위한 개발 가이드입니다. -->

# FINPM Agent Development Guide

This guide is the working contract for future FINPM agent developers.
Each agent may define its own detailed payload schema, but all agents should
follow the same orchestration and validation shape.

## Layer Rules

- Routers must not call LLMs directly.
- Routers must not access databases, S3, or vector stores directly.
- Agents must not create HTTP responses.
- Core agents should only process structured JSON-like data.
- Input agents convert external formats into JSON.
- Output agents convert JSON into user-facing artifacts.
- Orchestrators own flow control, context assembly, validation, and post-processing.

## Agent Responsibilities

Each agent should have one clear job.

Examples:

- `RequirementAgent`: generate requirement JSON from project context.
- `ValidatorAgent`: validate schema and business rules.
- `WbsAgent`: generate WBS JSON from requirement or project context.
- `ActionItemAgent`: extract action item JSON from meeting context.
- `TraceabilityAgent`: generate and validate artifact relationships.

## Required Agent Shape

Every agent should expose one primary async method.

```python
async def generate(self, request: AgentRequest) -> AgentResponse:
    ...
```

Use a more specific method name only when it improves clarity, for example:

```python
async def validate(self, result: dict) -> AgentResponse:
    ...
```

## Input Contract

Use `AgentRequest` as the common envelope:

```python
AgentRequest(
    project_id="PRJ-001",
    documents=[{"chunk_id": "CHUNK-001", "text": "..."}],
    context={
        "source_document_ids": ["DOC-001"],
        "document_ids": ["DOC-001"],
        "source_document_type": "CONSTRUCTION_REQUIREMENT_DEFINITION",
        "target_artifact_type": "REQUIREMENT_SPEC",
        "template": {
            "template_id": "TPL-REQ-SPEC-DEFAULT",
            "template_version": "v1",
        },
        "query": "Create a requirement spec",
        "user_scope": "...",
    },
)
```

Agent-specific fields should live under `context` until a dedicated schema is
introduced.

## Confirmed Generation Paths

The current product direction is source-document driven generation.

Supported initial paths:

- `CONSTRUCTION_REQUIREMENT_DEFINITION` -> `REQUIREMENT_SPEC`
- `REQUIREMENT_SPEC` -> `SCREEN_DESIGN`
- `REQUIREMENT_SPEC` -> `WBS`

Agents should treat source documents as prior project artifacts and generate
the requested target artifact according to the selected template.

## Template Contract

Templates may come from either an admin UI or a built-in code-level registry.
Agents should not load templates directly from storage. The orchestrator should
resolve the template and pass the selected template metadata through context.

Minimum context shape:

```python
{
    "target_artifact_type": "REQUIREMENT_SPEC",
    "template": {
        "template_id": "TPL-REQ-SPEC-DEFAULT",
        "template_version": "v1",
    },
}
```

## Output Contract

Use `AgentResponse` as the common envelope:

```python
AgentResponse(
    success=True,
    agent_name="RequirementAgent",
    result={
        "requirements": [
            {
                "requirement_id": "RQ-001",
                "description": "The user can sign in.",
                "source": "RFP 3.1",
            }
        ]
    },
)
```

On failure:

```python
AgentResponse(
    success=False,
    agent_name="RequirementAgent",
    error="Missing project_id",
)
```

## TODO Template For New Agents

When adding a new agent, complete this checklist:

- [ ] Define the agent responsibility in one sentence.
- [ ] Define input data expected in `AgentRequest.context`.
- [ ] Define output JSON shape under `AgentResponse.result`.
- [ ] Document supported `source_document_type` -> `target_artifact_type` paths.
- [ ] Document required template sections and placeholders.
- [ ] Add rule validation requirements.
- [ ] Add unit tests for success and failure cases.
- [ ] Ensure the agent does not call DB, S3, or vector search directly.
- [ ] Ensure LLM calls go through `app.core.llm`.
- [ ] Wire the agent through an orchestrator, not a router.

## Test Expectations

Place tests by layer:

- `tests/agents/` for individual agent behavior.
- `tests/orchestrator/` for flow and dependency coordination.
- `tests/api/` for routing and response behavior.
- `tests/schemas/` for shared schema contracts.
