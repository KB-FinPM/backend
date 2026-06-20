# FINPM Backend Development Guide

## Stack

- Python 3.11
- FastAPI and Uvicorn
- Pydantic v2
- SQLAlchemy async sessions
- SQLite for local development, PostgreSQL/pgvector-capable repositories for deployed environments
- Amazon Bedrock through `app.core.llm.LLMService`
- S3 or local mock storage through `app.storage.s3`

## Setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.db.init_schema
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Use a Python 3.11 interpreter. On machines with multiple Python versions, call the
intended interpreter directly instead of relying on `python` from `PATH`.

## Tests

```powershell
cd backend
python -m pytest --collect-only
python -m pytest
```

## Security Notes

- Do not commit `.env`, `.env.*`, local databases, logs, mock storage, caches, or build output.
- `.env.example` must contain placeholders or empty values only.
- If any real AWS, API, or database credential was ever committed or shared, rotate it in the provider console before continuing development.
- Production secrets should live in a secret manager or deployment platform secrets, not in source files.
