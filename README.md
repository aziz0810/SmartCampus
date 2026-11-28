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

## IIT public catalog scraper

Set `SCRAPER_CONTACT_EMAIL` in `.env` to the project contact address. From the
repository root, install the requirements and run the scraper from `backend/`:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m scraper.run
```

The scraper checks IIT's `robots.txt` before requesting pages, uses the
configured project user agent, follows only the allowlisted IIT URLs, waits at
least two seconds between requests, and caps requests at 40 pages. It removes
contact details, student-result/news panels, and bank details before writing
its ignored local cache. It does not write to PostgreSQL.

The reviewable catalog is written to
`backend/seed/iit_scraped_catalog.json`; page coverage is written to
`backend/scraper/output/coverage.md`. Values carry source URL, consultation
date, and a content hash. The model does not represent admission conditions or
career opportunities, so those appear only in the coverage report. Generated
catalog values need human review before database loading.

## Schema migrations (SA-17)

The catalog and responsible-account models are a baseline pending reconciliation
with the SA-12/13/14 data model. From `backend/`, generate and inspect the
initial migration before applying it:

```bash
alembic revision --autogenerate -m "initial schema"
# Review migrations/versions/*_initial_schema.py against the agreed data model.
alembic upgrade head
```
