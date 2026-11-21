"""
STEP 3 — Copy all InfraGov data from Supabase (Postgres + Storage) into
Azure Databricks Unity Catalog (prd_mega.sgpbpi163).

What it does
  * Reads every source table over a TLS connection (sslmode=require), READ ONLY.
  * Transforms rows to the UC schema (see services/schema.py):
      - auth.users + public.profiles → infragov_users (bcrypt hash kept; it is
        upgraded to Argon2id automatically at the user's next sign-in)
      - JSONB preferences → 4 boolean columns
      - Postgres arrays → JSON strings
      - invitation tokens → SHA-256 (plaintext tokens are NOT copied)
      - result_detail / extracted_text / phone → AES-256-GCM encrypted
      - mbi_entries & dimension_collaborators gain assessment_id
  * Writes to UC with PARAMETERISED multi-row INSERTs via the app's own
    Databricks connector (same service principal, TLS).
  * Copies Storage bucket "assessment-documents" into the UC Volume.
  * Prints source vs target row counts so you can verify the result.

Usage (from the project root, with .env holding the Databricks + key settings):
    pip install -r migration/requirements-migration.txt
    export SUPABASE_DB_URL='postgresql://postgres.<ref>:<password>@<host>:5432/postgres'
    export SUPABASE_URL='https://<ref>.supabase.co'
    export SUPABASE_SERVICE_ROLE_KEY='...'      # only needed for --files
    python -m migration.migrate_supabase_to_uc --dry-run          # counts only
    python -m migration.migrate_supabase_to_uc --truncate --files # full copy

Run it from a trusted machine; never commit the Supabase credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import constants as C  # noqa: E402
from services.crypto import encrypt_field, sha256_hex  # noqa: E402
from services.db import get_db  # noqa: E402
from services.schema import SCHEMA  # noqa: E402

BATCH_PARAMS = 240  # keep each INSERT under the connector's parameter limit


def ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v
    return v


def js(v):
    return json.dumps(list(v) if v is not None else [], ensure_ascii=False, default=str)


def fetch(pg, sql):
    with pg.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def transform(pg) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    users = fetch(pg, """
        SELECT u.id::text AS id, lower(u.email) AS email, u.encrypted_password, u.email_confirmed_at, u.last_sign_in_at,
               u.banned_until, u.created_at AS u_created, p.name, p.organisation, p.country, p.job_title, p.phone, p.role::text AS role,
               p.preferences, p.created_at, p.updated_at
        FROM auth.users u JOIN public.profiles p ON p.id = u.id""")
    out["users"] = [{
        "id": r["id"], "email": r["email"], "password_hash": r["encrypted_password"] or None,
        "name": r["name"] or "", "organisation": r["organisation"] or "", "country": r["country"] or "",
        "job_title": r["job_title"] or "", "phone": encrypt_field(r["phone"] or ""), "role": r["role"],
        "pref_email_notifications": bool((r["preferences"] or {}).get("emailNotifications", True)),
        "pref_weekly_digest": bool((r["preferences"] or {}).get("weeklyDigest", True)),
        "pref_invite_notifications": bool((r["preferences"] or {}).get("inviteNotifications", True)),
        "pref_publication_notifications": bool((r["preferences"] or {}).get("publicationNotifications", True)),
        "is_active": r["banned_until"] is None or ts(r["banned_until"]) < datetime.utcnow(),
        "email_confirmed_at": ts(r["email_confirmed_at"]), "failed_login_count": 0, "locked_until": None,
        "last_login_at": ts(r["last_sign_in_at"]), "password_changed_at": None,
        "created_at": ts(r["created_at"] or r["u_created"]), "updated_at": ts(r["updated_at"] or r["u_created"]),
    } for r in users]

    out["assessments"] = [{
        "id": r["id"], "kind": r["kind"] or "infragov", "title": r["title"], "country": r["country"], "department": r["department"] or "",
        "description": r["description"], "fiscal_years": js(r["fiscal_years"]), "owner_user_id": r["owner_user_id"],
        "created_at": ts(r["created_at"]), "updated_at": ts(r["updated_at"]),
    } for r in fetch(pg, "SELECT id::text, kind::text, title, country, department, description, fiscal_years, owner_user_id::text, created_at, updated_at FROM public.assessments")]

    dims = fetch(pg, "SELECT id::text, assessment_id::text, dim_id, status::text, created_at, updated_at FROM public.dimensions")
    dim_to_a = {d["id"]: d["assessment_id"] for d in dims}
    out["dimensions"] = [{**d, "created_at": ts(d["created_at"]), "updated_at": ts(d["updated_at"])} for d in dims]

    out["mbi_entries"] = [{
        "id": r["id"], "dimension_id": r["dimension_id"], "assessment_id": dim_to_a.get(r["dimension_id"]), "mbi_code": r["mbi_code"],
        "key_respondents": js(r["key_respondents"]), "data_source": r["data_source"] or "", "result_summary": r["result_summary"] or "",
        "result_detail": encrypt_field(r["result_detail"] or ""), "maturity_benchmark": r["maturity_benchmark"], "score": r["score"],
        "files": js(r["files"]), "status": r["status"], "last_edited_by": r["last_edited_by"], "last_edited_at": ts(r["last_edited_at"]),
        "created_at": ts(r["created_at"]), "updated_at": ts(r["updated_at"]),
    } for r in fetch(pg, """SELECT id::text, dimension_id::text, mbi_code, key_respondents, data_source, result_summary, result_detail,
                                  maturity_benchmark::text, score, files, status::text, last_edited_by::text, last_edited_at, created_at, updated_at
                           FROM public.mbi_entries""")]

    out["comments"] = [{**r, "created_at": ts(r["created_at"]), "updated_at": ts(r["updated_at"])} for r in fetch(pg, """
        SELECT id::text, assessment_id::text, dimension_id::text, mbi_code, author_user_id::text, author_name, text, created_at, updated_at
        FROM public.comments""")]

    out["activity_log"] = [{
        **{k: r[k] for k in ("id", "assessment_id", "type", "actor_user_id", "actor_name", "actor_organisation", "target_user_id", "target_name",
                             "dim_id", "dimension_name", "mbi_code", "import_source", "document_name", "from_role", "to_role", "reason",
                             "review_note", "request_id")},
        "dimension_ids": js(r["dimension_ids"]) if r["dimension_ids"] is not None else None,
        "fields_changed": js(r["fields_changed"]) if r["fields_changed"] is not None else None,
        "ai_assisted": bool(r["ai_assisted"]), "created_at": ts(r["created_at"]),
    } for r in fetch(pg, """SELECT id::text, assessment_id::text, type::text, actor_user_id::text, actor_name, actor_organisation,
                                  target_user_id::text, target_name, dim_id, dimension_name, dimension_ids, mbi_code, fields_changed,
                                  import_source, document_name, coalesce(ai_assisted, false) AS ai_assisted, from_role, to_role, reason,
                                  review_note, request_id::text, created_at FROM public.activity_log""")]

    out["dimension_collaborators"] = [{**r, "assessment_id": dim_to_a.get(r["dimension_id"]), "invited_at": ts(r["invited_at"])} for r in fetch(pg, """
        SELECT id::text, dimension_id::text, user_id::text, role::text, invited_by::text, invited_at FROM public.dimension_collaborators""")]

    out["dimension_invitations"] = [{
        "id": r["id"], "token_hash": sha256_hex(r["token"]), "assessment_id": r["assessment_id"], "dimension_id": r["dimension_id"],
        "email": (r["email"] or "").lower(), "role": r["role"], "organisation": r["organisation"], "invited_by": r["invited_by"],
        "status": r["status"], "accepted_user_id": r["accepted_user_id"], "accepted_at": ts(r["accepted_at"]),
        "expires_at": ts(r["expires_at"]), "created_at": ts(r["created_at"]),
    } for r in fetch(pg, """SELECT id::text, token, assessment_id::text, dimension_id::text, email, role::text, organisation, invited_by::text,
                                  status::text, accepted_user_id::text, accepted_at, expires_at, created_at FROM public.dimension_invitations""")]

    out["assessment_team"] = [{**r, "joined_at": ts(r["joined_at"]), "last_activity": ts(r["last_activity"])} for r in fetch(pg, """
        SELECT id::text, assessment_id::text, user_id::text, role, organisation, joined_at, last_activity FROM public.assessment_team""")]

    out["unpublish_requests"] = [{**r, "reviewed_at": ts(r["reviewed_at"]), "created_at": ts(r["created_at"])} for r in fetch(pg, """
        SELECT id::text, assessment_id::text, dimension_id::text, requested_by_user_id::text, requested_by_name, requested_by_email, reason,
               status::text, reviewed_by_user_id::text, reviewed_by_name, reviewed_at, review_note, created_at FROM public.unpublish_requests""")]

    out["assessment_documents"] = [{
        **{k: r[k] for k in ("id", "assessment_id", "filename", "mime_type", "size_bytes", "storage_path", "status", "error", "char_count",
                             "page_count", "uploaded_by_user_id", "uploaded_by_name", "uploaded_by_organisation")},
        "sha256": None, "extracted_text": encrypt_field(r["extracted_text"] or "") or None,
        "created_at": ts(r["created_at"]), "updated_at": ts(r["updated_at"]),
    } for r in fetch(pg, """SELECT id::text, assessment_id::text, filename, mime_type, size_bytes, storage_path, status, error, extracted_text,
                                  char_count, page_count, uploaded_by_user_id::text, uploaded_by_name, uploaded_by_organisation, created_at, updated_at
                           FROM public.assessment_documents""")]

    out["indicator_suggestions"] = [{
        **{k: r[k] for k in ("id", "assessment_id", "dimension_id", "dim_id", "mbi_id", "status", "reason", "locale", "model", "drafted_by", "drafted_by_name")},
        "suggestion": json.dumps(r["suggestion"], ensure_ascii=False) if r["suggestion"] is not None else None,
        "document_ids": js(r["document_ids"]), "drafted_at": ts(r["drafted_at"]),
    } for r in fetch(pg, """SELECT id::text, assessment_id::text, dimension_id::text, dim_id, mbi_id, status, suggestion, reason, locale, model,
                                  document_ids::text[] AS document_ids, drafted_by::text, drafted_by_name, drafted_at FROM public.indicator_suggestions""")]
    return out


def write(table_key: str, rows: list[dict], db) -> None:
    if not rows:
        return
    table = C.T[table_key]
    cols = [c for c, *_ in SCHEMA[table_key]["cols"]]
    per = max(1, BATCH_PARAMS // len(cols))
    for start in range(0, len(rows), per):
        chunk = rows[start:start + per]
        params, values = {}, []
        for i, r in enumerate(chunk):
            names = []
            for c in cols:
                key = f"{c}_{i}"
                params[key] = r.get(c)
                names.append(f":{key}")
            values.append("(" + ", ".join(names) + ")")
        db.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES {', '.join(values)}", params)


def copy_files(rows: list[dict]) -> int:
    from services import storage

    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    n = 0
    for r in rows:
        path = urllib.parse.quote(r["storage_path"])
        req = urllib.request.Request(f"{base}/storage/v1/object/assessment-documents/{path}",
                                     headers={"Authorization": f"Bearer {key}", "apikey": key})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - fixed https Supabase host
            storage.put(r["storage_path"], resp.read())
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="read + transform only, print counts")
    ap.add_argument("--truncate", action="store_true", help="DELETE existing rows in the UC tables first")
    ap.add_argument("--files", action="store_true", help="also copy Storage files into the UC Volume")
    args = ap.parse_args()
    if C.DB_BACKEND != "databricks" and not args.dry_run:
        sys.exit("Set DB_BACKEND=databricks (and the DATABRICKS_* variables) to write to Unity Catalog.")
    import psycopg

    url = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(url, sslmode="require", options="-c default_transaction_read_only=on") as pg:
        data = transform(pg)
    print(f"{'table':40} {'rows':>8}")
    for k, rows in data.items():
        print(f"{C.TABLE_NAMES[k]:40} {len(rows):>8}")
    if args.dry_run:
        return
    db = get_db()
    order = ["users", "assessments", "dimensions", "mbi_entries", "comments", "activity_log", "dimension_collaborators",
             "dimension_invitations", "assessment_team", "unpublish_requests", "assessment_documents", "indicator_suggestions"]
    if args.truncate:
        for k in reversed(order):
            db.execute(f"DELETE FROM {C.T[k]}")
    for k in order:
        write(k, data[k], db)
        got = db.one(f"SELECT count(*) AS n FROM {C.T[k]}")["n"]
        print(f"loaded {C.TABLE_NAMES[k]:38} source={len(data[k]):>6} target={got:>6} {'OK' if got == len(data[k]) else 'MISMATCH'}")
    if args.files:
        print("files copied:", copy_files(data["assessment_documents"]))


if __name__ == "__main__":
    main()
