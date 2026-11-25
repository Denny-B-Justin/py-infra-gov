# InfraGov Assessment Tool — Python Dash (Posit Connect)

Python 3.11.9 / Dash 4 port of the Next.js + Supabase app (`infragov-dashboard.vercel.app`),
backed by **Azure Databricks Unity Catalog** (`prd_mega.sgpbpi163`) and hardened for production.

## Project layout

```
app.py                     Dash app, ?page= router, secure download route (entrypoint app:app)
constants.py               Table names, UC location, roles, limits, env-driven deployment settings
manage.py                  gen-keys · create-admin · print-uc-ddl · seed-demo (local only)
requirements.txt           Pinned dependencies (pip-audit clean)
manifest.json              Posit Connect manifest (rsconnect-python, python-dash, 3.11.9)
.env.sample                Every environment variable, documented
assets/                    style.css (compiled), app.js, self-hosted fonts, icons, images, video
pages/                     One module per page + pages_constants.py (page copy & UI constants)
utils/                     Design system: layout, components, charts, panels, i18n, framework data
services/                  db (parameterised SQL) · auth · permissions · repository · security
                           crypto · validators · documents · storage (UC Volume) · ai · exports · users
data/                      Framework questions (4 languages), countries, i18n messages, release notes
migration/                 Data-volume SQL, UC DDL, grants, Supabase→UC script, MIGRATION_GUIDE.md
tailwind/input.css         Source of assets/style.css (design tokens from the original globals.css)
SECURITY_AUDIT.md          Findings in the original app + controls in this version
```

## Pages (`/?page=<name>`)

| Page | URL |
|---|---|
| Landing | `/?page=home` |
| About · Release notes | `/?page=about` · `/?page=release-notes` |
| Sign in · Forgot · Set/reset password | `/?page=login` · `/?page=forgot-password` · `/?page=reset-password&token=…` |
| Assessments · New | `/?page=assessments` · `/?page=new-assessment&kind=pagfa` |
| Dimensions · Indicator form · Publish | `/?page=dimensions&id=<uuid>` · `/?page=dimension&id=<uuid>&dim=3&mbi=2` · `/?page=publish&id=<uuid>&dim=3` |
| Visualization · Settings · Report | `/?page=visualization&id=…` · `/?page=details&id=…&tab=team` · `/?page=report&id=…` |
| Global dashboard · Country profile | `/?page=dashboard&kind=infragov` · `/?page=country&name=serbia` |
| Account · Admin (Admins only) · Join invite | `/?page=account` · `/?page=admin` · `/?page=join&token=…` |

## Run locally

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export APP_ENV=development DB_BACKEND=sqlite
python manage.py seed-demo        # demo users, password printed
python app.py                     # http://127.0.0.1:8050/?page=home
```

## Deploy to Posit Connect

1. Create the UC objects and grants (`migration/01_…sql`, `02_…sql`), then migrate data (`migration/MIGRATION_GUIDE.md`).
2. Deploy:
   ```bash
   pip install rsconnect-python
   rsconnect add --server https://connect.example.org --name connect --api-key <key>
   rsconnect deploy manifest manifest.json --name connect --title "InfraGov Assessment Tool"
   ```
3. In the content's **Vars** panel set everything from `.env.sample` (mark credentials as secret). The app refuses to start in production if `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` or the Databricks credentials are missing.
4. If any file changes, regenerate the manifest:
   `rsconnect write-manifest dash . --entrypoint app:app --override-python-version 3.11.9 -x ".env" -x ".local/*" -x "tailwind/*" -x "migration/*" -x "manage.py" -x "*.md" -o`
5. First Admin (if not migrated): `python manage.py create-admin you@org.org "Your Name"` with production env vars.

## Restyling

Class names are Tailwind utilities copied from the original components. After changing them, rebuild:
`npx @tailwindcss/cli@4 -i tailwind/input.css -o assets/style.css --minify`

## Behaviour changes vs. the original (deliberate)

* Data visibility is server-enforced: non-members see only **published** answers; team, activity and invitations are member-only; the user directory is Admin-only.
* Owners can't unpublish directly — they file a request that an Admin approves (as the UI always intended).
* Invite links only work for the invited e-mail address and expire after 14 days; new users are created by an Admin (open registration stays closed).
* Account → Profile/Notifications/Password now actually save; the sign-in e-mail is read-only.
* Assessment Settings "Save Changes" now saves Department and Description (the title stays system-generated).
* AI features appear only when `ANTHROPIC_API_KEY` is set.

## Exporting the Supabase data to JSON (`migration.py`)

`python migration.py` downloads every Supabase table into `migration_data/<table>.json`
(one file per table; add `--files` for uploaded documents, `--include-password-hashes`
for bcrypt hashes). It needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your local
`.env` (see `.env.sample`). The folder contains personal data: it is git-ignored and excluded
from the Connect bundle — delete it after the upload.
