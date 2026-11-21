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
