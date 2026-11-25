"""
Notebook cell 2 of 2 (Python) — load the Supabase JSON export into the UC tables.

Run this cell right after 01_create_uc_tables.sql (cell 1). It reads the
per-table JSON files written by migration.py from SOURCE_DIR and REPLACES the
contents of each infragov_* table (INSERT OVERWRITE), so it is safe to re-run.

On the way it applies the same transforms as migrate_supabase_to_uc.py:
  * auth_users.json + profiles.json → infragov_users (preferences → 4 booleans)
  * arrays / JSON objects → JSON strings
  * invitation tokens → SHA-256 (plaintext tokens are NOT loaded)
  * phone / result_detail / extracted_text → AES-256-GCM (enc:v1:) when a key is set
  * mbi_entries & dimension_collaborators gain assessment_id
  * uploaded documents in SOURCE_DIR/files/<storage_path> are size-checked,
    hashed into assessment_documents.sha256 and copied to the infragov_documents volume
Column types come from the tables themselves, so the two cells stay in sync.
Everything (rows and files) is checked before anything is written.

Before running: create the FIELD_ENCRYPTION_KEY secret with 01a_create_encryption_secret.py
and give Posit Connect the SAME value.
Settings are notebook widgets (source folder, secret scope, encryption, dry run).
The dry_run widget starts at "yes": check the output, then switch it to "no" to load.
"""
import base64
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone

from pyspark.sql.types import BooleanType, IntegerType, LongType, StringType, TimestampType

TARGET = "prd_mega.sgpbpi163"  # fixed: must match cell 1 and constants.py
DOCUMENT_VOLUME = "/Volumes/prd_mega/sgpbpi163/pimpam_policy/PIMPAM-AI/infragov_documents/"  # fixed: the app reads documents only from here

# Settings appear as widgets at the top of the notebook.
widgets = dbutils.widgets  # noqa: F821 - notebook global
widgets.text("source_dir", "/Volumes/prd_mega/sgpbpi163/pimpam_policy/PIMPAM-AI/infra-gov", "Source folder (JSON export)")
widgets.text("secret_scope", "infragov", "Secret scope")
widgets.dropdown("encrypt_fields", "yes", ["yes", "no"], "Encrypt sensitive fields")
widgets.dropdown("dry_run", "yes", ["yes", "no"], "Dry run (validate only)")
SOURCE_DIR = widgets.get("source_dir").strip().rstrip("/")
# (scope, key) of FIELD_ENCRYPTION_KEY; None loads those fields as plaintext (the app encrypts them on next save).
ENCRYPTION_SECRET = (widgets.get("secret_scope").strip(), "FIELD_ENCRYPTION_KEY") if widgets.get("encrypt_fields") == "yes" else None
DRY_RUN = widgets.get("dry_run") == "yes"
print(f"source: {SOURCE_DIR} | encryption: {'/'.join(ENCRYPTION_SECRET) if ENCRYPTION_SECRET else 'OFF'} | dry run: {DRY_RUN}\n")

# Load order (parents first). Every key maps to prd_mega.sgpbpi163.infragov_<key>.
TABLES = ["users", "assessments", "dimensions", "mbi_entries", "comments", "activity_log", "dimension_collaborators",
          "dimension_invitations", "assessment_team", "unpublish_requests", "assessment_documents", "indicator_suggestions"]
# Source fields that are transformed into other columns (not reported as dropped).
CONSUMED = {"users": {"preferences"}, "dimension_invitations": {"token"}}

# ---------------------------------------------------------------- encryption (mirrors services/crypto.py)
_PREFIX = "enc:v1:"
_aesgcm = None
if ENCRYPTION_SECRET:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        _key_b64 = dbutils.secrets.get(*ENCRYPTION_SECRET)  # noqa: F821 - notebook global
    except Exception as e:  # noqa: BLE001 - dbutils raises a Java-side IllegalArgumentException
        raise RuntimeError(
            f"Secret {ENCRYPTION_SECRET[1]!r} not found in scope {ENCRYPTION_SECRET[0]!r}. Run the "
            "01a_create_encryption_secret.py cell first and set the same value in Posit Connect. "
            "Or set the 'Encrypt sensitive fields' widget to 'no' to load those fields as plaintext."
        ) from e
    _key = base64.urlsafe_b64decode(_key_b64 + "=" * (-len(_key_b64) % 4))
    if len(_key) != 32:
        raise ValueError("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes")
    _aesgcm = AESGCM(_key)
else:
    print("WARNING: no encryption key - phone / result_detail / extracted_text are loaded as plaintext.")


def encrypt_field(plaintext):
    if not plaintext:
        return ""
    if _aesgcm is None or plaintext.startswith(_PREFIX):
        return plaintext
    nonce = os.urandom(12)
    ct = _aesgcm.encrypt(nonce, plaintext.encode("utf-8"), b"infragov")
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")


def sha256_hex(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- type coercion (driven by the table schema)
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}(?::?\d{2})?)?$")


def parse_ts(v):
    """Supabase ISO strings ('...18215Z', '...+00:00', 1-9 fraction digits) → aware UTC datetime."""
    m = _TS.match(v.strip())
    if not m:
        raise ValueError(f"Unrecognised timestamp: {v!r}")
    day, clock, frac, tz = m.groups()
    if tz in (None, "Z"):
        tz = "+00:00"
    elif len(tz) == 3:
        tz += ":00"
    elif ":" not in tz:
        tz = f"{tz[:3]}:{tz[3:]}"
    dt = datetime.fromisoformat(f"{day}T{clock}.{(frac or '0')[:6].ljust(6, '0')}{tz}")
    return dt.astimezone(timezone.utc)


def coerce(value, dtype):
    if value is None:
        return None
    if isinstance(dtype, TimestampType):
        return value if isinstance(value, datetime) else parse_ts(value)
    if isinstance(dtype, (IntegerType, LongType)):
        return int(value)
    if isinstance(dtype, BooleanType):
        return bool(value)
    if isinstance(dtype, StringType):
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    return value


# ---------------------------------------------------------------- source → target rows
def load(name):
    with open(f"{SOURCE_DIR}/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def transform(src):
    now = datetime.now(timezone.utc)
    auth = {u["id"]: u for u in src["auth_users"]}
    users = []
    for p in src["profiles"]:
        a = auth.get(p["id"])
        if a is None:
            print(f"  skipped profile {p['id']}: no matching auth user")
            continue
        prefs = p.get("preferences") or {}
        banned = parse_ts(a["banned_until"]) if a.get("banned_until") else None
        users.append({
            "id": p["id"], "email": (a.get("email") or p.get("email") or "").lower(),
            "password_hash": a.get("encrypted_password") or None,
            "name": p.get("name") or "", "organisation": p.get("organisation") or "", "country": p.get("country") or "",
            "job_title": p.get("job_title") or "", "phone": encrypt_field(p.get("phone") or ""), "role": p.get("role"),
            "pref_email_notifications": prefs.get("emailNotifications", True),
            "pref_weekly_digest": prefs.get("weeklyDigest", True),
            "pref_invite_notifications": prefs.get("inviteNotifications", True),
            "pref_publication_notifications": prefs.get("publicationNotifications", True),
            "is_active": banned is None or banned < now,
            "email_confirmed_at": a.get("email_confirmed_at"), "failed_login_count": 0, "locked_until": None,
            "last_login_at": a.get("last_sign_in_at"), "password_changed_at": None,
            "created_at": p.get("created_at") or a.get("created_at"), "updated_at": p.get("updated_at") or a.get("created_at"),
        })

    dim_to_a = {d["id"]: d["assessment_id"] for d in src["dimensions"]}
    return {
        "users": users,
        "assessments": [{**r, "kind": r.get("kind") or "infragov", "department": r.get("department") or "",
                         "fiscal_years": r.get("fiscal_years") or []} for r in src["assessments"]],
        "dimensions": src["dimensions"],
        "mbi_entries": [{**r, "assessment_id": dim_to_a.get(r["dimension_id"]), "key_respondents": r.get("key_respondents") or [],
                         "data_source": r.get("data_source") or "", "result_summary": r.get("result_summary") or "",
                         "result_detail": encrypt_field(r.get("result_detail") or ""), "files": r.get("files") or []}
                        for r in src["mbi_entries"]],
        "comments": src["comments"],
        "activity_log": [{**r, "ai_assisted": bool(r.get("ai_assisted"))} for r in src["activity_log"]],
        "dimension_collaborators": [{**r, "assessment_id": dim_to_a.get(r["dimension_id"])} for r in src["dimension_collaborators"]],
        "dimension_invitations": [{**r, "token_hash": sha256_hex(r["token"]) if r.get("token") else None,
                                   "email": (r.get("email") or "").lower()} for r in src["dimension_invitations"]],
        "assessment_team": src["assessment_team"],
        "unpublish_requests": src["unpublish_requests"],
        "assessment_documents": [{**r, "sha256": None, "extracted_text": encrypt_field(r.get("extracted_text") or "") or None}
                                 for r in src["assessment_documents"]],
        "indicator_suggestions": [{**r, "document_ids": r.get("document_ids") or []} for r in src["indicator_suggestions"]],
    }


SOURCE_FILES = {"users": "profiles"}  # source file whose fields feed each table (for the dropped-columns report)
names = ["auth_users"] + [SOURCE_FILES.get(t, t) for t in TABLES]
src = {n: load(n) for n in names}
data = transform(src)
errors = []

# ---------------------------------------------------------------- uploaded documents (from migration.py --files)
files_dir = f"{SOURCE_DIR}/files"
copies = []  # (source file, path inside DOCUMENT_VOLUME)
if os.path.isdir(files_dir):
    by_name = {}  # fallback for folder uploads that arrive flattened; file names are unique UUIDs
    for root, _, fnames in os.walk(files_dir):
        for n in fnames:
            by_name.setdefault(n, []).append(os.path.join(root, n))
    for d in data["assessment_documents"]:
        rel = (d.get("storage_path") or "").lstrip("/")
        if not rel or ".." in rel.split("/"):
            errors.append(f"document {d['id']}: unsafe storage_path {rel!r}")
            continue
        path = f"{files_dir}/{rel}"
        if not os.path.isfile(path):
            found = by_name.get(os.path.basename(rel), [])
            if len(found) != 1:
                errors.append(f"document {d['id']}: {rel} not found in {files_dir}" + (" (name is ambiguous)" if found else ""))
                continue
            path = found[0]
        with open(path, "rb") as f:
            blob = f.read()
        if len(blob) != d["size_bytes"]:
            errors.append(f"document {d['id']}: {rel} is {len(blob)} bytes, expected {d['size_bytes']} (incomplete upload?)")
            continue
        d["sha256"] = hashlib.sha256(blob).hexdigest()
        copies.append((path, rel))
    print(f"documents: {len(copies)} of {len(data['assessment_documents'])} files found and size-checked in {files_dir}\n")
else:
    print(f"documents: no {files_dir} folder - files will NOT be copied (export with: python migration.py --files)\n")

# ---------------------------------------------------------------- validate every row before writing anything
prepared = {}
for key in TABLES:
    fq = f"{TARGET}.infragov_{key}"
    schema = spark.table(fq).schema  # noqa: F821 - notebook global
    cols = {f.name for f in schema.fields}
    dropped = {k for r in src[SOURCE_FILES.get(key, key)] for k in r} - cols - CONSUMED.get(key, set())
    rows = []
    for r in data[key]:
        try:
            row = tuple(coerce(r.get(f.name), f.dataType) for f in schema.fields)
        except (TypeError, ValueError) as e:
            errors.append(f"{fq} id={r.get('id')}: {e}")
            continue
        missing = [f.name for f, v in zip(schema.fields, row) if v is None and not f.nullable]
        if missing:
            errors.append(f"{fq} id={r.get('id')}: NULL in NOT NULL column(s) {', '.join(missing)}")
        rows.append(row)
    prepared[key] = (fq, schema, rows)
    note = f"  (source fields not loaded: {', '.join(sorted(dropped))})" if dropped else ""
    print(f"{fq:58} {len(rows):>6} rows{note}")

if errors:
    raise ValueError(f"{len(errors)} problem(s) found - nothing was written:\n" + "\n".join(errors[:50]))

if DRY_RUN:
    print("\nDry run: validation passed, nothing written. Set the 'Dry run' widget to 'no' to load.")
else:
    print()
    for path, rel in copies:  # files first, so every document row that appears already has its file
        dest = f"{DOCUMENT_VOLUME}/{rel}"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(path, dest)
        if os.path.getsize(dest) != os.path.getsize(path):
            raise IOError(f"copy of {rel} to {dest} is incomplete")
    if copies:
        print(f"documents copied to {DOCUMENT_VOLUME}: {len(copies)}\n")

    for key in TABLES:
        fq, schema, rows = prepared[key]
        spark.createDataFrame(rows, schema).write.insertInto(fq, overwrite=True)  # noqa: F821
        got = spark.table(fq).count()  # noqa: F821
        print(f"loaded {fq:52} source={len(rows):>6} target={got:>6} {'OK' if got == len(rows) else 'MISMATCH'}")

    no_password = sum(1 for u in data["users"] if not u["password_hash"])
    if no_password:
        print(f"{no_password} user(s) have no password hash; send them a set-password link (Admin > Users > Reset link).")
