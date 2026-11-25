"""
Export every InfraGov table from Supabase into JSON files (one file per table).

    migration_data/
        auth_users.json              <- Supabase Auth users (email, status, dates)
        profiles.json
        assessments.json
        dimensions.json
        mbi_entries.json
        comments.json
        activity_log.json
        dimension_collaborators.json
        dimension_invitations.json
        assessment_team.json
        unpublish_requests.json
        assessment_documents.json
        indicator_suggestions.json
        _export_summary.json         <- row counts + mapping to UC table names (not a table)
        files/                       <- only with --files (uploaded documents)

READ ONLY: this script never writes to Supabase. It uses only the Python
standard library (plus python-dotenv if installed, and psycopg only for the
optional --include-password-hashes).

Usage (from the repo root, with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env):
    python migration.py                              # all tables
    python migration.py --tables assessments comments
    python migration.py --files                      # also download uploaded documents
    python migration.py --include-password-hashes    # also export bcrypt hashes (needs SUPABASE_DB_URL)
    python migration.py --out my_folder

SECURITY: the exported files contain personal data (names, e-mails, phone
numbers) and the service-role key bypasses all row-level security. Run this on a
trusted machine, never commit migration_data/ or .env, and delete the folder
once the data is loaded into Databricks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "migration_data"
PAGE_SIZE = 1000
TIMEOUT_SEC = 120
MAX_RETRIES = 4

# Supabase source table  ->  suggested Unity Catalog table (prd_mega.sgpbpi163.<name>)
# (names match constants.TABLE_NAMES; "profiles" + "auth_users" are merged into infragov_users)
PUBLIC_TABLES: dict[str, str] = {
    "profiles": "infragov_users",
    "assessments": "infragov_assessments",
    "dimensions": "infragov_dimensions",
    "mbi_entries": "infragov_mbi_entries",
    "comments": "infragov_comments",
    "activity_log": "infragov_activity_log",
    "dimension_collaborators": "infragov_dimension_collaborators",
    "dimension_invitations": "infragov_dimension_invitations",
    "assessment_team": "infragov_assessment_team",
    "unpublish_requests": "infragov_unpublish_requests",
    "assessment_documents": "infragov_assessment_documents",
    "indicator_suggestions": "infragov_indicator_suggestions",
}
AUTH_USERS = "auth_users"
ALL_TABLES = [AUTH_USERS, *PUBLIC_TABLES]

STORAGE_BUCKET_DEFAULT = "assessment-documents"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
# Auth fields worth keeping (the Auth API also returns tokens/metadata we do not need).
_AUTH_FIELDS = ("id", "email", "phone", "email_confirmed_at", "last_sign_in_at", "banned_until",
                "created_at", "updated_at")


# --------------------------------------------------------------------------- env
def load_env() -> None:
    """Load .env from the repo root (python-dotenv if present, else a tiny parser)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        return
    except ImportError:
        pass
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"ERROR: environment variable {name} is missing. Add it to your .env file (see .env.sample).")
    return value


def supabase_base_url() -> str:
    url = require_env("SUPABASE_URL").rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        sys.exit("ERROR: SUPABASE_URL must be an https:// URL such as https://<project-ref>.supabase.co")
    return f"https://{parsed.netloc}"


# ------------------------------------------------------------------------ HTTP
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects, so the service-role key can't be forwarded to another host."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def http_get(url: str, key: str, extra_headers: dict[str, str] | None = None):
    """GET with retries on 429/5xx. Returns (body_bytes, response_headers)."""
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    headers.update(extra_headers or {})
    last: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with _opener.open(req, timeout=TIMEOUT_SEC) as resp:  # noqa: S310 - https host validated above
                return resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                last = e
                time.sleep(2 ** attempt)
                continue
            if e.code in (401, 403):
                sys.exit(f"ERROR: Supabase rejected the key (HTTP {e.code}). Use the *service_role* key "
                         f"(Project Settings → API), not the anon key.")
            raise RuntimeError(f"HTTP {e.code} for {urllib.parse.urlparse(url).path}: {body}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
    raise RuntimeError(f"Could not reach Supabase: {last}")


# --------------------------------------------------------------------- exporters
def export_table(base: str, key: str, table: str) -> tuple[list[dict], int | None]:
    """Download every row of public.<table> using stable, paginated REST calls."""
    if not _IDENT.match(table):  # defensive: names come from the constants above
        raise ValueError(f"Unsafe table name: {table!r}")
    rows: list[dict] = []
    expected: int | None = None
    offset = 0
    while True:
        qs = urllib.parse.urlencode({"select": "*", "order": "id.asc", "limit": PAGE_SIZE, "offset": offset})
        body, headers = http_get(f"{base}/rest/v1/{table}?{qs}", key, {"Prefer": "count=exact"})
        if expected is None:
            m = re.search(r"/(\d+)$", headers.get("Content-Range", ""))
            expected = int(m.group(1)) if m else None
        page = json.loads(body)
        if not page:
            break
        rows.extend(page)
        offset += len(page)  # advance by what we actually got (server may cap max rows)
    return rows, expected


def export_auth_users(base: str, key: str) -> list[dict]:
    """Supabase Auth users via the admin API (no password hashes are exposed here)."""
    users: list[dict] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({"page": page, "per_page": PAGE_SIZE})
        body, _ = http_get(f"{base}/auth/v1/admin/users?{qs}", key)
        batch = json.loads(body).get("users", [])
        if not batch:
            break
        users.extend({k: u.get(k) for k in _AUTH_FIELDS} for u in batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return sorted(users, key=lambda u: u["id"])


def add_password_hashes(users: list[dict]) -> int:
    """Optional: read bcrypt hashes straight from Postgres (auth.users.encrypted_password)."""
    db_url = require_env("SUPABASE_DB_URL")
    try:
        import psycopg
    except ImportError:
        sys.exit("ERROR: --include-password-hashes needs psycopg:  pip install 'psycopg[binary]'")
    with psycopg.connect(db_url, sslmode="require", connect_timeout=20) as conn, conn.cursor() as cur:
        conn.read_only = True
        cur.execute("SELECT id::text, encrypted_password FROM auth.users")
        hashes = dict(cur.fetchall())
    for u in users:
        u["encrypted_password"] = hashes.get(u["id"]) or None
    return sum(1 for u in users if u["encrypted_password"])


def download_files(base: str, key: str, docs: list[dict], out_dir: Path) -> tuple[int, list[str]]:
    """Optional: download uploaded documents referenced by assessment_documents.storage_path."""
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", STORAGE_BUCKET_DEFAULT).strip() or STORAGE_BUCKET_DEFAULT
    if not re.match(r"^[A-Za-z0-9._-]+$", bucket):
        sys.exit("ERROR: SUPABASE_STORAGE_BUCKET contains invalid characters.")
    files_dir = (out_dir / "files").resolve()
    files_dir.mkdir(parents=True, exist_ok=True)
    done, failed = 0, []
    for d in docs:
        rel = d.get("storage_path")
        if not rel:
            continue
        target = (files_dir / rel).resolve()
        if files_dir not in target.parents:  # path-traversal guard
            failed.append(f"{rel} (unsafe path)")
            continue
        try:
            data, _ = http_get(f"{base}/storage/v1/object/{bucket}/{urllib.parse.quote(rel)}", key,
                               {"Accept": "*/*"})
        except RuntimeError as e:
            failed.append(f"{rel} ({e})")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o600)
        done += 1
    return done, failed


# ------------------------------------------------------------------------ output
def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.chmod(tmp, 0o600)  # personal data: owner-only
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Download all InfraGov data from Supabase into JSON files.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default: ./migration_data)")
    ap.add_argument("--tables", nargs="+", choices=ALL_TABLES, metavar="TABLE",
                    help=f"only export these tables (default: all). Choices: {', '.join(ALL_TABLES)}")
    ap.add_argument("--files", action="store_true", help="also download uploaded documents from Supabase Storage")
    ap.add_argument("--include-password-hashes", action="store_true",
                    help="add bcrypt hashes to auth_users.json (needs SUPABASE_DB_URL + psycopg)")
    args = ap.parse_args()

    load_env()
    base = supabase_base_url()
    key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)

    wanted = args.tables or ALL_TABLES
    summary: dict[str, dict] = {}
    docs: list[dict] = []
    problems = 0

    print(f"Supabase project: {urllib.parse.urlparse(base).hostname}\nOutput folder:   {out_dir}\n")
    for table in wanted:
        try:
            if table == AUTH_USERS:
                rows, expected = export_auth_users(base, key), None
                if args.include_password_hashes:
                    n = add_password_hashes(rows)
                    print(f"  (password hashes added for {n} of {len(rows)} users)")
                uc = "infragov_users (merge with profiles)"
            else:
                rows, expected = export_table(base, key, table)
                uc = PUBLIC_TABLES[table]
            if table == "assessment_documents":
                docs = rows
        except RuntimeError as e:
            print(f"  FAILED  {table}: {e}")
            problems += 1
            continue
        write_json(out_dir / f"{table}.json", rows)
        ok = expected is None or expected == len(rows)
        problems += 0 if ok else 1
        summary[table] = {"rows": len(rows), "server_count": expected, "file": f"{table}.json", "uc_table": uc}
        flag = "OK " if ok else "MISMATCH"
        print(f"  {flag:8} {table:26} {len(rows):>8} rows  -> {table}.json")

    if args.files:
        if not docs and "assessment_documents" not in wanted:
            try:
                docs, _ = export_table(base, key, "assessment_documents")
            except RuntimeError as e:
                print(f"  FAILED  could not list documents: {e}")
        done, failed = download_files(base, key, docs, out_dir)
        summary["_files"] = {"downloaded": done, "failed": failed}
        problems += len(failed)
        print(f"\n  Documents downloaded: {done}/{len(docs)} -> {out_dir / 'files'}")
        for f in failed:
            print(f"    could not download: {f}")

    write_json(out_dir / "_export_summary.json", {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": urllib.parse.urlparse(base).hostname,
        "tables": summary,
    })
    print("\nDone." if not problems else f"\nFinished with {problems} problem(s) - see above.")
    print("Reminder: these files hold personal data. Do not commit them; delete them after the upload.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
