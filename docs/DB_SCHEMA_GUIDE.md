# DB Schema Guide

FINPM currently uses SQLAlchemy metadata as the MVP schema source.

## Current Scope

The backend models define these table groups:

- Documents and chunks
- Generated artifacts
- Artifact templates
- Artifact traceability links

## Check Registered Tables

Before creating or changing tables, print the currently registered SQLAlchemy
metadata:

```bash
python -m app.db.describe_schema
```

This command does not connect to the database. It only reads model metadata.

## Create Tables

For local SQLite or a freshly provisioned DB:

```bash
python -m app.db.init_schema
```

This uses `Base.metadata.create_all`.

## Change Workflow

For MVP changes:

1. Add or update SQLAlchemy model files under `app/models`.
2. Import new models in `app/db/base.py`.
3. Add repository/service tests using in-memory SQLite.
4. Run:

```bash
python -m app.db.describe_schema
python -m pytest -q
```

5. Run `python -m app.db.init_schema` only against the intended local/provisioned
   database.

## Later Migration Tooling

TODO: Add Alembic before production schema changes become frequent or before
multiple shared environments need controlled migrations.
