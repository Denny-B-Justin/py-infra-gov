"""
Logical schema — the single source of truth for both backends.

`SCHEMA` drives:
  * the SQLite DDL used for local development (``SQLITE_DDL``), and
  * the Unity Catalog DDL in ``migration/01_create_uc_tables.sql``
    (regenerate with ``python manage.py print-uc-ddl``).

Notes on the Supabase → Unity Catalog mapping
  * UUID        → STRING (lower-case canonical UUID text)
  * TIMESTAMPTZ → TIMESTAMP (stored in UTC)
  * TEXT[] / INT[] arrays → STRING holding a JSON array (e.g. '["a","b"]')
  * JSONB       → STRING holding JSON (profiles.preferences is flattened
                  into four BOOLEAN columns instead)
  * ENUM types  → STRING + CHECK constraint
  * PRIMARY KEY / FOREIGN KEY in UC are informational (not enforced), so the
    application enforces uniqueness and performs cascading deletes itself.
"""
from __future__ import annotations

import constants as C

# (column, unity-catalog type, NOT NULL?, comment)
Col = tuple[str, str, bool, str]

SCHEMA: dict[str, dict] = {
    "users": {
        "comment": "Platform users (replaces Supabase auth.users + public.profiles).",
        "cols": [
            ("id", "STRING", True, "UUID; same value as Supabase auth.users.id / profiles.id"),
            ("email", "STRING", True, "Lower-case login e-mail (unique)"),
            ("password_hash", "STRING", False, "argon2id hash; migrated bcrypt ($2a$) hashes are re-hashed on next login"),
            ("name", "STRING", True, ""),
            ("organisation", "STRING", True, ""),
            ("country", "STRING", True, ""),
            ("job_title", "STRING", True, ""),
            ("phone", "STRING", True, "Encrypted at rest (AES-256-GCM, prefix enc:v1:)"),
            ("role", "STRING", True, "Admin | Owner | Contributor | Reviewer | Viewer"),
            ("pref_email_notifications", "BOOLEAN", True, ""),
            ("pref_weekly_digest", "BOOLEAN", True, ""),
            ("pref_invite_notifications", "BOOLEAN", True, ""),
            ("pref_publication_notifications", "BOOLEAN", True, ""),
            ("is_active", "BOOLEAN", True, "False = account disabled"),
            ("email_confirmed_at", "TIMESTAMP", False, ""),
            ("failed_login_count", "INT", True, "Consecutive failed logins (lockout)"),
            ("locked_until", "TIMESTAMP", False, "Temporary lockout end"),
            ("last_login_at", "TIMESTAMP", False, ""),
            ("password_changed_at", "TIMESTAMP", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["email"]],
        "checks": {"role_valid": "role IN ('Admin','Owner','Contributor','Reviewer','Viewer')"},
    },
    "sessions": {
        "comment": "Server-side login sessions (only a SHA-256 of the session id is stored).",
        "cols": [
            ("session_hash", "STRING", True, "SHA-256 of the random session id held in the signed cookie"),
            ("user_id", "STRING", True, ""),
            ("created_at", "TIMESTAMP", True, ""),
            ("last_seen_at", "TIMESTAMP", True, ""),
            ("expires_at", "TIMESTAMP", True, "Absolute expiry"),
            ("user_agent", "STRING", True, "Truncated user agent"),
            ("revoked_at", "TIMESTAMP", False, ""),
        ],
        "pk": ["session_hash"],
        "unique": [],
        "checks": {},
    },
    "auth_tokens": {
        "comment": "Single-use password reset / set-password tokens (hash only).",
        "cols": [
            ("token_hash", "STRING", True, "SHA-256 of the token sent by e-mail"),
            ("user_id", "STRING", True, ""),
            ("purpose", "STRING", True, "reset | invite"),
            ("created_at", "TIMESTAMP", True, ""),
            ("expires_at", "TIMESTAMP", True, ""),
            ("used_at", "TIMESTAMP", False, ""),
        ],
        "pk": ["token_hash"],
        "unique": [],
        "checks": {"purpose_valid": "purpose IN ('reset','invite')"},
    },
    "assessments": {
        "comment": "Top-level assessment container (one per country / framework / FY).",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("kind", "STRING", True, "infragov | pagfa"),
            ("title", "STRING", True, ""),
            ("country", "STRING", True, ""),
            ("department", "STRING", True, ""),
            ("description", "STRING", False, ""),
            ("fiscal_years", "STRING", True, "JSON array of FY labels, e.g. [\"25/26\"]"),
            ("owner_user_id", "STRING", True, "FK → infragov_users.id"),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [],
        "checks": {"kind_valid": "kind IN ('infragov','pagfa')"},
    },
    "dimensions": {
        "comment": "16 InfraGov dimensions / 8 PAG-FA pillars per assessment.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, "FK → infragov_assessments.id"),
            ("dim_id", "INT", True, "1-16 (InfraGov) or 1-8 (PAG-FA)"),
            ("status", "STRING", True, "Draft | Validated | Published"),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["assessment_id", "dim_id"]],
        "checks": {"status_valid": "status IN ('Draft','Validated','Published')",
                   "dim_range": "dim_id BETWEEN 1 AND 16"},
    },
    "mbi_entries": {
        "comment": "Indicator (MBI) answers.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("dimension_id", "STRING", True, "FK → infragov_dimensions.id"),
            ("assessment_id", "STRING", True, "Denormalised FK → infragov_assessments.id (new column)"),
            ("mbi_code", "STRING", True, "e.g. D3.2"),
            ("key_respondents", "STRING", True, "JSON array of strings"),
            ("data_source", "STRING", True, ""),
            ("result_summary", "STRING", True, ""),
            ("result_detail", "STRING", True, "Internal-only; encrypted at rest (enc:v1:)"),
            ("maturity_benchmark", "STRING", False, "Incipient | Nascent | Emerging | Advanced"),
            ("score", "INT", False, "1-4"),
            ("files", "STRING", True, "JSON array of attached file names"),
            ("status", "STRING", True, "complete | in-progress | untouched"),
            ("last_edited_by", "STRING", False, "FK → infragov_users.id"),
            ("last_edited_at", "TIMESTAMP", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["dimension_id", "mbi_code"]],
        "checks": {"score_range": "score IS NULL OR score BETWEEN 1 AND 4",
                   "status_valid": "status IN ('complete','in-progress','untouched')"},
    },
    "comments": {
        "comment": "Dimension-level and per-indicator comment threads.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("dimension_id", "STRING", True, ""),
            ("mbi_code", "STRING", False, "NULL for dimension-level threads"),
            ("author_user_id", "STRING", True, ""),
            ("author_name", "STRING", True, ""),
            ("text", "STRING", True, ""),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", False, "Set when edited"),
        ],
        "pk": ["id"],
        "unique": [],
        "checks": {},
    },
    "activity_log": {
        "comment": "Audit trail per assessment.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("type", "STRING", True, "activity type, e.g. mbi.updated"),
            ("actor_user_id", "STRING", True, ""),
            ("actor_name", "STRING", True, ""),
            ("actor_organisation", "STRING", False, ""),
            ("target_user_id", "STRING", False, ""),
            ("target_name", "STRING", False, ""),
            ("dim_id", "INT", False, ""),
            ("dimension_name", "STRING", False, ""),
            ("dimension_ids", "STRING", False, "JSON array of ints"),
            ("mbi_code", "STRING", False, ""),
            ("fields_changed", "STRING", False, "JSON array of strings"),
            ("import_source", "STRING", False, "docx | pdf"),
            ("document_name", "STRING", False, ""),
            ("ai_assisted", "BOOLEAN", True, ""),
            ("from_role", "STRING", False, ""),
            ("to_role", "STRING", False, ""),
            ("reason", "STRING", False, ""),
            ("review_note", "STRING", False, ""),
            ("request_id", "STRING", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [],
        "checks": {},
    },
    "dimension_collaborators": {
        "comment": "Per-dimension role assignments.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("dimension_id", "STRING", True, ""),
            ("assessment_id", "STRING", True, "Denormalised (new column)"),
            ("user_id", "STRING", True, ""),
            ("role", "STRING", True, "Contributor | Reviewer | Viewer"),
            ("invited_by", "STRING", True, ""),
            ("invited_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["dimension_id", "user_id"]],
        "checks": {"role_valid": "role IN ('Contributor','Reviewer','Viewer')"},
    },
    "dimension_invitations": {
        "comment": "Pending per-dimension invitations (token stored as SHA-256 only).",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("token_hash", "STRING", True, "SHA-256 of the invitation token (Supabase stored plaintext)"),
            ("assessment_id", "STRING", True, ""),
            ("dimension_id", "STRING", True, ""),
            ("email", "STRING", True, "Invitee e-mail; must match the accepting account"),
            ("role", "STRING", True, ""),
            ("organisation", "STRING", False, ""),
            ("invited_by", "STRING", True, ""),
            ("status", "STRING", True, "Pending | Accepted | Revoked | Expired"),
            ("accepted_user_id", "STRING", False, ""),
            ("accepted_at", "TIMESTAMP", False, ""),
            ("expires_at", "TIMESTAMP", True, ""),
            ("created_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["token_hash"]],
        "checks": {"status_valid": "status IN ('Pending','Accepted','Revoked','Expired')"},
    },
    "assessment_team": {
        "comment": "Denormalised team list per assessment.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("user_id", "STRING", True, ""),
            ("role", "STRING", True, "Owner | Contributor | Reviewer | Viewer"),
            ("organisation", "STRING", False, ""),
            ("joined_at", "TIMESTAMP", True, ""),
            ("last_activity", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["assessment_id", "user_id"]],
        "checks": {},
    },
    "unpublish_requests": {
        "comment": "Owner-initiated unpublish requests awaiting Admin review.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("dimension_id", "STRING", True, ""),
            ("requested_by_user_id", "STRING", True, ""),
            ("requested_by_name", "STRING", True, ""),
            ("requested_by_email", "STRING", True, ""),
            ("reason", "STRING", True, ""),
            ("status", "STRING", True, "Pending | Approved | Denied"),
            ("reviewed_by_user_id", "STRING", False, ""),
            ("reviewed_by_name", "STRING", False, ""),
            ("reviewed_at", "TIMESTAMP", False, ""),
            ("review_note", "STRING", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [],
        "checks": {"status_valid": "status IN ('Pending','Approved','Denied')"},
    },
    "assessment_documents": {
        "comment": "Source documents; files live in the UC Volume infragov_documents.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("filename", "STRING", True, "Sanitised original file name"),
            ("mime_type", "STRING", False, ""),
            ("size_bytes", "BIGINT", True, ""),
            ("storage_path", "STRING", True, "Path inside the UC Volume"),
            ("sha256", "STRING", False, "Content hash (integrity)"),
            ("status", "STRING", True, "processing | ready | failed"),
            ("error", "STRING", False, ""),
            ("extracted_text", "STRING", False, "Encrypted at rest (enc:v1:)"),
            ("char_count", "INT", False, ""),
            ("page_count", "INT", False, ""),
            ("uploaded_by_user_id", "STRING", False, ""),
            ("uploaded_by_name", "STRING", True, ""),
            ("uploaded_by_organisation", "STRING", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
            ("updated_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["storage_path"]],
        "checks": {"status_valid": "status IN ('processing','ready','failed')"},
    },
    "indicator_suggestions": {
        "comment": "Saved AI 'Suggest Responses' drafts.",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("assessment_id", "STRING", True, ""),
            ("dimension_id", "STRING", True, ""),
            ("dim_id", "INT", True, ""),
            ("mbi_id", "INT", True, "1-based indicator number"),
            ("status", "STRING", True, "suggested | no_evidence"),
            ("suggestion", "STRING", False, "JSON draft (was JSONB)"),
            ("reason", "STRING", False, ""),
            ("locale", "STRING", True, ""),
            ("model", "STRING", False, ""),
            ("document_ids", "STRING", True, "JSON array of document ids"),
            ("drafted_by", "STRING", False, ""),
            ("drafted_by_name", "STRING", False, ""),
            ("drafted_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [["dimension_id", "mbi_id"]],
        "checks": {"status_valid": "status IN ('suggested','no_evidence')"},
    },
    "security_events": {
        "comment": "Security audit trail (logins, lockouts, admin actions).",
        "cols": [
            ("id", "STRING", True, "UUID"),
            ("event_type", "STRING", True, "login.success | login.failure | lockout | ..."),
            ("user_id", "STRING", False, ""),
            ("ip_hash", "STRING", False, "Keyed hash of the client IP (no raw IPs stored)"),
            ("detail", "STRING", False, ""),
            ("created_at", "TIMESTAMP", True, ""),
        ],
        "pk": ["id"],
        "unique": [],
        "checks": {},
    },
}

_SQLITE_TYPES = {"STRING": "TEXT", "TIMESTAMP": "TEXT", "BOOLEAN": "INTEGER", "INT": "INTEGER", "BIGINT": "INTEGER"}


def _sqlite_ddl() -> str:
    parts = []
    for key, spec in SCHEMA.items():
        name = C.TABLE_NAMES[key]
        cols = [f"  {c} {_SQLITE_TYPES[t]}{' NOT NULL' if nn else ''}" for c, t, nn, _ in spec["cols"]]
        cols.append(f"  PRIMARY KEY ({', '.join(spec['pk'])})")
        parts.append(f"CREATE TABLE IF NOT EXISTS {name} (\n" + ",\n".join(cols) + "\n);")
        for i, uq in enumerate(spec["unique"]):
            parts.append(f"CREATE UNIQUE INDEX IF NOT EXISTS {name}_uq{i} ON {name} ({', '.join(uq)});")
    idx = [
        ("dimensions", "assessment_id"), ("mbi_entries", "assessment_id"), ("comments", "assessment_id"),
        ("activity_log", "assessment_id"), ("dimension_collaborators", "user_id"),
        ("assessment_team", "user_id"), ("unpublish_requests", "status"), ("sessions", "user_id"),
    ]
    for key, col in idx:
        name = C.TABLE_NAMES[key]
        parts.append(f"CREATE INDEX IF NOT EXISTS {name}_{col}_idx ON {name} ({col});")
    return "\n".join(parts)


SQLITE_DDL = _sqlite_ddl()


def uc_ddl() -> str:
    """Unity Catalog DDL for every table (used to regenerate the migration SQL)."""
    fq = f"{C.UC_CATALOG}.{C.UC_SCHEMA}"
    out = [
        "-- ============================================================================",
        "-- InfraGov — Unity Catalog DDL (Azure Databricks)",
        f"-- Target schema: {fq}",
        "-- Generated from services/schema.py — keep the two in sync.",
        "-- Run in a Databricks SQL editor as a user with CREATE TABLE on the schema.",
        "-- ============================================================================",
        "",
        f"USE CATALOG {C.UC_CATALOG};",
        f"USE SCHEMA {C.UC_SCHEMA};",
        "",
        f"-- Volume that replaces the Supabase Storage bucket 'assessment-documents'",
        f"CREATE VOLUME IF NOT EXISTS {fq}.{C.UC_DOCUMENT_VOLUME}",
        "  COMMENT 'InfraGov source documents (migrated from Supabase Storage)';",
        "",
    ]
    for key, spec in SCHEMA.items():
        name = f"{fq}.{C.TABLE_NAMES[key]}"
        lines = []
        for c, t, nn, comment in spec["cols"]:
            cm = f" COMMENT '{comment}'" if comment else ""
            lines.append(f"  {c} {t}{' NOT NULL' if nn else ''}{cm}")
        lines.append(f"  CONSTRAINT {C.TABLE_NAMES[key]}_pk PRIMARY KEY ({', '.join(spec['pk'])})")
        out.append(f"CREATE TABLE IF NOT EXISTS {name} (\n" + ",\n".join(lines) + "\n)")
        out.append("USING DELTA")
        out.append(f"COMMENT '{spec['comment']}'")
        out.append("TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');")
        for cname, expr in spec["checks"].items():
            out.append(f"ALTER TABLE {name} ADD CONSTRAINT {cname} CHECK ({expr});")
        out.append("")
    return "\n".join(out)
