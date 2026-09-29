# Backend

FastAPI + PostgreSQL (SQLite supported for zero-setup local dev).

## Quickstart

```powershell
# one-time (from the repo root): create .env and set AUTH_SECRET — the server won't start without it
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"

# from backend/
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head               # creates/updates the schema
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload      # http://localhost:8000/docs

.\.venv\Scripts\python.exe -m pytest              # SQLite
.\.venv\Scripts\python.exe -m pytest --postgres   # real PostgreSQL (throwaway, via pgserver)
.\.venv\Scripts\python.exe -m ruff check .
```

Run `pytest --postgres` before trusting any schema change — SQLite hides length, timezone and
type problems that Postgres rejects.

## Structure

```
app/
  core/         Settings (env-var config) + domain errors
  db/           Base, UTCDateTime, lazy engine/session
  api/          route handlers (thin — delegate to services) + error envelope; mounts /api/v1
  auth/         register, login, me — Argon2id + JWT bearer
  models/       User, Course, Chapter, Topic, Concept, Document, CurriculumProposal, … — see
                ../docs/DATA_MODEL.md
  schemas/      request/response schemas (auth has its own in auth/schemas.py)
  services/
    courses/     Course hierarchy CRUD + ownership/isolation enforcement
    documents/   upload + ingestion pipeline (detect, extract, clean, chunk)
    curriculum/  AI curriculum proposals, grounding, apply, outline
    {retrieval,learning,questions,evaluation,scheduling,mastery,analytics}/
                 still empty, built out Phase 8+
  ai/           AIProvider, OpenAI-compatible transport, MockAIProvider — see ../docs/AI.md
  prompts/      versioned prompt templates
  storage/      document file storage (local disk)
migrations/     Alembic — the only thing that creates or changes the schema
tests/          auth, courses, documents, curriculum, AI provider, isolation (every endpoint),
                errors, config, migrations
```

See [`../docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md) for the decisions behind all of this.
