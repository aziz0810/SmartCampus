#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname postgres \
  --set=app_db_user="$APP_DB_USER" \
  --set=app_db_password="$APP_DB_PASSWORD" \
  --set=app_db_name="$APP_DB_NAME" <<'EOSQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE',
  :'app_db_user',
  :'app_db_password'
) \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db_name', :'app_db_user')
\gexec

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'app_db_name')
\gexec
EOSQL

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$APP_DB_NAME" <<'EOSQL'
CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
