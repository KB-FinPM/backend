# FINPM Backend Development Guide

This guide explains how to set up, run, and test the FINPM backend locally.

## Requirements

- Python 3.11+ for the current local environment
- Python 3.12+ for the target backend stack
- PowerShell on Windows
- AWS credentials or IAM role when testing real S3, Bedrock, or Aurora

## Environment Variables

Copy `.env.example` to `.env` under `C:\workspace\FINPM\backend`.

```powershell
Copy-Item .env.example .env
```

Set DB, S3, AWS, and Bedrock values in that `.env` file.

Local DB default:

```env
DATABASE_URL=sqlite+aiosqlite:///./finpm.db
```

Aurora PostgreSQL example:

```env
DATABASE_URL=postgresql+asyncpg://finpm_user:CHANGE_ME@your-aurora-endpoint.ap-northeast-2.rds.amazonaws.com:5432/finpm
```

S3 settings:

```env
S3_BUCKET_NAME=kbds-s3-finpm
S3_UPLOAD_PREFIX=storage/upload_files
S3_TEMPLATE_PREFIX=storage/template_files
S3_GENERATED_PREFIX=storage/generated_files
```

AWS/Bedrock settings:

```env
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5
```

If the backend runs on AWS with an IAM role, keep access keys empty and let the
runtime credential provider resolve credentials.

## Create Virtual Environment

From `C:\workspace\FINPM\backend`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Check And Create Tables

Print the registered SQLAlchemy tables without connecting to the DB:

```powershell
python -m app.db.describe_schema
```

Create tables against the configured `DATABASE_URL`:

```powershell
python -m app.db.init_schema
```

Use this only for local or freshly provisioned MVP environments. Add Alembic
before production-style shared schema changes.

## Run API Server

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

## Run Tests

```powershell
python -m pytest
```

Current expected result:

```text
All tests pass
```

## Current API Flow

Upload:

```text
Upload API
-> InputOrchestrator(FILE)
-> S3Service
-> DocumentService
-> DocumentIngestionOrchestrator
-> DocumentRepository
-> OutputOrchestrator(API_RESPONSE)
```

Artifact generation:

```text
Generation API
-> InputOrchestrator(ARTIFACT_REQUEST)
-> GenerationService
-> GenerationOrchestrator
-> RetrievalService
-> ArtifactAgent
-> ValidatorAgent
-> ArtifactService
-> OutputOrchestrator(API_RESPONSE)
```

Schedule todo extraction:

```text
Schedule API
-> InputOrchestrator(MEETING_NOTES)
-> ScheduleService
-> ScheduleOrchestrator
-> ScheduleManagementAgent
-> ValidatorAgent
-> OutputOrchestrator(API_RESPONSE)
```

## Useful API Checks

Generate schedule todos:

```powershell
curl.exe -X POST http://localhost:8000/schedule/todos `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PRJ-001\",\"meeting_notes\":\"Discussed login scope and due date.\"}"
```

Generate a requirement artifact:

```powershell
curl.exe -X POST http://localhost:8000/generate/requirement `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PRJ-001\",\"source_document_ids\":[\"DOC-001\"],\"source_document_type\":\"CONSTRUCTION_REQUIREMENT_DEFINITION\",\"target_artifact_type\":\"REQUIREMENT_SPEC\",\"template_id\":\"TPL-REQ-SPEC-DEFAULT\",\"query\":\"Create a requirement spec\"}"
```

## Agent Import Rule

Do not change routers for Agent implementation. Replace the internals of the
adapter class under `app/agents/.../agent.py`, then add/adjust tests under
`tests/agents`.

Primary adapter slots:

- `app/agents/core_agents/artifact_agent/agent.py`
- `app/agents/core_agents/wbs_agent/agent.py`
- `app/agents/core_agents/screen_design_agent/agent.py`
- `app/agents/core_agents/schedule_management_agent/agent.py`
- `app/agents/input_agents/document_parser_agent/agent.py`
- `app/agents/output_agents/markdown_agent/agent.py`

## Commit Policy

Keep commits small:

- source change
- tests for that change
- docs/config changes when they clarify operation

Do not push from local automation unless explicitly requested.
