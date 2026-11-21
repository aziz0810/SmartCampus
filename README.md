# SmartCampus AI

## Local PostgreSQL (SA-16)

1. Copy `.env.example` to `.env` and change both passwords.
2. Start PostgreSQL and pgvector: `docker compose up -d`.
3. Check startup: `docker compose ps` (wait until the `db` service is healthy).

The database is `smartcampus` by default. The `smartcampus_app` role owns it and
has no superuser, database creation, or role creation privileges. The `vector`
extension is installed during first-time initialization. The init script runs
only when the data volume is empty; removing it with `docker compose down -v`
deletes the database data.

## Backend database connection (SA-16)

Set `DB_HOST=localhost` and `DB_PORT` in `.env` to match the published Docker
port. Install the backend dependencies from the repository root, then start the
API:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

`GET http://127.0.0.1:8000/health/db` checks the database connection.

## Schema migrations (SA-17)

The catalog and responsible-account models are a baseline pending reconciliation
with the SA-12/13/14 data model. From `backend/`, generate and inspect the
initial migration before applying it:

```bash
alembic revision --autogenerate -m "initial schema"
# Review migrations/versions/*_initial_schema.py against the agreed data model.
alembic upgrade head
```
