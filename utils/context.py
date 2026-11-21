"""Per-request page context and callback guard helpers."""
from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import flask
from dash import no_update
from dash.exceptions import PreventUpdate

from services import auth
from services.repository import Forbidden, NotFound
from services.validators import ValidationError
from utils.i18n import normalise_locale

log = logging.getLogger("infragov.ui")


@dataclass
class Ctx:
    user: dict | None
    locale: str
    page: str
    params: dict[str, str]
    nav_countries: dict[str, list[str]] = field(default_factory=lambda: {"infragov": [], "pagfa": []})
    assessment_kind: str | None = None
    pending: list[dict] = field(default_factory=list)
    bell: Any = None


def current_locale() -> str:
    try:
        return normalise_locale(flask.session.get("locale"))
    except RuntimeError:
        return "en"


def require_user() -> dict:
    """For use inside callbacks: the signed-in user or stop the callback."""
    user = auth.current_user()
    if not user:
        raise PreventUpdate
    return user


def user_message(exc: Exception) -> str:
    if isinstance(exc, (ValidationError, Forbidden, NotFound)):
        return str(exc) or "That action isn't allowed."
    log.exception("Callback failed")
    return "Something went wrong. Please try again."


def refresh_token() -> float:
    return time.time()


def safe_action(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run a mutation; convert known errors to a message string."""

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw), ""
        except PreventUpdate:
            raise
        except Exception as exc:  # noqa: BLE001
            return None, user_message(exc)

    return wrapper


NO = no_update


def base_url() -> str:
    """Absolute app URL for links in e-mails.

    Uses APP_BASE_URL (never the request Host header, which an attacker can
    spoof to poison reset links). Falls back to the request host only in
    development.
    """
    import dash

    import constants as C

    if C.APP_BASE_URL:
        return C.APP_BASE_URL.rstrip("/") + "/"
    prefix = dash.get_relative_path("/")
    if not C.IS_PRODUCTION:
        try:
            return flask.request.host_url.rstrip("/") + prefix
        except RuntimeError:
            pass
    return prefix
