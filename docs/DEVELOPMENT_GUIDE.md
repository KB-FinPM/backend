<!-- EN: Developer setup, run, and test guide for the FINPM backend. -->
<!-- KO: FINPM 백엔드 개발 환경 설정, 실행, 테스트 가이드입니다. -->

# FINPM Backend Development Guide

This guide explains how to set up, run, and test the FINPM backend locally.

## 1. Requirements

- Python 3.11+
- PowerShell on Windows
- AWS credentials when testing real S3, Bedrock, or Aurora integrations

## 2. Create Virtual Environment

From `C:\workspace\FINPM\backend`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If script activation is blocked by PowerShell policy, run commands through the
venv Python directly:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Environment Variables

Copy `.env.example` to `.env`.

```powershell
Copy-Item .env.example .env
```

Local default:

```env
DATABASE_URL=sqlite+aiosqlite:///./finpm.db
```

Aurora PostgreSQL example:

```env
DATABASE_URL=postgresql+asyncpg://finpm_user:CHANGE_ME@your-aurora-endpoint.ap-northeast-2.rds.amazonaws.com:5432/finpm
```

Configured S3 layout:

```env
S3_BUCKET_NAME=kbds-s3-finpm
S3_UPLOAD_PREFIX=storage/upload_files
S3_TEMPLATE_PREFIX=storage/template_files
S3_GENERATED_PREFIX=storage/generated_files
```

## 4. Initialize Database

For local SQLite or a provisioned Aurora PostgreSQL database:

```powershell
.\venv\Scripts\python.exe -m app.db.init_schema
```

This creates the current SQLAlchemy tables. In a later production stage, use
Alembic migrations instead of direct metadata creation.

## 5. Run API Server

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{
  "success": true,
  "message": "FINPM API is running"
}
```

## 6. Run Tests

```powershell
.\venv\Scripts\python.exe -m pytest
```

Current expected result:

```text
18 passed
```

One Pydantic v2 deprecation warning may remain until `Settings.Config` is
migrated to `SettingsConfigDict`.

## 7. Useful API Checks

Upload a source document:

```powershell
curl.exe -X POST http://localhost:8000/upload `
  -F "project_id=PRJ-001" `
  -F "document_type=CONSTRUCTION_REQUIREMENT_DEFINITION" `
  -F "file=@C:\path\to\source.pdf"
```

Generate a requirement artifact:

```powershell
curl.exe -X POST http://localhost:8000/generate/requirement `
  -H "Content-Type: application/json" `
  -d "{\"project_id\":\"PRJ-001\",\"source_document_ids\":[\"DOC-001\"],\"source_document_type\":\"CONSTRUCTION_REQUIREMENT_DEFINITION\",\"target_artifact_type\":\"REQUIREMENT_SPEC\",\"template_id\":\"TPL-REQ-SPEC-DEFAULT\",\"query\":\"Create a requirement spec\"}"
```

## 8. Architecture Notes

Do not call LLMs, DB, S3, or vector stores directly from routers.

Use this flow:

```text
API Router
-> Service or Orchestrator
-> Repository / Storage / Retrieval boundary
-> External system
```

Current upload flow:

```text
Upload API
-> S3Service.upload()
-> DocumentRepository.create_document()
-> DocumentUploadResponse
```

Current generation flow:

```text
Generation API
-> GenerationOrchestrator
-> RetrievalService
-> RequirementAgent
-> ValidatorAgent
-> GenerationResponse
```

## 9. AWS Setup Checklist

- Create Aurora PostgreSQL database.
- Create DB user for the backend.
- Allow network access from the backend runtime to Aurora.
- Put Aurora connection string into `DATABASE_URL`.
- Confirm S3 bucket exists: `kbds-s3-finpm`.
- Confirm S3 prefixes:
  - `storage/upload_files`
  - `storage/template_files`
  - `storage/generated_files`
- Configure AWS credentials or runtime IAM role.
- Confirm Bedrock model access in the target region.

## 10. Commit Policy

Keep commits small by step:

- feature or schema change
- tests for that change
- documentation-only updates separately when possible

Do not push from local automation unless explicitly requested.
