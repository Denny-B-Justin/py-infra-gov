"""
Authentication: password hashing, login, server-side sessions, reset tokens.

* Passwords are hashed with Argon2id (argon2-cffi). Hashes migrated from
  Supabase Auth (bcrypt ``$2a$``) are verified with bcrypt once and then
  transparently re-hashed to Argon2id.
* Sessions are server-side: the signed, HttpOnly, Secure, SameSite cookie
  carries only a random session id; the database stores its SHA-256, so a
  leaked table cannot be replayed. Sessions expire after inactivity and at an
  absolute limit, are rotated on login (no fixation) and revoked on logout or
  password change.
* Brute force: per-IP throttling plus per-account lockout persisted in the DB.
  Error messages never reveal whether an account exists.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any

import bcrypt
import flask
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

import constants as C
from services import ratelimit
from services.crypto import decrypt_field, keyed_hash, new_token, sha256_hex
from services.db import get_db, parse_ts, utcnow
from services.validators import ValidationError, new_uuid, validate_email, validate_password_input

log = logging.getLogger("infragov.auth")

_ph = PasswordHasher(time_cost=3, memory_cost=46 * 1024, parallelism=1, hash_len=32, salt_len=16)
_DUMMY_HASH = _ph.hash("not-a-real-password-just-for-timing")
GENERIC_LOGIN_ERROR = "Invalid email or password."

# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> tuple[bool, bool]:
    """Return (matches, needs_rehash)."""
    if not stored_hash:
        _safe_dummy(password)
        return False, False
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False, False
        return ok, ok  # always upgrade bcrypt → argon2id
    try:
        _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, _ph.check_needs_rehash(stored_hash)


def _safe_dummy(password: str) -> None:
    try:
        _ph.verify(_DUMMY_HASH, password)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- helpers


def client_ip() -> str:
    try:
        return flask.request.remote_addr or "unknown"
    except RuntimeError:
        return "unknown"


def log_security_event(event_type: str, user_id: str | None = None, detail: str = "") -> None:
    try:
        get_db().insert(C.T["security_events"], {
            "id": new_uuid(),
            "event_type": event_type[:64],
            "user_id": user_id,
            "ip_hash": keyed_hash(client_ip()),
            "detail": detail[:500],
            "created_at": utcnow(),
        })
    except Exception:  # noqa: BLE001
        log.warning("Could not write security event %s", event_type)


def _user_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row.get("name") or "",
        "organisation": row.get("organisation") or "",
        "country": row.get("country") or "",
        "jobTitle": row.get("job_title") or "",
        "phone": decrypt_field(row.get("phone")),
        "role": row.get("role") or C.ROLE_VIEWER,
        "preferences": {
            "emailNotifications": bool(row.get("pref_email_notifications")),
            "weeklyDigest": bool(row.get("pref_weekly_digest")),
            "inviteNotifications": bool(row.get("pref_invite_notifications")),
            "publicationNotifications": bool(row.get("pref_publication_notifications")),
        },
    }


def get_user_by_email(email: str) -> dict[str, Any] | None:
    return get_db().one(f"SELECT * FROM {C.T['users']} WHERE email = :email", {"email": email})


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return get_db().one(f"SELECT * FROM {C.T['users']} WHERE id = :id", {"id": user_id})


# ---------------------------------------------------------------- login


def authenticate(email_raw: str, password_raw: str) -> tuple[dict[str, Any] | None, str]:
    """Validate credentials. Returns (public_user, error_message)."""
    ip = client_ip()
    limit, window = C.LOGIN_RATE_PER_IP
    if not ratelimit.allow("login-ip", ip, limit, window):
        log_security_event("login.rate_limited")
        return None, "Too many sign-in attempts. Please wait a few minutes and try again."
    try:
        email = validate_email(email_raw)
        password = validate_password_input(password_raw)
    except ValidationError:
        _safe_dummy(str(password_raw or "")[: C.PASSWORD_MAX_LENGTH])
        return None, GENERIC_LOGIN_ERROR

    db = get_db()
    row = get_user_by_email(email)
    now = utcnow()
    if row is None:
        _safe_dummy(password)
        log_security_event("login.failure", None, "unknown account")
        return None, GENERIC_LOGIN_ERROR
    locked_until = parse_ts(row.get("locked_until"))
    if locked_until and locked_until > now:
        _safe_dummy(password)
        log_security_event("login.locked", row["id"])
        return None, "This account is temporarily locked after repeated failed sign-ins. Try again later."
    ok, needs_rehash = verify_password(row.get("password_hash"), password)
    if not ok or not row.get("is_active"):
        failures = int(row.get("failed_login_count") or 0) + 1
        values: dict[str, Any] = {"failed_login_count": failures, "updated_at": now}
        if failures >= C.LOGIN_MAX_FAILURES:
            values["locked_until"] = now + timedelta(minutes=C.LOGIN_LOCKOUT_MINUTES)
            values["failed_login_count"] = 0
            log_security_event("login.lockout", row["id"])
        db.update(C.T["users"], values, {"id": row["id"]})
        log_security_event("login.failure", row["id"])
        return None, GENERIC_LOGIN_ERROR
    values = {"failed_login_count": 0, "locked_until": None, "last_login_at": now, "updated_at": now}
    if needs_rehash:
        values["password_hash"] = hash_password(password)
    db.update(C.T["users"], values, {"id": row["id"]})
    ratelimit.reset("login-ip", ip)
    log_security_event("login.success", row["id"])
    return _user_public(row), ""


# ---------------------------------------------------------------- sessions

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def start_session(user_id: str) -> None:
    """Rotate the session (prevents fixation) and persist it server-side."""
    old = flask.session.get("sid")
    if old:
        revoke_session(old)
    flask.session.clear()
    sid = new_token(32)
    now = utcnow()
    ua = (flask.request.headers.get("User-Agent") or "")[:200]
    get_db().insert(C.T["sessions"], {
        "session_hash": sha256_hex(sid),
        "user_id": user_id,
        "created_at": now,
        "last_seen_at": now,
        "expires_at": now + timedelta(hours=C.SESSION_ABSOLUTE_TIMEOUT_HOURS),
        "user_agent": ua,
        "revoked_at": None,
    })
    flask.session.permanent = True
    flask.session["sid"] = sid
    flask.session["uid"] = user_id


def revoke_session(sid: str) -> None:
    h = sha256_hex(sid)
    with _cache_lock:
        _cache.pop(h, None)
    try:
        get_db().update(C.T["sessions"], {"revoked_at": utcnow()}, {"session_hash": h})
    except Exception:  # noqa: BLE001
        log.warning("Could not revoke session")


def revoke_all_sessions(user_id: str, except_sid: str | None = None) -> None:
    db = get_db()
    keep = sha256_hex(except_sid) if except_sid else ""
    db.execute(
        f"UPDATE {C.T['sessions']} SET revoked_at = :now WHERE user_id = :uid AND revoked_at IS NULL AND session_hash <> :keep",
        {"now": utcnow(), "uid": user_id, "keep": keep},
    )
    with _cache_lock:
        for k in [k for k, (_, v) in _cache.items() if v.get("id") == user_id and k != keep]:
            _cache.pop(k, None)


def logout() -> None:
    sid = flask.session.get("sid")
    if sid:
        revoke_session(sid)
        log_security_event("logout", flask.session.get("uid"))
    flask.session.clear()


def invalidate_user_cache(user_id: str) -> None:
    with _cache_lock:
        for k in [k for k, (_, v) in _cache.items() if v.get("id") == user_id]:
            _cache.pop(k, None)


def current_user() -> dict[str, Any] | None:
    """The signed-in user for this request, or None. Validated server-side."""
    try:
        sid = flask.session.get("sid")
    except RuntimeError:
        return None
    if not sid or not isinstance(sid, str) or len(sid) > 128:
        return None
    h = sha256_hex(sid)
    now_mono = time.monotonic()
    with _cache_lock:
        hit = _cache.get(h)
        if hit and now_mono - hit[0] < C.SESSION_CACHE_TTL_SEC:
            return hit[1]
    db = get_db()
    srow = db.one(f"SELECT * FROM {C.T['sessions']} WHERE session_hash = :h", {"h": h})
    now = utcnow()
    if (
        not srow
        or srow.get("revoked_at")
        or (parse_ts(srow["expires_at"]) or now) <= now
        or (parse_ts(srow["last_seen_at"]) or now) + timedelta(minutes=C.SESSION_IDLE_TIMEOUT_MIN) <= now
    ):
        flask.session.clear()
        return None
    urow = get_user_by_id(srow["user_id"])
    if not urow or not urow.get("is_active"):
        flask.session.clear()
        return None
    last_seen = parse_ts(srow["last_seen_at"]) or now
    if (now - last_seen).total_seconds() > 120:
        db.update(C.T["sessions"], {"last_seen_at": now}, {"session_hash": h})
    user = _user_public(urow)
    with _cache_lock:
        _cache[h] = (now_mono, user)
    return user


# ---------------------------------------------------------------- tokens


def create_auth_token(user_id: str, purpose: str, ttl: timedelta) -> str:
    raw = new_token(32)
    now = utcnow()
    get_db().insert(C.T["auth_tokens"], {
        "token_hash": sha256_hex(raw),
        "user_id": user_id,
        "purpose": purpose,
        "created_at": now,
        "expires_at": now + ttl,
        "used_at": None,
    })
    return raw


def peek_auth_token(raw: str) -> dict[str, Any] | None:
    row = get_db().one(f"SELECT * FROM {C.T['auth_tokens']} WHERE token_hash = :h", {"h": sha256_hex(raw)})
    if not row or row.get("used_at") or (parse_ts(row["expires_at"]) or utcnow()) <= utcnow():
        return None
    return row


def consume_auth_token(raw: str) -> dict[str, Any] | None:
    row = peek_auth_token(raw)
    if not row:
        return None
    get_db().update(C.T["auth_tokens"], {"used_at": utcnow()}, {"token_hash": row["token_hash"]})
    return row


def set_password(user_id: str, new_password: str) -> None:
    now = utcnow()
    get_db().update(C.T["users"], {
        "password_hash": hash_password(new_password),
        "password_changed_at": now,
        "email_confirmed_at": now,
        "failed_login_count": 0,
        "locked_until": None,
        "updated_at": now,
    }, {"id": user_id})
    invalidate_user_cache(user_id)
