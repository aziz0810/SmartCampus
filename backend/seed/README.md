# SmartCampus demo catalog seed

`demo_catalog.json` is a curated development seed composed from
[`iit_scraped_catalog.json`](iit_scraped_catalog.json) plus explicitly fictional
examples. The loader uses the existing SA-17 tables and does not create or
alter schema objects.

## Provenance

| Data | Contents | Database marking |
|---|---|---|
| Public IIT scrape | 13 formations, their general specialties, and 7 subject labels | `is_demo=false`; `source_note` retains the URL/date and says `needs_review=true`. These scraped facts have not been independently verified. |
| Synthetic catalog | One additional IIT preparatory formation, one ISB placeholder, 6 example programs, 8 example subjects, 40 subject mappings, and 5 example tuition fees | `is_demo=true`; `source_note` says the records are fictitious. No ISB curriculum or fee is asserted. |
| Staff accounts | Five example staff accounts and one inactive interview-officer account | `@example.com` emails; passwords are Argon2 hashes generated from `DEMO_USER_PASSWORD`. |

`institution`, `role`, and `app_user` do not have provenance columns in the
current schema. Names and emails in those rows are clearly marked as demo data.
No personal contact details or real account data are included. The raw scrape
file is left unchanged.

Some French labels in the current scrape already contain Unicode replacement
characters (`�`). They are preserved rather than guessed; correct or re-scrape
those source records before presenting them as verified catalog text.

## Configure and run (PowerShell, from the repository root)

Set a local demo password in the ignored `.env` file. Use a long development-only
value; it is not included in the seed JSON or tracked source. `.env.example`
contains the variable name.

```powershell
Set-Location .\backend
..\.venv\Scripts\Activate.ps1
python seed\validate_seed.py
python -m seed.load_demo_data --dry-run
python -m seed.load_demo_data
```

The loader rejects production `APP_ENV`, validates before connecting, and wraps
all upserts in one transaction. A dry run prints the prospective row counts and
rolls everything back. Re-running the regular command updates rows by their
natural keys; it does not duplicate them, delete rows, or reset an existing
account's password. Demo user passwords are set only when each account is first
created.

An existing database may still have the older nullable definitions for
`duration_semesters`, `semester`, `credits`, and `amount` until Alembic reaches
head. This seed supplies all four values either way. The loader does not run
Alembic; schema upgrades remain separate from the seed ticket.

## Tests

```powershell
python -m pytest tests\seed -v
```

Validation tests run without PostgreSQL. Loader integration tests use one
transaction and always roll it back; they skip with a reason if the local SA-17
database or its tables are unavailable.
