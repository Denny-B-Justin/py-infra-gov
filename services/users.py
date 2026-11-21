"""User administration and self-service account management."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import constants as C
from services import auth, mailer
from services import permissions as P
from services.crypto import encrypt_field
from services.db import get_db, to_iso, utcnow
from services.repository import Forbidden
from services.validators import (
    ValidationError, clean_text, new_uuid, password_policy_errors, validate_choice, validate_email,
)
from utils.countries import country_names, profile_countries

T = C.T


def list_users(admin: dict) -> list[dict]:
    if not P.is_admin(admin):
        raise Forbidden("Admins only")
    rows = get_db().query(
        f"SELECT id, email, name, organisation, country, role, is_active, created_at, last_login_at FROM {T['users']} ORDER BY created_at DESC"
    )
    return [{**r, "created_at": to_iso(r["created_at"]), "last_login_at": to_iso(r.get("last_login_at"))} for r in rows]


def create_user(admin: dict, *, email: str, name: str, organisation: str, country: str, role: str,
                password: str | None, base_url: str) -> dict[str, Any]:
    """Admin-only. Either sets a password directly or issues a set-password link."""
    if not P.is_admin(admin):
        raise Forbidden("Only Admins can create users.")
    email = validate_email(email)
    role = validate_choice(role, C.CREATABLE_USER_ROLES)
    name = clean_text(name, C.FIELD_LIMITS["name"], multiline=False)
    organisation = clean_text(organisation, C.FIELD_LIMITS["organisation"], multiline=False)
    if country and country not in country_names():
        raise ValidationError("Select a valid country.")
    db = get_db()
    if auth.get_user_by_email(email):
        raise ValidationError(f"{email} is already registered.")
    if password:
        errs = password_policy_errors(password, email, name)
        if errs:
            raise ValidationError(" ".join(errs))
    now = utcnow()
    uid = new_uuid()
    db.insert(T["users"], {
        "id": uid, "email": email, "password_hash": auth.hash_password(password) if password else None,
        "name": name, "organisation": organisation, "country": country or "", "job_title": "", "phone": "",
        "role": role, "pref_email_notifications": True, "pref_weekly_digest": True,
        "pref_invite_notifications": True, "pref_publication_notifications": True, "is_active": True,
        "email_confirmed_at": now if password else None, "failed_login_count": 0, "locked_until": None,
        "last_login_at": None, "password_changed_at": now if password else None, "created_at": now, "updated_at": now,
    })
    auth.log_security_event("admin.user_created", admin["id"], f"role={role}")
    result: dict[str, Any] = {"id": uid, "email": email, "mode": "password" if password else "invite"}
    if not password:
        token = auth.create_auth_token(uid, "invite", timedelta(hours=C.INVITE_SET_PASSWORD_TTL_HOURS))
        link = f"{base_url}?page=reset-password&token={token}"
        sent = mailer.send(
            email, "You're invited to the InfraGov Assessment Tool",
            f"Hello{(' ' + name) if name else ''},\n\nAn administrator created an InfraGov Assessment Tool account for you.\n"
            f"Set your password here (valid for {C.INVITE_SET_PASSWORD_TTL_HOURS} hours):\n{link}\n",
        )
        result["emailSent"] = sent
        result["link"] = None if sent else link
    return result


def admin_reset_link(admin: dict, user_id: str, base_url: str) -> str:
    if not P.is_admin(admin):
        raise Forbidden("Admins only")
    if not auth.get_user_by_id(user_id):
        raise ValidationError("User not found.")
    token = auth.create_auth_token(user_id, "reset", timedelta(minutes=C.RESET_TOKEN_TTL_MIN))
    auth.log_security_event("admin.reset_link", admin["id"], f"target={user_id}")
    return f"{base_url}?page=reset-password&token={token}"


def update_profile(user: dict, form: dict) -> None:
    name = clean_text(form.get("name"), C.FIELD_LIMITS["name"], multiline=False)
    if not name:
        raise ValidationError("Full name is required.")
    country = form.get("country") or ""
    if country and country not in profile_countries() and country not in country_names():
        raise ValidationError("Select a valid country.")
    get_db().update(T["users"], {
        "name": name,
        "organisation": clean_text(form.get("organisation"), C.FIELD_LIMITS["organisation"], multiline=False),
        "country": country,
        "job_title": clean_text(form.get("jobTitle"), C.FIELD_LIMITS["jobTitle"], multiline=False),
        "phone": encrypt_field(clean_text(form.get("phone"), C.FIELD_LIMITS["phone"], multiline=False)),
        "updated_at": utcnow(),
    }, {"id": user["id"]})
    auth.invalidate_user_cache(user["id"])


def update_preferences(user: dict, prefs: dict) -> None:
    get_db().update(T["users"], {
        "pref_email_notifications": bool(prefs.get("emailNotifications")),
        "pref_weekly_digest": bool(prefs.get("weeklyDigest")),
        "pref_invite_notifications": bool(prefs.get("inviteNotifications")),
        "pref_publication_notifications": bool(prefs.get("publicationNotifications")),
        "updated_at": utcnow(),
    }, {"id": user["id"]})
    auth.invalidate_user_cache(user["id"])


def change_password(user: dict, current: str, new: str, confirm: str, current_sid: str | None) -> None:
    if new != confirm:
        raise ValidationError("New passwords do not match.")
    row = auth.get_user_by_id(user["id"])
    ok, _ = auth.verify_password((row or {}).get("password_hash"), current or "")
    if not ok:
        auth.log_security_event("password.change_failed", user["id"])
        raise ValidationError("Current password is incorrect.")
    errs = password_policy_errors(new, user["email"], user.get("name", ""))
    if errs:
        raise ValidationError(" ".join(errs))
    auth.set_password(user["id"], new)
    auth.revoke_all_sessions(user["id"], except_sid=current_sid)
    auth.log_security_event("password.changed", user["id"])


def request_password_reset(email_raw: str, base_url: str) -> None:
    """Always behaves the same whether or not the account exists."""
    try:
        email = validate_email(email_raw)
    except ValidationError:
        raise
    row = auth.get_user_by_email(email)
    if not row or not row.get("is_active"):
        auth.log_security_event("password.reset_unknown")
        return
    token = auth.create_auth_token(row["id"], "reset", timedelta(minutes=C.RESET_TOKEN_TTL_MIN))
    link = f"{base_url}?page=reset-password&token={token}"
    mailer.send(email, "Reset your InfraGov password",
                f"Someone requested a password reset for your InfraGov account.\n\nReset it here (valid for one hour):\n{link}\n\n"
                "If this wasn't you, ignore this e-mail — your password is unchanged.\n")
    auth.log_security_event("password.reset_requested", row["id"])


def complete_password_reset(raw_token: str, new: str, confirm: str) -> str:
    row = auth.peek_auth_token(raw_token)
    if not row:
        raise ValidationError("This link is invalid or has expired.")
    user = auth.get_user_by_id(row["user_id"])
    if not user or not user.get("is_active"):
        raise ValidationError("This link is invalid or has expired.")
    if new != confirm:
        raise ValidationError("Passwords don't match.")
    errs = password_policy_errors(new, user["email"], user.get("name") or "")
    if errs:
        raise ValidationError(" ".join(errs))
    if not auth.consume_auth_token(raw_token):
        raise ValidationError("This link is invalid or has expired.")
    auth.set_password(user["id"], new)
    auth.revoke_all_sessions(user["id"])
    auth.log_security_event("password.reset_completed", user["id"])
    return user["id"]
