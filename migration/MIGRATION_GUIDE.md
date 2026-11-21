# Migrating InfraGov from Supabase to Azure Databricks Unity Catalog

Target schema: **`prd_mega.sgpbpi163`**

## Is there a NoSQL database?

**No.** The original app uses **Supabase = PostgreSQL**, a relational SQL database, so the
data maps naturally onto Unity Catalog tables. Three things are document- or key/value-style and need special handling:

| NoSQL-like element | Where | How it becomes SQL (UC) |
|---|---|---|
| `JSONB` column `profiles.preferences` | user notification settings | Flattened into 4 `BOOLEAN` columns (`pref_email_notifications`, …) |
| `JSONB` column `indicator_suggestions.suggestion` | AI drafts | Stored as a JSON `STRING`; query with `from_json(suggestion, 'struct<…>')` or `suggestion:dataSource` |
| Postgres arrays (`TEXT[]`, `INT[]`, `UUID[]`) | key respondents, files, fiscal years, dimension ids, fields changed, document ids | JSON `STRING` columns, e.g. `["a","b"]` (query with `from_json(col,'array<string>')`) |
| **Supabase Storage** (object store) | bucket `assessment-documents` | **UC Volume** `prd_mega.sgpbpi163.infragov_documents` (same relative paths) |
| Browser `localStorage` (zustand) | cached session + assessments | Not migrated — replaced by server-side sessions; the database is the only source of truth |

## Table names to use

| Supabase source | Unity Catalog table |
|---|---|
| `auth.users` + `public.profiles` | `prd_mega.sgpbpi163.infragov_users` |
| `public.assessments` | `prd_mega.sgpbpi163.infragov_assessments` |
| `public.dimensions` | `prd_mega.sgpbpi163.infragov_dimensions` |
| `public.mbi_entries` | `prd_mega.sgpbpi163.infragov_mbi_entries` |
| `public.comments` | `prd_mega.sgpbpi163.infragov_comments` |
| `public.activity_log` | `prd_mega.sgpbpi163.infragov_activity_log` |
| `public.dimension_collaborators` | `prd_mega.sgpbpi163.infragov_dimension_collaborators` |
| `public.dimension_invitations` | `prd_mega.sgpbpi163.infragov_dimension_invitations` |
| `public.assessment_team` | `prd_mega.sgpbpi163.infragov_assessment_team` |
| `public.unpublish_requests` | `prd_mega.sgpbpi163.infragov_unpublish_requests` |
| `public.assessment_documents` | `prd_mega.sgpbpi163.infragov_assessment_documents` |
| `public.indicator_suggestions` | `prd_mega.sgpbpi163.infragov_indicator_suggestions` |
| *(new)* server-side sessions | `prd_mega.sgpbpi163.infragov_user_sessions` |
| *(new)* reset / set-password tokens | `prd_mega.sgpbpi163.infragov_auth_tokens` |
| *(new)* security audit trail | `prd_mega.sgpbpi163.infragov_security_events` |
| Storage bucket `assessment-documents` | Volume `prd_mega.sgpbpi163.infragov_documents` |

Names live in `constants.py` (`TABLE_NAMES`). Type mapping: UUID→`STRING`, `TIMESTAMPTZ`→`TIMESTAMP` (UTC), enums→`STRING` + `CHECK` constraint.
UC primary/foreign keys are informational, so the app enforces uniqueness and cascades deletes itself.

## How much data?

The exact figures live in your Supabase project, which this repo can't reach — run
**`00_supabase_data_volume.sql`** in the Supabase SQL editor for row counts and sizes per table plus the Storage bucket total.

What the schema implies:

| Per assessment (maximum) | InfraGov | PAG-FA |
|---|---|---|
| `dimensions` | 16 | 8 |
| `mbi_entries` (≈1–3 KB each) | 119 | 42 |
| `indicator_suggestions` (≈2–4 KB each) | 119 | 42 |
| `activity_log` | ~1 per saved edit (typically 100–500) | same |
| `comments`, team, collaborators, invitations | tens | tens |

Example: **50 assessments** ≈ 6,000 indicator answers, ~25,000 rows in total and roughly **10–50 MB** of table data
(less once stored as compressed Delta/Parquet). Users are in the tens to low hundreds.
The variable part is **uploaded documents**: up to 50 MB per file in the Volume, plus up to 1.5 M characters of extracted text per document in `infragov_assessment_documents`.
For a tool at this stage (a handful of country assessments), expect well under 10,000 rows and under 100 MB of table data; files are usually the larger share.

## Steps

1. **Measure** — run `00_supabase_data_volume.sql` in Supabase.
2. **Create the tables** — run `01_create_uc_tables.sql` in a Databricks SQL editor (one-off; it adds CHECK constraints).
3. **Grant least privilege** — edit and run `02_grants_least_privilege.sql` for the app's service principal; give it *Can use* on the SQL warehouse.
4. **Configure** — copy `.env.sample` to `.env` on a trusted machine; set the `DATABRICKS_*` variables, `FIELD_ENCRYPTION_KEY` (the **same** key the app will use) and `SUPABASE_DB_URL` (Supabase → Settings → Database → connection string), plus `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` if you copy files.
5. **Dry run** —
   ```bash
   pip install -r migration/requirements-migration.txt
   python -m migration.migrate_supabase_to_uc --dry-run
   ```
6. **Migrate** —
   ```bash
   python -m migration.migrate_supabase_to_uc --truncate --files
   ```
   It prints `source` vs `target` counts per table; every line should say `OK`.
7. **Freeze Supabase writes** during the cut-over (or run the script again right before switching DNS/links).
8. **Deploy** the Dash app to Posit Connect (see README) and sign in with an existing account — passwords keep working (bcrypt is upgraded to Argon2id automatically).

### What the script changes on the way

* Invitation tokens are converted to SHA-256 hashes; existing invite links keep working **for the invited e-mail address only**.
* `result_detail`, `extracted_text` and `phone` are encrypted with `FIELD_ENCRYPTION_KEY`.
* Supabase sessions/refresh tokens are not copied — everyone signs in once after the switch.
* Users whose `encrypted_password` is empty (invited but never set a password) get no password; an Admin can send them a set-password link from **Admin → Users → Reset link**.
