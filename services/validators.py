"""
Input validation & sanitisation.

Defence in depth: every query is parameterised (services/db.py), so input can
never change SQL structure. On top of that, untrusted input is validated
against strict allow-lists *before* it reaches the data layer, and free text
is normalised (control characters stripped, length bounded).

Output encoding is handled by React/Dash, which escapes all text children;
the app never renders raw HTML from data (no dangerously_allow_html, no
HTML-mode Markdown).
"""
from __future__ import annotations

import re
import unicodedata
import uuid

import constants as C

_EMAIL_RE = re.compile(C.EMAIL_PATTERN)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_FY_RE = re.compile(r"^(\d{4}|\d{2}/\d{2})$")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ ()\-]+")

COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789012", "qwertyuiop", "letmein",
    "welcome", "admin", "administrator", "infragov", "changeme", "iloveyou",
    "passw0rd", "p@ssw0rd", "p@ssword", "abc123", "111111111111", "000000000000",
}


class ValidationError(ValueError):
    """Raised with a user-safe message when input is rejected."""


def clean_text(value: object, max_len: int, *, multiline: bool = True) -> str:
    """Normalise free text: NFC, strip control/bidi chars, bound length."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFC", str(value))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        s = s.replace("\n", " ")
    s = _CONTROL.sub("", s)
    return s.strip()[:max_len]


def validate_email(value: object) -> str:
    """Validate the username (e-mail) field. Returns the canonical form.

    Rejects anything outside a strict allow-list — quotes, spaces, semicolons,
    comment markers and other SQL/meta characters can never pass.
    """
    if not isinstance(value, str):
        raise ValidationError("Enter a valid e-mail address.")
    email = unicodedata.normalize("NFKC", value).strip().lower()
    if not email or len(email) > C.EMAIL_MAX_LENGTH:
        raise ValidationError("Enter a valid e-mail address.")
    if not email.isascii() or not _EMAIL_RE.match(email) or ".." in email:
        raise ValidationError("Enter a valid e-mail address.")
    return email


def is_valid_email(value: object) -> bool:
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


def validate_password_input(value: object) -> str:
    """Bound the size of a submitted password (login) without judging strength."""
    if not isinstance(value, str) or not value or len(value) > C.PASSWORD_MAX_LENGTH:
        raise ValidationError("Invalid email or password.")
    return value


def password_policy_errors(password: str, email: str = "", name: str = "") -> list[str]:
    errors: list[str] = []
    if len(password) < C.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {C.PASSWORD_MIN_LENGTH} characters.")
    if len(password) > C.PASSWORD_MAX_LENGTH:
        errors.append(f"Password must be at most {C.PASSWORD_MAX_LENGTH} characters.")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        errors.append("Use at least three of: lower-case, upper-case, digits, symbols.")
    low = password.lower()
    if low in COMMON_PASSWORDS or len(set(password)) < 5:
        errors.append("That password is too common or too simple.")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in low:
        errors.append("Password must not contain your e-mail name.")
    if name and any(len(part) >= 4 and part.lower() in low for part in name.split()):
        errors.append("Password must not contain your name.")
    return errors


def validate_uuid(value: object) -> str:
    s = str(value or "").strip().lower()
    if not _UUID_RE.match(s):
        raise ValidationError("Invalid identifier.")
    return s


def is_uuid(value: object) -> bool:
    return bool(_UUID_RE.match(str(value or "").strip().lower()))


def validate_token(value: object) -> str:
    s = str(value or "").strip()
    if not _TOKEN_RE.match(s):
        raise ValidationError("This link is invalid or has expired.")
    return s


def validate_int(value: object, lo: int, hi: int) -> int:
    try:
        n = int(str(value))
    except (TypeError, ValueError):
        raise ValidationError("Invalid number.") from None
    if n < lo or n > hi:
        raise ValidationError("Number out of range.")
    return n


def validate_choice(value: object, allowed: tuple[str, ...] | list[str]) -> str:
    s = str(value or "")
    if s not in allowed:
        raise ValidationError("Invalid option.")
    return s


def validate_fiscal_year(value: object) -> str:
    s = str(value or "").strip()
    if not _FY_RE.match(s):
        raise ValidationError("Invalid fiscal year.")
    return s


def safe_filename(name: object, max_len: int = 160) -> str:
    base = str(name or "file").replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _SAFE_FILENAME.sub("_", base).strip(" .") or "file"
    if len(base) > max_len:
        stem, dot, ext = base.rpartition(".")
        base = (stem[: max_len - len(ext) - 1] + "." + ext) if dot else base[:max_len]
    return base


def new_uuid() -> str:
    return str(uuid.uuid4())


def csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR)."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s
