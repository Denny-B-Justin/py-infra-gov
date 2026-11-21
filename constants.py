"""
constants.py — single source of truth for deployment-level constants.

Everything that changes between environments (hosts, IDs, secrets) is read
from environment variables. Nothing secret is ever hard-coded here; the
defaults below are safe placeholders. See `.env.sample` for the full list.

Table names are fixed (not environment-driven) so that every SQL statement
in the app refers to a known, validated identifier. User input is NEVER
interpolated into SQL — only these constants are, and they are checked
against a strict identifier pattern at import time.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Local .env loading (development only). On Posit Connect, set the variables
# in the content's "Vars" panel instead — never deploy a .env file.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
try:  # pragma: no cover - optional in production
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except Exception:  # noqa: BLE001
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_NAME = "InfraGov Assessment Tool"
APP_TITLE = "InfraGov MBT — Maturity Benchmarking Tool"
APP_DESCRIPTION = "InfraGov 2.0 Public Investment Management Maturity Benchmarking Platform"
APP_VERSION = "1.5.1"
PYTHON_VERSION = "3.11.9"

# "production" | "development". Production hard-disables every debug feature.
APP_ENV = _env("APP_ENV", "production").lower()
IS_PRODUCTION = APP_ENV != "development"
# Debug mode is OFF unless explicitly enabled in development. It can never be
# switched on in production, even if DASH_DEBUG is set.
DEBUG = (not IS_PRODUCTION) and _env_bool("DASH_DEBUG", False)

# Public base URL of the deployed app (used for links in e-mails and for the
# CSRF origin allow-list), e.g. https://connect.example.org/content/<guid>/
APP_BASE_URL = _env("APP_BASE_URL", "")
# Extra origins allowed to POST to the app (comma separated). Leave empty for
# same-origin only — this is the recommended CORS posture.
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in _env("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Flask session signing key — REQUIRED in production (>= 32 random bytes).
SECRET_KEY = _env("SECRET_KEY", "")
# AES-256-GCM key (urlsafe base64, 32 bytes) for field-level encryption of
# sensitive columns at rest. REQUIRED in production.
FIELD_ENCRYPTION_KEY = _env("FIELD_ENCRYPTION_KEY", "")

DEFAULT_LOCALE = "en"
LOCALES = ("en", "fr", "es", "pt")
LOCALE_LABELS = {"en": "English", "fr": "Français", "es": "Español", "pt": "Português"}

# ---------------------------------------------------------------------------
# Database backend
#   databricks — Azure Databricks Unity Catalog (production)
#   sqlite     — local file database for development only
# ---------------------------------------------------------------------------
DB_BACKEND = _env("DB_BACKEND", "databricks").lower()
SQLITE_PATH = _env("SQLITE_PATH", str(BASE_DIR / ".local" / "infragov.sqlite3"))
LOCAL_STORAGE_DIR = _env("LOCAL_STORAGE_DIR", str(BASE_DIR / ".local" / "documents"))

# Azure Databricks connection (service principal, OAuth machine-to-machine).
DATABRICKS_SERVER_HOSTNAME = _env("DATABRICKS_SERVER_HOSTNAME")  # adb-xxxxxxxx.azuredatabricks.net
DATABRICKS_HTTP_PATH = _env("DATABRICKS_HTTP_PATH")              # /sql/1.0/warehouses/<id>
DATABRICKS_CLIENT_ID = _env("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = _env("DATABRICKS_CLIENT_SECRET")
# "databricks-oauth" → secret generated in Databricks (Account console → SP → Secrets)
# "azure-client-secret" → Microsoft Entra ID app-registration secret (needs tenant id)
DATABRICKS_AUTH_TYPE = _env("DATABRICKS_AUTH_TYPE", "databricks-oauth").lower()
AZURE_TENANT_ID = _env("AZURE_TENANT_ID")

# Unity Catalog location of every table this app uses.
UC_CATALOG = "prd_mega"
UC_SCHEMA = "sgpbpi163"
UC_TABLE_PREFIX = "infragov_"

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _fq(table: str) -> str:
    """Fully-qualified, validated UC table name (catalog.schema.table)."""
    for part in (UC_CATALOG, UC_SCHEMA, table):
        if not _IDENT.match(part):
            raise ValueError(f"Invalid SQL identifier: {part!r}")
    if DB_BACKEND == "sqlite":
        return table
    return f"`{UC_CATALOG}`.`{UC_SCHEMA}`.`{table}`"


# ---------------------------------------------------------------------------
# Table names (ideal names to use when migrating the Supabase data).
#   Supabase source                       → Unity Catalog table
#   auth.users + public.profiles          → infragov_users
#   (new) server-side sessions            → infragov_user_sessions
#   (new) reset / invite password tokens  → infragov_auth_tokens
#   public.assessments                    → infragov_assessments
#   public.dimensions                     → infragov_dimensions
#   public.mbi_entries                    → infragov_mbi_entries
#   public.comments                       → infragov_comments
#   public.activity_log                   → infragov_activity_log
#   public.dimension_collaborators        → infragov_dimension_collaborators
#   public.dimension_invitations          → infragov_dimension_invitations
#   public.assessment_team                → infragov_assessment_team
#   public.unpublish_requests             → infragov_unpublish_requests
#   public.assessment_documents           → infragov_assessment_documents
#   public.indicator_suggestions          → infragov_indicator_suggestions
#   (new) security audit trail            → infragov_security_events
#   storage bucket assessment-documents   → UC Volume infragov_documents
# ---------------------------------------------------------------------------
TABLE_NAMES = {
    "users": f"{UC_TABLE_PREFIX}users",
    "sessions": f"{UC_TABLE_PREFIX}user_sessions",
    "auth_tokens": f"{UC_TABLE_PREFIX}auth_tokens",
    "assessments": f"{UC_TABLE_PREFIX}assessments",
    "dimensions": f"{UC_TABLE_PREFIX}dimensions",
    "mbi_entries": f"{UC_TABLE_PREFIX}mbi_entries",
    "comments": f"{UC_TABLE_PREFIX}comments",
    "activity_log": f"{UC_TABLE_PREFIX}activity_log",
    "dimension_collaborators": f"{UC_TABLE_PREFIX}dimension_collaborators",
    "dimension_invitations": f"{UC_TABLE_PREFIX}dimension_invitations",
    "assessment_team": f"{UC_TABLE_PREFIX}assessment_team",
    "unpublish_requests": f"{UC_TABLE_PREFIX}unpublish_requests",
    "assessment_documents": f"{UC_TABLE_PREFIX}assessment_documents",
    "indicator_suggestions": f"{UC_TABLE_PREFIX}indicator_suggestions",
    "security_events": f"{UC_TABLE_PREFIX}security_events",
}
# Fully-qualified names used in SQL (e.g. `prd_mega`.`sgpbpi163`.`infragov_users`).
T = {key: _fq(name) for key, name in TABLE_NAMES.items()}

# UC Volume that replaces the Supabase Storage bucket "assessment-documents".
UC_DOCUMENT_VOLUME = f"{UC_TABLE_PREFIX}documents"
UC_VOLUME_PATH = f"/Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_DOCUMENT_VOLUME}"

# ---------------------------------------------------------------------------
# Authentication & session security
# ---------------------------------------------------------------------------
# "__Secure-" prefix: browser only accepts it over HTTPS. Not "__Host-" because
# the cookie Path is scoped to the Posit Connect content path (see app.py), so
# other content on the same Connect host never receives it.
SESSION_COOKIE_NAME = "__Secure-infragov" if IS_PRODUCTION else "infragov_session"
SESSION_IDLE_TIMEOUT_MIN = _env_int("SESSION_IDLE_TIMEOUT_MIN", 30)
SESSION_ABSOLUTE_TIMEOUT_HOURS = _env_int("SESSION_ABSOLUTE_TIMEOUT_HOURS", 12)
SESSION_CACHE_TTL_SEC = 60  # in-process cache of session validation

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128  # bounded to stop hash-DoS with huge inputs
LOGIN_MAX_FAILURES = 5          # per account before temporary lockout
LOGIN_LOCKOUT_MINUTES = 15
LOGIN_RATE_PER_IP = (10, 300)   # 10 attempts / 5 minutes / IP
RESET_RATE_PER_IP = (5, 900)    # 5 requests / 15 minutes / IP
AI_RATE_PER_USER = (60, 3600)   # 60 AI calls / hour / user
RESET_TOKEN_TTL_MIN = 60
INVITE_SET_PASSWORD_TTL_HOURS = 72
DIMENSION_INVITE_TTL_DAYS = 14

EMAIL_MAX_LENGTH = 254
# Allow-list pattern for the username (e-mail) field. Deliberately stricter
# than RFC 5322: no quotes, spaces, semicolons, comment or SQL meta characters.
EMAIL_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9_%+-])?@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,63}$"

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_ADMIN = "Admin"
ROLE_OWNER = "Owner"
ROLE_CONTRIBUTOR = "Contributor"
ROLE_REVIEWER = "Reviewer"
ROLE_VIEWER = "Viewer"
PLATFORM_ROLES = (ROLE_ADMIN, ROLE_OWNER, ROLE_CONTRIBUTOR, ROLE_REVIEWER, ROLE_VIEWER)
COLLAB_ROLES = (ROLE_CONTRIBUTOR, ROLE_REVIEWER, ROLE_VIEWER)
CREATABLE_USER_ROLES = (ROLE_OWNER, ROLE_ADMIN)  # admin "Add a user" form

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------
FRAMEWORKS = ("infragov", "pagfa")
DIMENSION_STATUSES = ("Draft", "Validated", "Published")
MBI_STATUSES = ("complete", "in-progress", "untouched")
MATURITY_LEVELS = ("Incipient", "Nascent", "Emerging", "Advanced")
UNPUBLISH_STATUSES = ("Pending", "Approved", "Denied")
INVITATION_STATUSES = ("Pending", "Accepted", "Revoked", "Expired")
DOCUMENT_STATUSES = ("processing", "ready", "failed")
ACTIVITY_TYPES = (
    "assessment.created", "collaborator.added", "collaborator.roleChanged",
    "collaborator.removed", "dimension.published", "dimension.unpublished",
    "dimension.imported", "mbi.updated", "unpublish.requested",
    "unpublish.approved", "unpublish.denied", "document.uploaded", "document.deleted",
)

FIELD_LIMITS = {
    "keyRespondent": 100,
    "dataSource": 100,
    "resultSummary": 200,
    "resultDetail": 2000,
    "comment": 2000,
    "unpublishReason": 500,
    "reviewNote": 400,
    "department": 200,
    "description": 2000,
    "name": 120,
    "organisation": 120,
    "jobTitle": 120,
    "phone": 40,
}

# Source documents (replacement for the Supabase Storage bucket).
DOCUMENT_MAX_BYTES = 50 * 1024 * 1024
DOCUMENT_ALLOWED_EXT = ("pdf", "docx", "xlsx", "xls", "csv")
DOCUMENT_MAX_EXTRACTED_CHARS = 1_500_000
ZIP_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024  # zip-bomb guard for docx/xlsx
# Flask request cap: base64 upload overhead (~4/3) + JSON envelope.
MAX_CONTENT_LENGTH = int(DOCUMENT_MAX_BYTES * 1.4) + 1024 * 1024

# ---------------------------------------------------------------------------
# AI (Anthropic) — optional. Features are hidden when no key is set.
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
AI_REFINE_MODEL = _env("AI_REFINE_MODEL", "claude-haiku-4-5-20251001")
AI_SUGGEST_MODEL = _env("AI_SUGGEST_MODEL", "claude-sonnet-5-5")
AI_REFINE_MAX_INPUT = 8000
AI_CONTEXT_BUDGET_CHARS = 240_000
AI_ENABLED = bool(ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Outbound e-mail (password reset / invitations) — optional SMTP.
# ---------------------------------------------------------------------------
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USERNAME = _env("SMTP_USERNAME")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM = _env("SMTP_FROM", "InfraGov Assessment Tool <no-reply@pim-pam.net>")
SMTP_ENABLED = bool(SMTP_HOST and SMTP_FROM)

# ---------------------------------------------------------------------------
# External links
# ---------------------------------------------------------------------------
PIM_PAM_URL = "https://pim-pam.net"
FEEDBACK_EMAIL = "infragov@pim-pam.net"


def validate_runtime_config() -> list[str]:
    """Return a list of fatal configuration problems (empty == OK)."""
    problems: list[str] = []
    if IS_PRODUCTION:
        if len(SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set to at least 32 random characters.")
        if not FIELD_ENCRYPTION_KEY:
            problems.append("FIELD_ENCRYPTION_KEY must be set (32-byte urlsafe base64).")
        if DB_BACKEND != "databricks":
            problems.append("DB_BACKEND must be 'databricks' in production.")
    if DB_BACKEND == "databricks":
        for name in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH",
                     "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET"):
            if not globals()[name]:
                problems.append(f"{name} is required when DB_BACKEND=databricks.")
        if DATABRICKS_AUTH_TYPE == "azure-client-secret" and not AZURE_TENANT_ID:
            problems.append("AZURE_TENANT_ID is required when DATABRICKS_AUTH_TYPE=azure-client-secret.")
    elif DB_BACKEND != "sqlite":
        problems.append("DB_BACKEND must be 'databricks' or 'sqlite'.")
    return problems
